from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "storm" / "scripts" / "storm_state.py"
SPEC = importlib.util.spec_from_file_location("storm_state", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load storm_state.py")
STATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE)


class CheckpointRoundTripTests(unittest.TestCase):
    def run_cli(self, *args: str, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected_returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def init_run(self, output: Path) -> Path:
        self.run_cli(
            "init",
            "--mode",
            "classic",
            "--topic",
            "Agent memory systems",
            "--output",
            str(output),
        )
        return output / ".storm-run" / "run.json"

    def test_checkpoint_round_trip_preserves_state_and_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            advanced = json.loads(
                self.run_cli(
                    "advance", "--run", str(run_path), "--event", "scope_defined"
                ).stdout
            )

            reloaded = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            self.assertEqual(reloaded, advanced)
            self.run_cli("validate", "--run", str(run_path))
            events = [
                json.loads(line)
                for line in (run_path.parent / "event-log.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual([event["event_id"] for event in events], [1, 2])
            self.assertEqual(events[1]["before_state_hash"], events[0]["after_state_hash"])

    def test_corrupt_and_unknown_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            run_path.write_text("{not-json", encoding="utf-8")
            corrupt = self.run_cli(
                "validate", "--run", str(run_path), expected_returncode=2
            )
            self.assertIn("not valid JSON", corrupt.stderr)

        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            state = json.loads(run_path.read_text(encoding="utf-8"))
            state["schema_version"] = "99.0"
            run_path.write_text(json.dumps(state), encoding="utf-8")
            unknown = self.run_cli(
                "validate", "--run", str(run_path), expected_returncode=2
            )
            self.assertIn("unsupported schema_version", unknown.stderr)

        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            event_path = run_path.parent / "event-log.jsonl"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["event"] = "tampered"
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            corrupt_event = self.run_cli(
                "validate", "--run", str(run_path), expected_returncode=2
            )
            self.assertIn("invalid initial event", corrupt_event.stderr)

    def test_interrupted_second_replace_keeps_last_valid_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            real_replace = os.replace
            replace_count = 0

            def fail_second_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
                nonlocal replace_count
                replace_count += 1
                if replace_count == 2:
                    raise OSError("simulated interruption")
                real_replace(source, destination)

            args = argparse.Namespace(run=str(run_path), event="scope_defined")
            with mock.patch.object(STATE.os, "replace", side_effect=fail_second_replace):
                with self.assertRaises(OSError):
                    STATE.advance_run(args)

            state, events = STATE.load_guarded_run(run_path)
            self.assertEqual(state["phase"], "INITIALIZED")
            self.assertEqual(state["last_event_id"], 1)
            self.assertEqual(len(events), 1)

            recovered = STATE.advance_run(args)
            self.assertEqual(recovered["phase"], "SCOPED")
            self.assertEqual(recovered["last_event_id"], 2)


if __name__ == "__main__":
    unittest.main()
