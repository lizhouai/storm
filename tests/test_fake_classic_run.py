from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "storm" / "scripts"
STATE_CLI = SCRIPTS / "storm_state.py"
ARTIFACT_CLI = SCRIPTS / "validate_artifacts.py"
CITATION_CLI = SCRIPTS / "audit_citations.py"
RETRIEVAL_CLI = SCRIPTS / "retrieval_backend.py"
FIXTURES = ROOT / "tests" / "fixtures" / "classic-run"
RETRIEVAL_FIXTURES = ROOT / "tests" / "fixtures" / "retrieval"

TRANSITIONS = (
    ("scope_defined", "SCOPED"),
    ("perspectives_ready", "PERSPECTIVES_READY"),
    ("interviews_completed", "INTERVIEWS_COMPLETE"),
    ("information_table_ready", "INFORMATION_TABLE_READY"),
    ("direct_outline_ready", "DIRECT_OUTLINE_READY"),
    ("refined_outline_ready", "REFINED_OUTLINE_READY"),
    ("draft_ready", "DRAFT_READY"),
    ("polished", "POLISHED"),
    ("verified", "VERIFIED"),
    ("completed", "COMPLETE"),
)

NONTERMINAL_PHASES = (
    "INITIALIZED",
    "SCOPED",
    "PERSPECTIVES_READY",
    "INTERVIEWS_COMPLETE",
    "INFORMATION_TABLE_READY",
    "DIRECT_OUTLINE_READY",
    "REFINED_OUTLINE_READY",
    "DRAFT_READY",
    "POLISHED",
    "VERIFIED",
)


class FakeClassicRunTests(unittest.TestCase):
    def run_python(
        self, script: Path, *args: str, expected_returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected_returncode,
            msg=f"command: {script.name} {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def test_fake_classic_run_reaches_complete_through_real_clis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            result = self.run_complete(output)

            self.assertEqual(result["state"]["phase"], "COMPLETE")
            self.assertEqual(result["state"]["status"], "complete")
            self.assertIsNone(result["state"]["next_action"])
            self.assertTrue(result["citation_report"]["valid"])
            self.assertTrue(result["artifact_report"]["valid"])
            self.assertEqual(len(result["artifact_report"]["artifacts"]), 4)
            retrieval_rows = [
                json.loads(line)
                for line in (output / ".storm-run" / "retrieval-log.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertTrue(retrieval_rows)
            self.assertTrue(all(row["backend_used"] == "lexical" for row in retrieval_rows))
            self.assertTrue(all(row["model"] is None for row in retrieval_rows))

    def test_every_nonterminal_phase_resumes_in_a_fresh_process(self) -> None:
        for phase in NONTERMINAL_PHASES:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "run"
                state = self.build_to_phase(output, phase)
                before_action = state["next_action"]

                interrupted = self.state_command(
                    output,
                    "fail",
                    "--error",
                    f"simulated interruption at {phase}",
                )
                resumed = self.state_command(output, "resume")

                self.assertEqual(interrupted["phase"], phase)
                self.assertEqual(interrupted["status"], "failed")
                self.assertEqual(resumed["phase"], phase)
                self.assertEqual(resumed["status"], "running")
                self.assertEqual(resumed["next_action"], before_action)

    def test_repeated_fake_inputs_have_identical_normalized_events_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_complete(Path(directory) / "first")
            second = self.run_complete(Path(directory) / "second")

            self.assertEqual(first["normalized_events"], second["normalized_events"])
            self.assertEqual(
                self.public_hashes(first["artifact_report"]),
                self.public_hashes(second["artifact_report"]),
            )

    def test_required_phase_evidence_fails_closed(self) -> None:
        cases = (
            ("SCOPED", "perspectives_ready", "perspectives.json"),
            ("PERSPECTIVES_READY", "interviews_completed", "retrieval-log.jsonl"),
            ("INTERVIEWS_COMPLETE", "information_table_ready", "information-table.jsonl"),
            ("INFORMATION_TABLE_READY", "direct_outline_ready", "direct_gen_outline"),
            ("DIRECT_OUTLINE_READY", "refined_outline_ready", "storm_gen_outline"),
            ("REFINED_OUTLINE_READY", "draft_ready", "storm_gen_article"),
            ("DRAFT_READY", "polished", "storm_gen_article_polished"),
            ("POLISHED", "verified", "citation-audit.json"),
        )
        for phase, event, expected_error in cases:
            with self.subTest(event=event), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "run"
                state = self.build_to_phase(output, phase)

                rejected = self.run_python(
                    STATE_CLI,
                    "advance",
                    "--run",
                    str(self.run_path(output)),
                    "--event",
                    event,
                    expected_returncode=2,
                )

                self.assertIn(expected_error, rejected.stderr)
                unchanged = self.state_command(output, "status")
                self.assertEqual(unchanged["phase"], state["phase"])
                self.assertEqual(unchanged["last_event_id"], state["last_event_id"])

    def run_complete(self, output: Path) -> dict[str, object]:
        state = self.build_to_phase(output, "COMPLETE")
        events = [
            json.loads(line)
            for line in (output / ".storm-run" / "event-log.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        return {
            "state": state,
            "citation_report": json.loads(
                (output / ".storm-run" / "citation-audit.json").read_text(
                    encoding="utf-8"
                )
            ),
            "artifact_report": self.validate_bundle(output),
            "normalized_events": [
                {
                    "event_id": event["event_id"],
                    "event": event["event"],
                    "before_phase": event["before_phase"],
                    "after_phase": event["after_phase"],
                    "before_status": event["before_status"],
                    "after_status": event["after_status"],
                    "artifact_hashes": event["artifact_hashes"],
                    "error": event["error"],
                }
                for event in events
            ],
        }

    def build_to_phase(self, output: Path, target_phase: str) -> dict[str, object]:
        output.mkdir(parents=True, exist_ok=True)
        state = json.loads(
            self.run_python(
                STATE_CLI,
                "init",
                "--mode",
                "classic",
                "--topic",
                "Deterministic RAG evaluation",
                "--output",
                str(output),
            ).stdout
        )
        if target_phase == "INITIALIZED":
            return state
        for event, resulting_phase in TRANSITIONS:
            self.stage_evidence(output, event)
            if event == "verified":
                self.run_citation_audit(output)
                self.validate_bundle(output, staging=True)
            state = self.state_command(output, "advance", "--event", event)
            if resulting_phase == target_phase:
                return state
        self.fail(f"unknown target phase: {target_phase}")

    def stage_evidence(self, output: Path, event: str) -> None:
        control = output / ".storm-run"
        fixture_names = {
            "perspectives_ready": ("perspectives.json",),
            "interviews_completed": ("interviews.jsonl",),
            "information_table_ready": ("information-table.jsonl",),
            "direct_outline_ready": ("direct_gen_outline.html",),
            "refined_outline_ready": ("storm_gen_outline.html",),
            "draft_ready": ("storm_gen_article.html",),
            "polished": ("storm_gen_article_polished.html",),
            "verified": ("sources.json", "claim-support.json"),
        }.get(event, ())
        for name in fixture_names:
            destination = (
                control / name
                if name.endswith((".json", ".jsonl"))
                else control / "staging" / name
            )
            shutil.copyfile(FIXTURES / name, destination)
        if event == "interviews_completed":
            index_path = control / "retrieval-index.json"
            trace_path = control / "retrieval-log.jsonl"
            self.run_python(
                RETRIEVAL_CLI,
                "index",
                "--backend",
                "lexical",
                "--corpus",
                str(RETRIEVAL_FIXTURES / "corpus.jsonl"),
                "--output",
                str(index_path),
                "--chunk-size",
                "500",
                "--chunk-overlap",
                "0",
            )
            for query in (
                "deterministic retrieval fixed evidence",
                "citation audit unsupported claims",
            ):
                self.run_python(
                    RETRIEVAL_CLI,
                    "search",
                    "--index",
                    str(index_path),
                    "--query",
                    query,
                    "--top-k",
                    "1",
                    "--trace",
                    str(trace_path),
                )

    def run_citation_audit(self, output: Path) -> dict[str, object]:
        control = output / ".storm-run"
        return json.loads(
            self.run_python(
                CITATION_CLI,
                "--article",
                str(control / "staging" / "storm_gen_article_polished.html"),
                "--sources",
                str(control / "sources.json"),
                "--claims",
                str(control / "claim-support.json"),
                "--run",
                str(self.run_path(output)),
                "--staging",
            ).stdout
        )

    def validate_bundle(
        self, output: Path, *, staging: bool = False
    ) -> dict[str, object]:
        extra_args = ("--staging",) if staging else ()
        return json.loads(
            self.run_python(
                ARTIFACT_CLI,
                str(output),
                "--topic",
                "Deterministic RAG evaluation",
                "--run",
                str(self.run_path(output)),
                *extra_args,
            ).stdout
        )

    def state_command(self, output: Path, command: str, *args: str) -> dict[str, object]:
        return json.loads(
            self.run_python(
                STATE_CLI,
                command,
                "--run",
                str(self.run_path(output)),
                *args,
            ).stdout
        )

    @staticmethod
    def run_path(output: Path) -> Path:
        return output / ".storm-run" / "run.json"

    @staticmethod
    def public_hashes(report: dict[str, object]) -> dict[str, str]:
        artifacts = report["artifacts"]
        return {
            name: metadata["sha256"]
            for name, metadata in artifacts.items()
        }


if __name__ == "__main__":
    unittest.main()
