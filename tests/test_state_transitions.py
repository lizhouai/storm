from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "storm" / "scripts" / "storm_state.py"


class StormStateCliTests(unittest.TestCase):
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

    def init_run(self, output: Path, mode: str = "classic") -> Path:
        self.run_cli(
            "init",
            "--mode",
            mode,
            "--topic",
            "Current RAG evaluation",
            "--output",
            str(output),
        )
        return output / ".storm-run" / "run.json"

    def write_jsonl(self, path: Path, records: list[dict[str, object]]) -> None:
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_init_creates_a_valid_classic_run_and_initial_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "rag-evaluation"

            result = self.run_cli(
                "init",
                "--mode",
                "classic",
                "--topic",
                "Current RAG evaluation",
                "--output",
                str(output),
            )

            state = json.loads(result.stdout)
            run_path = output / ".storm-run" / "run.json"
            events_path = output / ".storm-run" / "event-log.jsonl"
            self.assertEqual(json.loads(run_path.read_text(encoding="utf-8")), state)
            self.assertEqual(state["schema_version"], "1.0")
            self.assertEqual(state["mode"], "classic")
            self.assertEqual(state["phase"], "INITIALIZED")
            self.assertEqual(state["status"], "running")
            self.assertEqual(state["next_action"], "define_scope")
            self.assertEqual(state["last_event_id"], 1)
            self.assertTrue(state["run_id"].startswith("storm-"))
            uuid.UUID(state["run_id"].removeprefix("storm-"))

            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_id"], 1)
            self.assertEqual(events[0]["event"], "initialized")
            self.assertIsNone(events[0]["before_phase"])
            self.assertEqual(events[0]["after_phase"], "INITIALIZED")
            self.assertIn("before_state_hash", events[0])
            self.assertIn("after_state_hash", events[0])
            self.assertEqual(events[0]["artifact_hashes"], {})

    def test_status_and_validate_read_back_the_guarded_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")

            status = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            validation = json.loads(
                self.run_cli("validate", "--run", str(run_path)).stdout
            )

            self.assertEqual(status["phase"], "INITIALIZED")
            self.assertEqual(validation, {"valid": True, "run_id": status["run_id"]})

    def test_advance_applies_a_legal_transition_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")

            first = json.loads(
                self.run_cli(
                    "advance", "--run", str(run_path), "--event", "scope_defined"
                ).stdout
            )
            repeated = json.loads(
                self.run_cli(
                    "advance", "--run", str(run_path), "--event", "scope_defined"
                ).stdout
            )

            self.assertEqual(first, repeated)
            self.assertEqual(first["phase"], "SCOPED")
            self.assertEqual(first["next_action"], "generate_perspectives")
            self.assertEqual(first["last_event_id"], 2)
            events = (
                run_path.parent / "event-log.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 2)

    def test_perspective_transition_requires_basic_writer_and_unique_role_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            self.run_cli(
                "advance", "--run", str(run_path), "--event", "scope_defined"
            )

            missing = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "perspectives_ready",
                expected_returncode=2,
            )
            self.assertIn("perspectives.json", missing.stderr)

            perspectives_path = run_path.parent / "perspectives.json"
            perspectives_path.write_text(
                json.dumps(
                    [
                        {"id": "P1", "role": "Basic fact writer"},
                        {"id": "P2", "role": "Retrieval specialist"},
                    ]
                ),
                encoding="utf-8",
            )
            state = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "perspectives_ready",
                ).stdout
            )
            self.assertEqual(state["phase"], "PERSPECTIVES_READY")

    def test_classic_run_follows_every_phase_and_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.init_run(output)
            control = run_path.parent
            (control / "perspectives.json").write_text(
                json.dumps(
                    [
                        {"id": "P1", "role": "Basic fact writer"},
                        {"id": "P2", "role": "Evaluation specialist"},
                    ]
                ),
                encoding="utf-8",
            )
            self.write_jsonl(
                control / "retrieval-log.jsonl",
                [{"source_id": "S1"}, {"source_id": "S2"}],
            )
            self.write_jsonl(
                control / "interviews.jsonl",
                [
                    {"perspective_id": "P1", "queries": ["rag evaluation"], "source_ids": ["S1"]},
                    {"perspective_id": "P2", "queries": ["rag metrics"], "source_ids": ["S2"]},
                ],
            )
            self.write_jsonl(
                control / "information-table.jsonl",
                [
                    {
                        "source_id": "S1",
                        "snippet": "Evidence",
                        "claim_supported": "Claim",
                        "reliability_note": "primary",
                    }
                ],
            )
            for name in (
                "direct_gen_outline.html",
                "storm_gen_outline.html",
                "storm_gen_article.html",
                "storm_gen_article_polished.html",
            ):
                (output / name).write_text("<html>evidence</html>", encoding="utf-8")
            (control / "citation-audit.json").write_text(
                json.dumps({"valid": True}), encoding="utf-8"
            )

            expected = [
                ("scope_defined", "SCOPED", "generate_perspectives"),
                ("perspectives_ready", "PERSPECTIVES_READY", "run_interviews"),
                ("interviews_completed", "INTERVIEWS_COMPLETE", "build_information_table"),
                ("information_table_ready", "INFORMATION_TABLE_READY", "generate_direct_outline"),
                ("direct_outline_ready", "DIRECT_OUTLINE_READY", "refine_outline"),
                ("refined_outline_ready", "REFINED_OUTLINE_READY", "write_draft"),
                ("draft_ready", "DRAFT_READY", "polish_article"),
                ("polished", "POLISHED", "verify_artifacts"),
                ("verified", "VERIFIED", "publish"),
                ("completed", "COMPLETE", None),
            ]
            for event, phase, next_action in expected:
                state = json.loads(
                    self.run_cli(
                        "advance", "--run", str(run_path), "--event", event
                    ).stdout
                )
                self.assertEqual((state["phase"], state["next_action"]), (phase, next_action))
            self.assertEqual(state["status"], "complete")

    def test_interviews_require_valid_turns_queries_and_resolvable_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            control = run_path.parent
            (control / "perspectives.json").write_text(
                json.dumps([{"id": "P1", "role": "Basic fact writer"}]),
                encoding="utf-8",
            )
            for event in ("scope_defined", "perspectives_ready"):
                self.run_cli("advance", "--run", str(run_path), "--event", event)
            self.write_jsonl(
                control / "interviews.jsonl",
                [{"perspective_id": "P1", "queries": ["rag"], "source_ids": ["S1"]}],
            )

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "interviews_completed",
                expected_returncode=2,
            )
            self.assertIn("retrieval-log.jsonl", rejected.stderr)

            self.write_jsonl(control / "retrieval-log.jsonl", [{"source_id": "S1"}])
            state = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "interviews_completed",
                ).stdout
            )
            self.assertEqual(state["phase"], "INTERVIEWS_COMPLETE")

    def test_information_table_requires_complete_deduplicated_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            control = run_path.parent
            (control / "perspectives.json").write_text(
                json.dumps([{"id": "P1", "role": "Basic fact writer"}]),
                encoding="utf-8",
            )
            self.write_jsonl(control / "retrieval-log.jsonl", [{"source_id": "S1"}])
            self.write_jsonl(
                control / "interviews.jsonl",
                [{"perspective_id": "P1", "queries": ["rag"], "source_ids": ["S1"]}],
            )
            for event in ("scope_defined", "perspectives_ready", "interviews_completed"):
                self.run_cli("advance", "--run", str(run_path), "--event", event)

            missing = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "information_table_ready",
                expected_returncode=2,
            )
            self.assertIn("information-table.jsonl", missing.stderr)

            self.write_jsonl(
                control / "information-table.jsonl",
                [{"source_id": "S1", "snippet": "Evidence", "claim_supported": "Claim", "reliability_note": "primary"}],
            )
            state = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "information_table_ready",
                ).stdout
            )
            self.assertEqual(state["phase"], "INFORMATION_TABLE_READY")

    def test_outline_transition_requires_the_expected_public_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.init_run(output)
            control = run_path.parent
            (control / "perspectives.json").write_text(
                json.dumps([{"id": "P1", "role": "Basic fact writer"}]),
                encoding="utf-8",
            )
            self.write_jsonl(control / "retrieval-log.jsonl", [{"source_id": "S1"}])
            self.write_jsonl(
                control / "interviews.jsonl",
                [{"perspective_id": "P1", "queries": ["rag"], "source_ids": ["S1"]}],
            )
            self.write_jsonl(
                control / "information-table.jsonl",
                [{"source_id": "S1", "snippet": "Evidence", "claim_supported": "Claim"}],
            )
            for event in (
                "scope_defined",
                "perspectives_ready",
                "interviews_completed",
                "information_table_ready",
            ):
                self.run_cli("advance", "--run", str(run_path), "--event", event)

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "direct_outline_ready",
                expected_returncode=2,
            )
            self.assertIn("direct_gen_outline", rejected.stderr)

            (output / "direct_gen_outline.html").write_text("outline", encoding="utf-8")
            advanced = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "direct_outline_ready",
                ).stdout
            )
            self.assertEqual(advanced["phase"], "DIRECT_OUTLINE_READY")

    def test_fail_block_and_resume_preserve_phase_and_retry_the_same_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")

            failed = json.loads(
                self.run_cli(
                    "fail", "--run", str(run_path), "--error", "retriever unavailable"
                ).stdout
            )
            repeated_failure = json.loads(
                self.run_cli(
                    "fail", "--run", str(run_path), "--error", "retriever unavailable"
                ).stdout
            )
            self.assertEqual(failed, repeated_failure)
            self.assertEqual((failed["phase"], failed["next_action"]), ("INITIALIZED", "define_scope"))
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["last_event_id"], 2)

            resumed = json.loads(self.run_cli("resume", "--run", str(run_path)).stdout)
            repeated_resume = json.loads(
                self.run_cli("resume", "--run", str(run_path)).stdout
            )
            self.assertEqual(resumed, repeated_resume)
            self.assertEqual(resumed["status"], "running")
            self.assertEqual(resumed["attempt"], 2)

            blocked = json.loads(
                self.run_cli(
                    "block", "--run", str(run_path), "--reason", "user input required"
                ).stdout
            )
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked["phase"], "INITIALIZED")
            resumed_again = json.loads(
                self.run_cli("resume", "--run", str(run_path)).stdout
            )
            self.assertEqual(resumed_again["attempt"], 3)
            self.assertEqual(resumed_again["next_action"], "define_scope")

    def test_co_storm_uses_the_frozen_outer_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run", mode="co-storm")
            expected = [
                ("warm_start_started", "WARM_START_RUNNING", "complete_warm_start"),
                ("warm_start_completed", "INTERACTIVE", "continue_roundtable"),
                ("reporting_started", "REPORTING", "verify_report"),
                ("verified", "VERIFIED", "publish"),
                ("completed", "COMPLETE", None),
            ]
            for event, phase, next_action in expected:
                state = json.loads(
                    self.run_cli(
                        "advance", "--run", str(run_path), "--event", event
                    ).stdout
                )
                self.assertEqual((state["phase"], state["next_action"]), (phase, next_action))
            self.assertEqual(state["status"], "complete")

    def test_unknown_and_out_of_order_events_fail_without_changing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(Path(temporary_directory) / "run")
            original = run_path.read_bytes()

            unknown = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "made_up",
                expected_returncode=2,
            )
            self.assertIn("unknown transition event", unknown.stderr)
            out_of_order = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "interviews_completed",
                expected_returncode=2,
            )
            self.assertIn("illegal transition", out_of_order.stderr)
            self.assertEqual(run_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
