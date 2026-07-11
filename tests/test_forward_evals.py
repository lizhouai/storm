from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_forward_evals.py"
CASES = ROOT / "evals" / "cases.json"


class ForwardEvalRunnerTests(unittest.TestCase):
    def run_runner(
        self, *args: str, expected_returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(RUNNER), *args],
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

    def test_fixture_contract_canary_exercises_all_ten_cases(self) -> None:
        expected_ids = {
            case["id"]
            for case in json.loads(CASES.read_text(encoding="utf-8"))["cases"]
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"

            summary = json.loads(
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(output),
                ).stdout
            )

            self.assertEqual(summary["adapter_label"], "offline-fixture-contract-canary")
            self.assertFalse(summary["release_gate"])
            self.assertEqual(summary["case_count"], 10)
            self.assertEqual(summary["run_count"], 10)
            self.assertEqual(summary["passed_count"], 10)
            self.assertEqual(summary["illegal_transition_count"], 0)
            self.assertEqual(summary["sandbox_verification"], "offline-fixture-only")
            self.assertEqual({item["case_id"] for item in summary["results"]}, expected_ids)
            negative = next(
                item
                for item in summary["results"]
                if item["case_id"] == "claimed-complete-state-incomplete"
            )
            self.assertEqual(
                negative["detected_violations"],
                ["claimed_complete_state_incomplete"],
            )
            self.assertTrue(negative["passed"])
            self.assertEqual(len(list((output / "traces").glob("*.json"))), 10)
            self.assertEqual(
                json.loads((output / "summary.json").read_text(encoding="utf-8")),
                summary,
            )

    def test_ten_repetitions_use_fresh_subprocesses_and_isolated_workdirs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = json.loads(
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(Path(directory) / "results"),
                    "--case-id",
                    "artifact-defaults",
                    "--repetitions",
                    "10",
                ).stdout
            )

            self.assertEqual(summary["run_count"], 10)
            self.assertEqual(summary["fresh_subprocess_count"], 10)
            self.assertEqual(summary["isolated_work_directory_count"], 10)
            self.assertEqual(summary["illegal_transition_count"], 0)
            self.assertEqual(
                len({item["isolation_slot"] for item in summary["results"]}), 10
            )

    def test_normalized_trace_files_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = []
            summaries = []
            for name in ("first", "second"):
                output = root / name
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(output),
                    "--case-id",
                    "co-storm-preview",
                    "--repetitions",
                    "2",
                )
                outputs.append(
                    {
                        path.name: json.loads(path.read_text(encoding="utf-8"))
                        for path in sorted((output / "traces").glob("*.json"))
                    }
                )
                summaries.append(
                    json.loads((output / "summary.json").read_text(encoding="utf-8"))
                )

            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(summaries[0], summaries[1])
            serialized = json.dumps(outputs[0], sort_keys=True)
            self.assertIn("<uuid>", serialized)
            self.assertIn("<timestamp>", serialized)
            self.assertIn("<workdir>", serialized)
            self.assertNotIn(str(root), serialized)

    def test_objective_mismatch_is_detected_from_host_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "fake_host.py"
            host.write_text(
                textwrap.dedent(
                    """
                    import argparse
                    import json
                    from pathlib import Path

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--case", required=True)
                    parser.add_argument("--output", required=True)
                    args = parser.parse_args()
                    output = Path(args.output)
                    (output / ".storm-run").mkdir(parents=True)
                    (output / ".storm-run" / "run.json").write_text(
                        json.dumps({"mode": "classic", "phase": "COMPLETE", "status": "complete", "next_action": None}),
                        encoding="utf-8",
                    )
                    (output / ".storm-run" / "candidate-report.json").write_text(
                        json.dumps({"claimed_complete": True}), encoding="utf-8"
                    )
                    (output / ".storm-run" / "trace.json").write_text(
                        json.dumps({"objective_id": "wrong-objective", "prompt_sha256": "wrong", "actions": [], "illegal_transitions": []}),
                        encoding="utf-8",
                    )
                    for name in (
                        "direct_gen_outline.html",
                        "storm_gen_outline.html",
                        "storm_gen_article.html",
                        "storm_gen_article_polished.html",
                    ):
                        (output / name).write_text("fixture", encoding="utf-8")
                    """
                ),
                encoding="utf-8",
            )
            command = (
                f'{sys.executable} {host} --case "{{case_json}}" '
                '--output "{candidate_dir}"'
            )

            summary = json.loads(
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(root / "results"),
                    "--case-id",
                    "artifact-defaults",
                    "--agent-command",
                    command,
                    expected_returncode=1,
                ).stdout
            )

            self.assertEqual(summary["adapter_label"], "real-host-command")
            self.assertFalse(summary["external_side_effects_network_sandbox_verified"])
            self.assertEqual(summary["failed_count"], 1)
            self.assertIn("objective_mismatch", summary["results"][0]["detected_violations"])

    def test_correct_objective_with_malformed_artifacts_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "malformed_host.py"
            host.write_text(
                textwrap.dedent(
                    """
                    import argparse
                    import hashlib
                    import json
                    from pathlib import Path

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--case", required=True)
                    parser.add_argument("--output", required=True)
                    args = parser.parse_args()
                    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
                    output = Path(args.output)
                    (output / ".storm-run").mkdir(parents=True)
                    (output / ".storm-run" / "run.json").write_text(
                        json.dumps({"mode": "classic", "phase": "COMPLETE", "status": "complete", "next_action": None}),
                        encoding="utf-8",
                    )
                    (output / ".storm-run" / "candidate-report.json").write_text(
                        json.dumps({"claimed_complete": True}), encoding="utf-8"
                    )
                    (output / ".storm-run" / "trace.json").write_text(
                        json.dumps({
                            "objective_id": case["id"],
                            "prompt_sha256": hashlib.sha256(case["prompt"].encode("utf-8")).hexdigest(),
                            "actions": [],
                            "illegal_transitions": [],
                        }),
                        encoding="utf-8",
                    )
                    for name in (
                        "direct_gen_outline.html",
                        "storm_gen_outline.html",
                        "storm_gen_article.html",
                        "storm_gen_article_polished.html",
                    ):
                        (output / name).write_text("malformed", encoding="utf-8")
                    (output.parent / "escaped.txt").write_text("escape", encoding="utf-8")
                    """
                ),
                encoding="utf-8",
            )
            command = (
                f'{sys.executable} {host} --case "{{case_json}}" '
                '--output "{candidate_dir}"'
            )

            summary = json.loads(
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(root / "results"),
                    "--case-id",
                    "artifact-defaults",
                    "--agent-command",
                    command,
                    expected_returncode=1,
                ).stdout
            )

            violations = summary["results"][0]["detected_violations"]
            self.assertNotIn("objective_mismatch", violations)
            self.assertIn("artifact_bundle_invalid", violations)
            self.assertIn("workspace_escape", violations)

    def test_forged_valid_citation_audit_is_recomputed_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "forged_audit_host.py"
            host.write_text(
                f"RUNNER_PATH = {str(RUNNER)!r}\n"
                + textwrap.dedent(
                    """
                    import argparse
                    import importlib.util
                    import json
                    from pathlib import Path

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--case", required=True)
                    parser.add_argument("--output", required=True)
                    args = parser.parse_args()
                    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
                    output = Path(args.output)
                    spec = importlib.util.spec_from_file_location("forward_runner", RUNNER_PATH)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.run_fixture_adapter(
                        {
                            "id": case["id"],
                            "prompt": case["prompt"],
                            "forward": {"fixture": "artifact-complete"},
                        },
                        output,
                    )
                    control = output / ".storm-run"
                    (control / "sources.json").write_text("{}", encoding="utf-8")
                    (control / "citation-audit.json").write_text(
                        json.dumps({"valid": True, "errors": []}), encoding="utf-8"
                    )
                    """
                ),
                encoding="utf-8",
            )
            command = (
                f'{sys.executable} {host} --case "{{case_json}}" '
                '--output "{candidate_dir}"'
            )

            summary = json.loads(
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(root / "results"),
                    "--case-id",
                    "artifact-defaults",
                    "--agent-command",
                    command,
                    expected_returncode=1,
                ).stdout
            )

            violations = summary["results"][0]["detected_violations"]
            self.assertNotIn("objective_mismatch", violations)
            self.assertIn("artifact_bundle_invalid", violations)

    def test_output_reuse_requires_replace_and_removes_stale_traces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            stale_trace = output / "traces" / "stale.json"
            stale_trace.parent.mkdir(parents=True)
            stale_trace.write_text("stale", encoding="utf-8")

            refused = self.run_runner(
                "--cases",
                str(CASES),
                "--output",
                str(output),
                "--case-id",
                "artifact-defaults",
                expected_returncode=2,
            )
            self.assertIn("non-empty", refused.stderr)
            self.assertTrue(stale_trace.exists())

            summary = json.loads(
                self.run_runner(
                    "--cases",
                    str(CASES),
                    "--output",
                    str(output),
                    "--case-id",
                    "artifact-defaults",
                    "--replace",
                ).stdout
            )
            self.assertEqual(summary["passed_count"], 1)
            self.assertFalse(stale_trace.exists())
            self.assertEqual(
                [path.name for path in (output / "traces").glob("*.json")],
                ["artifact-defaults-r01.json"],
            )

    def test_custom_cases_reject_traversal_and_unsupported_fields(self) -> None:
        base_case = json.loads(CASES.read_text(encoding="utf-8"))["cases"][0]
        cases = (
            ("traversal", {**base_case, "id": "../escape"}, "kebab-case"),
            ("extra-field", {**base_case, "unexpected": True}, "fields"),
        )
        for name, case, expected_error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cases_path = root / "cases.json"
                cases_path.write_text(
                    json.dumps({"schema_version": 2, "cases": [case]}),
                    encoding="utf-8",
                )
                output = root / "results"

                rejected = self.run_runner(
                    "--cases",
                    str(cases_path),
                    "--output",
                    str(output),
                    expected_returncode=2,
                )

                self.assertIn(expected_error, rejected.stderr)
                self.assertFalse((root / "escape-r01.json").exists())

    def test_agent_command_interface_requires_both_placeholders(self) -> None:
        invalid = self.run_runner(
            "--agent-command",
            "python host.py",
            "--validate-agent-command",
            expected_returncode=2,
        )
        self.assertIn("{case_json}", invalid.stderr)
        valid = self.run_runner(
            "--agent-command",
            'python host.py --case "{case_json}" --output "{candidate_dir}"',
            "--validate-agent-command",
        )
        self.assertEqual(json.loads(valid.stdout)["valid"], True)

    def test_real_host_environment_is_sanitized_and_declared_unsandboxed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "environment_host.py"
            host.write_text(
                textwrap.dedent(
                    """
                    import argparse
                    import json
                    import os
                    from pathlib import Path

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--case", required=True)
                    parser.add_argument("--output", required=True)
                    args = parser.parse_args()
                    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
                    print(json.dumps({
                        "secret_present": "STORM_FORWARD_EVAL_SECRET" in os.environ,
                        "case_fields": sorted(case),
                    }))
                    """
                ),
                encoding="utf-8",
            )
            command = (
                f'{sys.executable} {host} --case "{{case_json}}" '
                '--output "{candidate_dir}"'
            )
            output = root / "results"
            with mock.patch.dict(
                os.environ, {"STORM_FORWARD_EVAL_SECRET": "must-not-propagate"}
            ):
                summary = json.loads(
                    self.run_runner(
                        "--cases",
                        str(CASES),
                        "--output",
                        str(output),
                        "--case-id",
                        "artifact-defaults",
                        "--agent-command",
                        command,
                        expected_returncode=1,
                    ).stdout
                )

            trace = json.loads(
                (output / "traces" / "artifact-defaults-r01.json").read_text(
                    encoding="utf-8"
                )
            )
            host_stdout = json.loads(trace["adapter_result"]["stdout"])
            self.assertFalse(host_stdout["secret_present"])
            self.assertEqual(
                host_stdout["case_fields"],
                ["category", "description", "id", "prompt"],
            )
            self.assertFalse(summary["external_side_effects_network_sandbox_verified"])


if __name__ == "__main__":
    unittest.main()
