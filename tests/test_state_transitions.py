from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "storm" / "scripts" / "storm_state.py"
ARTIFACT_SCRIPT = ROOT / "skills" / "storm" / "scripts" / "validate_artifacts.py"
FIXTURES = ROOT / "tests" / "fixtures" / "classic-run"
STATE_SPEC = importlib.util.spec_from_file_location("storm_state_under_test", SCRIPT)
assert STATE_SPEC and STATE_SPEC.loader
STATE_MODULE = importlib.util.module_from_spec(STATE_SPEC)
STATE_SPEC.loader.exec_module(STATE_MODULE)


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

    def validate_artifacts(
        self, output: Path, run_path: Path
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                str(ARTIFACT_SCRIPT),
                str(output),
                "--run",
                str(run_path),
                "--staging",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def write_citation_audit(self, run_path: Path, *, valid: bool) -> None:
        (run_path.parent / "citation-audit.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "valid": valid,
                    "article": "storm_gen_article_polished.html",
                    "used_citation_ids": [1],
                    "sources": [],
                    "claims": [],
                    "errors": [] if valid else ["unsupported claim"],
                }
            ),
            encoding="utf-8",
        )

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

    def write_turn_payload(
        self,
        run_path: Path,
        *,
        turn_id: int,
        input_event: str = "USER_ASK",
        policy: str = "QUESTION_ANSWERING",
        next_actions: list[str] | None = None,
    ) -> Path:
        payload_path = run_path.parent / f"turn-{turn_id}.json"
        payload_path.write_text(
            json.dumps(
                {
                    "turn_id": turn_id,
                    "input_event": input_event,
                    "policy": policy,
                    "participants": [
                        {
                            "id": "basic",
                            "display_name": "Basic fact writer",
                            "role": "Basic fact writer",
                        },
                        {
                            "id": "moderator",
                            "display_name": "Moderator",
                            "role": "Moderator",
                        },
                    ],
                    "retrieval_records": [
                        {"query": "rag evaluation", "source_ids": ["S1"]}
                    ],
                    "mind_map_delta": {
                        "added": ["evaluation"],
                        "updated": [],
                        "removed": [],
                    },
                    "citations": [{"citation_id": 1, "source_id": "S1"}],
                    "next_actions": (
                        ["compare evaluation layers"]
                        if next_actions is None
                        else next_actions
                    ),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return payload_path

    def prepare_classic_run_to_polished(self, output: Path) -> Path:
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
                {
                    "perspective_id": "P1",
                    "queries": ["rag evaluation"],
                    "source_ids": ["S1"],
                },
                {
                    "perspective_id": "P2",
                    "queries": ["rag metrics"],
                    "source_ids": ["S2"],
                },
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
        staging = control / "staging"
        for name in (
            "direct_gen_outline.html",
            "storm_gen_outline.html",
            "storm_gen_article.html",
            "storm_gen_article_polished.html",
        ):
            shutil.copyfile(FIXTURES / name, staging / name)
        for event in (
            "scope_defined",
            "perspectives_ready",
            "interviews_completed",
            "information_table_ready",
            "direct_outline_ready",
            "refined_outline_ready",
            "draft_ready",
            "polished",
        ):
            self.run_cli("advance", "--run", str(run_path), "--event", event)
        return run_path

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
            run_path = self.prepare_classic_run_to_polished(output)
            self.write_citation_audit(run_path, valid=True)
            self.validate_artifacts(output, run_path)

            expected = [
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

    def test_verified_rejects_a_failed_citation_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.prepare_classic_run_to_polished(output)
            self.write_citation_audit(run_path, valid=False)

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "verified",
                expected_returncode=2,
            )

            self.assertIn("citation audit must be valid", rejected.stderr)
            state = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            self.assertEqual(state["phase"], "POLISHED")

    def test_verified_requires_validated_artifact_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.prepare_classic_run_to_polished(output)
            self.write_citation_audit(run_path, valid=True)

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "verified",
                expected_returncode=2,
            )

            self.assertIn("validated artifact metadata", rejected.stderr)
            state = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            self.assertEqual(state["artifacts"], {})
            self.assertEqual(state["phase"], "POLISHED")

    def test_complete_rechecks_validated_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.prepare_classic_run_to_polished(output)
            self.write_citation_audit(run_path, valid=True)
            self.validate_artifacts(output, run_path)
            self.run_cli(
                "advance", "--run", str(run_path), "--event", "verified"
            )
            with (run_path.parent / "staging" / "storm_gen_article_polished.html").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write("\n<!-- tampered after validation -->\n")

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "completed",
                expected_returncode=2,
            )

            self.assertIn("artifact hash does not match", rejected.stderr)
            state = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            self.assertEqual(state["phase"], "VERIFIED")
            self.assertEqual(state["status"], "running")

    def test_complete_writes_an_atomic_publication_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.prepare_classic_run_to_polished(output)
            self.write_citation_audit(run_path, valid=True)
            self.validate_artifacts(output, run_path)
            self.run_cli(
                "advance", "--run", str(run_path), "--event", "verified"
            )

            completed = json.loads(
                self.run_cli(
                    "advance", "--run", str(run_path), "--event", "completed"
                ).stdout
            )

            receipt = json.loads(
                (run_path.parent / "publication.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["schema_version"], 1)
            self.assertEqual(receipt["run_id"], completed["run_id"])
            self.assertEqual(
                receipt["artifact_hashes"],
                {
                    name: metadata["sha256"]
                    for name, metadata in completed["artifacts"].items()
                },
            )
            self.assertEqual(list(output.glob("*.tmp")), [])
            self.assertEqual(list(run_path.parent.glob("*.tmp")), [])
            self.assertFalse((run_path.parent / "staging").exists())
            polished_path = output / "storm_gen_article_polished.html"
            published_bytes = polished_path.read_bytes()
            polished_path.write_bytes(published_bytes + b"\n<!-- post-complete tamper -->\n")
            tampered = self.run_cli(
                "status", "--run", str(run_path), expected_returncode=2
            )
            self.assertIn("artifact hash does not match", tampered.stderr)
            polished_path.write_bytes(published_bytes)
            (run_path.parent / "publication.json").unlink()
            rejected = self.run_cli(
                "status", "--run", str(run_path), expected_returncode=2
            )
            self.assertIn("missing publication.json", rejected.stderr)

    def test_classic_artifacts_remain_staged_until_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            self.prepare_classic_run_to_polished(output)

            public_names = {
                "direct_gen_outline.html",
                "storm_gen_outline.html",
                "storm_gen_article.html",
                "storm_gen_article_polished.html",
            }
            self.assertEqual(
                {path.name for path in output.iterdir()} & public_names,
                set(),
            )
            self.assertEqual(
                {path.name for path in (output / ".storm-run" / "staging").iterdir()},
                public_names,
            )

    def test_failed_publication_rolls_back_new_public_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            run_path = self.prepare_classic_run_to_polished(output)
            self.write_citation_audit(run_path, valid=True)
            self.validate_artifacts(output, run_path)
            self.run_cli(
                "advance", "--run", str(run_path), "--event", "verified"
            )
            state = json.loads(run_path.read_text(encoding="utf-8"))
            original_replace = STATE_MODULE.atomic_replace_bytes
            call_count = 0

            def fail_on_second(path: Path, content: bytes) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("simulated publication failure")
                original_replace(path, content)

            with mock.patch.object(
                STATE_MODULE, "atomic_replace_bytes", side_effect=fail_on_second
            ):
                with self.assertRaises(STATE_MODULE.StateError) as caught:
                    STATE_MODULE.publish_classic_artifacts(run_path, state)

            self.assertIn("atomic Classic publication failed", str(caught.exception))
            self.assertIn(str(run_path.parent / "staging"), str(caught.exception))

            self.assertEqual(list(output.glob("*.html")), [])
            self.assertFalse((run_path.parent / "publication.json").exists())
            unchanged = json.loads(
                self.run_cli("status", "--run", str(run_path)).stdout
            )
            self.assertEqual(unchanged["phase"], "VERIFIED")

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

            (control / "staging" / "direct_gen_outline.html").write_text(
                "outline", encoding="utf-8"
            )
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
            state = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "warm_start_started",
                ).stdout
            )
            self.assertEqual(state["phase"], "WARM_START_RUNNING")
            warm_start_payload = self.write_turn_payload(run_path, turn_id=1)
            self.run_cli(
                "record-turn",
                "--run",
                str(run_path),
                "--turn",
                str(warm_start_payload),
            )
            state = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "warm_start_completed",
                ).stdout
            )
            self.assertEqual(state["phase"], "INTERACTIVE")
            conclusion_payload = self.write_turn_payload(
                run_path,
                turn_id=2,
                input_event="USER_CONCLUDE",
                policy="FINAL_REPORT",
                next_actions=[],
            )
            self.run_cli(
                "record-turn",
                "--run",
                str(run_path),
                "--turn",
                str(conclusion_payload),
            )
            for event, phase, next_action in (
                ("reporting_started", "REPORTING", "verify_report"),
                ("verified", "VERIFIED", "publish"),
                ("completed", "COMPLETE", None),
            ):
                state = json.loads(
                    self.run_cli(
                        "advance", "--run", str(run_path), "--event", event
                    ).stdout
                )
                self.assertEqual(
                    (state["phase"], state["next_action"]), (phase, next_action)
                )
            self.assertEqual(state["status"], "complete")
            validation = json.loads(
                self.run_cli("validate", "--run", str(run_path)).stdout
            )
            self.assertEqual(validation["turn_count"], 2)

    def test_co_storm_warm_start_requires_a_persisted_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(
                Path(temporary_directory) / "run", mode="co-storm"
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_started",
            )

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_completed",
                expected_returncode=2,
            )

            self.assertIn("persisted Co-STORM warm-start turn", rejected.stderr)
            state = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            self.assertEqual(state["phase"], "WARM_START_RUNNING")

    def test_co_storm_warm_start_cannot_be_a_final_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(
                Path(temporary_directory) / "run", mode="co-storm"
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_started",
            )
            payload_path = self.write_turn_payload(
                run_path,
                turn_id=1,
                input_event="USER_CONCLUDE",
                policy="FINAL_REPORT",
                next_actions=[],
            )

            rejected = self.run_cli(
                "record-turn",
                "--run",
                str(run_path),
                "--turn",
                str(payload_path),
                expected_returncode=2,
            )

            self.assertIn("warm start cannot be a final report", rejected.stderr)

    def test_record_turn_persists_a_hash_linked_co_storm_warm_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(
                Path(temporary_directory) / "run", mode="co-storm"
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_started",
            )
            payload_path = self.write_turn_payload(run_path, turn_id=1)

            recorded = json.loads(
                self.run_cli(
                    "record-turn",
                    "--run",
                    str(run_path),
                    "--turn",
                    str(payload_path),
                ).stdout
            )
            repeated = json.loads(
                self.run_cli(
                    "record-turn",
                    "--run",
                    str(run_path),
                    "--turn",
                    str(payload_path),
                ).stdout
            )
            advanced = json.loads(
                self.run_cli(
                    "advance",
                    "--run",
                    str(run_path),
                    "--event",
                    "warm_start_completed",
                ).stdout
            )

            self.assertTrue(recorded["valid"])
            self.assertEqual(repeated, recorded)
            self.assertEqual(recorded["turn_count"], 1)
            self.assertRegex(recorded["latest_turn_hash"], r"^[0-9a-f]{64}$")
            turn_log = (run_path.parent / "co-storm-turns.jsonl").read_text(
                encoding="utf-8"
            )
            entry = json.loads(turn_log)
            self.assertEqual(len(turn_log.splitlines()), 1)
            self.assertEqual(entry["turn_id"], 1)
            self.assertEqual(entry["previous_turn_hash"], "0" * 64)
            self.assertEqual(entry["turn_hash"], recorded["latest_turn_hash"])
            self.assertEqual(advanced["phase"], "INTERACTIVE")

    def test_co_storm_reporting_requires_a_persisted_final_report_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(
                Path(temporary_directory) / "run", mode="co-storm"
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_started",
            )
            payload_path = self.write_turn_payload(run_path, turn_id=1)
            self.run_cli(
                "record-turn",
                "--run",
                str(run_path),
                "--turn",
                str(payload_path),
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_completed",
            )

            rejected = self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "reporting_started",
                expected_returncode=2,
            )

            self.assertIn("USER_CONCLUDE with FINAL_REPORT", rejected.stderr)
            state = json.loads(self.run_cli("status", "--run", str(run_path)).stdout)
            self.assertEqual(state["phase"], "INTERACTIVE")

    def test_co_storm_turn_log_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_path = self.init_run(
                Path(temporary_directory) / "run", mode="co-storm"
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_started",
            )
            payload_path = self.write_turn_payload(run_path, turn_id=1)
            self.run_cli(
                "record-turn",
                "--run",
                str(run_path),
                "--turn",
                str(payload_path),
            )
            self.run_cli(
                "advance",
                "--run",
                str(run_path),
                "--event",
                "warm_start_completed",
            )
            turn_log_path = run_path.parent / "co-storm-turns.jsonl"
            entry = json.loads(turn_log_path.read_text(encoding="utf-8"))
            entry["mind_map_delta"]["added"] = ["tampered branch"]
            turn_log_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

            rejected = self.run_cli(
                "status", "--run", str(run_path), expected_returncode=2
            )

            self.assertIn("invalid turn_hash", rejected.stderr)

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
