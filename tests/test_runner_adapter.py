from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "storm" / "scripts"
ADAPTER_CLI = SCRIPTS / "runner_adapter.py"
STATE_CLI = SCRIPTS / "storm_state.py"
ARTIFACT_CLI = SCRIPTS / "validate_artifacts.py"
CITATION_CLI = SCRIPTS / "audit_citations.py"
FIXTURE = ROOT / "tests" / "fixtures" / "knowledge-storm-v1.1"


class RunnerAdapterTests(unittest.TestCase):
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

    def init_run(
        self,
        output: Path,
        *,
        mode: str = "classic",
        execution_backend: str = "local-runner",
    ) -> dict[str, object]:
        return json.loads(
            self.run_python(
                STATE_CLI,
                "init",
                "--mode",
                mode,
                "--topic",
                "Test Topic",
                "--output",
                str(output),
                "--execution-backend",
                execution_backend,
            ).stdout
        )

    def state(self, output: Path, command: str = "status", *args: str) -> dict[str, object]:
        return json.loads(
            self.run_python(
                STATE_CLI,
                command,
                "--run",
                str(self.run_path(output)),
                *args,
            ).stdout
        )

    def sync(
        self,
        output: Path,
        source: Path = FIXTURE,
        *,
        runner_version: str = "1.1.1",
        expected_returncode: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_python(
            ADAPTER_CLI,
            "sync",
            "--run",
            str(self.run_path(output)),
            "--source",
            str(source),
            "--runner-version",
            runner_version,
            "--retriever",
            "fixture-retriever",
            "--retriever-version",
            "fixture-1",
            "--search-top-k",
            "3",
            "--exit-status",
            "0",
            expected_returncode=expected_returncode,
        )

    def sync_and_advance_until(self, output: Path, source: Path, target_action: str) -> None:
        while True:
            state = self.state(output)
            if state["next_action"] == target_action:
                return
            report = json.loads(self.sync(output, source).stdout)
            event = report["suggested_event"]
            self.assertIsInstance(event, str)
            self.state(output, "advance", "--event", event)

    def test_probe_uses_distribution_metadata_without_importing_the_runner(self) -> None:
        adapter = self.load_adapter_module()
        with mock.patch.object(
            adapter.metadata,
            "version",
            side_effect=importlib.metadata.PackageNotFoundError("knowledge-storm"),
        ):
            missing = adapter.probe_dependency()
        self.assertFalse(missing["available"])
        self.assertFalse(missing["installed"])
        self.assertFalse(missing["supported"])
        self.assertIsNone(missing["version"])
        self.assertFalse(missing["automatic_install"])
        self.assertIn("knowledge-storm", missing["requirement"])
        self.assertIn("stable releases", missing["requirement"])

        with mock.patch.object(adapter.metadata, "version", return_value="1.1.1"):
            available = adapter.probe_dependency()
        self.assertTrue(available["available"])
        self.assertTrue(available["installed"])
        self.assertTrue(available["supported"])
        self.assertEqual(available["version"], "1.1.1")
        self.assertEqual(available["version_source"], "distribution-metadata")

        with mock.patch.object(adapter.metadata, "version", return_value="2.0.0"):
            incompatible = adapter.probe_dependency()
        self.assertTrue(incompatible["installed"])
        self.assertFalse(incompatible["supported"])
        self.assertFalse(incompatible["available"])

    def test_claim_candidates_cover_repeated_and_joint_citation_paragraphs(self) -> None:
        adapter = self.load_adapter_module()
        report = adapter.claims_from_article(
            "# Topic\n\nFirst fact [1].\n\nSecond fact [1].\n\nJoint fact [1][2].",
            {1, 2},
        )

        self.assertEqual(
            [claim["claim"] for claim in report["claims"]],
            ["First fact.", "Second fact.", "Joint fact."],
        )
        self.assertEqual(report["claims"][0]["citation_ids"], [1])
        self.assertEqual(report["claims"][1]["citation_ids"], [1])
        self.assertEqual(report["claims"][2]["citation_ids"], [1, 2])
        self.assertEqual(report["claims"][2]["source_ids"], [1, 2])

    def test_fixed_official_fixture_maps_phase_by_phase_and_reaches_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            state = self.init_run(output)
            while state["phase"] != "COMPLETE":
                before_run = self.run_path(output).read_bytes()
                event_log = output / ".storm-run" / "event-log.jsonl"
                before_events = event_log.read_bytes()
                report = json.loads(self.sync(output).stdout)
                self.assertEqual(before_run, self.run_path(output).read_bytes())
                self.assertEqual(before_events, event_log.read_bytes())
                self.assertEqual(report["next_action"], state["next_action"])

                if state["next_action"] == "verify_artifacts":
                    control = output / ".storm-run"
                    rejected = self.run_python(
                        CITATION_CLI,
                        "--article",
                        str(control / "staging" / "storm_gen_article_polished.html"),
                        "--sources",
                        str(control / "sources.json"),
                        "--claims",
                        str(control / "claim-support-candidates.json"),
                        "--run",
                        str(self.run_path(output)),
                        "--staging",
                        expected_returncode=1,
                    )
                    self.assertFalse(json.loads(rejected.stdout)["valid"])
                    candidates = json.loads(
                        (control / "claim-support-candidates.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        {claim["claim"] for claim in candidates["claims"]},
                        {
                            "Polished citation mapping is verified independently.",
                            "Deterministic runner evidence remains traceable.",
                        },
                    )
                    for claim in candidates["claims"]:
                        claim["support_status"] = "supported"
                        claim["evidence_note"] = "Fixture evidence was reviewed against the mapped source."
                        claim["action"] = "keep"
                    (control / "claim-support.json").write_text(
                        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    audited = self.run_python(
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
                    )
                    self.assertTrue(json.loads(audited.stdout)["valid"])
                    validated = self.run_python(
                        ARTIFACT_CLI,
                        str(output),
                        "--topic",
                        "Test Topic",
                        "--run",
                        str(self.run_path(output)),
                        "--staging",
                    )
                    self.assertTrue(json.loads(validated.stdout)["valid"])
                    state = self.state(output, "advance", "--event", "verified")
                elif state["next_action"] == "publish":
                    self.assertEqual(report["suggested_event"], "completed")
                    state = self.state(output, "advance", "--event", "completed")
                else:
                    self.assertIsInstance(report["suggested_event"], str)
                    state = self.state(
                        output, "advance", "--event", report["suggested_event"]
                    )

            self.assertEqual(state["status"], "complete")
            self.assertEqual(state["execution_backend"], "local-runner")
            self.assertEqual(
                {path.name for path in output.iterdir() if path.is_file()},
                {
                    "direct_gen_outline.html",
                    "storm_gen_outline.html",
                    "storm_gen_article.html",
                    "storm_gen_article_polished.html",
                },
            )
            control = output / ".storm-run"
            manifest_text = (control / "runner-manifest.json").read_text(encoding="utf-8")
            for secret in (
                "TOP-SECRET-API-KEY",
                "TOP-SECRET-RETRIEVER-TOKEN",
                "TOP-SECRET-PROMPT",
                "TOP-SECRET-RESPONSE",
                "https://private.example.invalid",
                "untrusted-config-name",
            ):
                self.assertNotIn(secret, manifest_text)
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["runner_version"], "1.1.1")
            self.assertEqual(manifest["runner_version_source"], "explicit")
            self.assertIn(
                {"path": "conv_simulator_lm.max_tokens", "value": 2048},
                manifest["model_configuration"],
            )
            self.assertEqual(manifest["retriever"]["name"], "fixture-retriever")
            self.assertEqual(manifest["retriever"]["top_k"], 3)
            self.assertEqual(manifest["lm_history"]["line_count"], 1)
            self.assertEqual(len(manifest["lm_history"]["sha256"]), 64)
            self.assertGreaterEqual(manifest["redacted_field_count"], 3)
            self.assertTrue(manifest["workflow_traceable"])
            self.assertFalse(manifest["generated_content_reproducible"])

            draft_html = (output / "storm_gen_article.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>", draft_html)
            self.assertIn("&lt;script&gt;", draft_html)
            sources = json.loads((control / "sources.json").read_text(encoding="utf-8"))
            self.assertEqual(len(sources["sources"]), 2)
            self.assertEqual(sources["sources"][0]["title"], "Citation mapping contract")
            self.assertEqual(sources["sources"][1]["title"], "Runner output contract")
            self.assertNotIn("unused-after-polish", json.dumps(sources))
            interviews = [
                json.loads(line)
                for line in (control / "interviews.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(all(query.strip() for row in interviews for query in row["queries"]))
            self.assertEqual(
                interviews[0]["question"],
                "How is deterministic runner evidence captured?",
            )
            self.assertEqual(
                interviews[0]["answer"],
                "The official runner keeps structured conversation and search outputs.",
            )
            information_rows = [
                json.loads(line)
                for line in (control / "information-table.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                information_rows[0]["claim_supported"],
                "The official runner keeps structured conversation and search outputs.",
            )

    def test_adapter_rejects_wrong_mode_or_execution_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guarded = root / "guarded"
            self.init_run(guarded, execution_backend="guarded-agent")
            rejected = self.sync(guarded, expected_returncode=2)
            self.assertIn("execution_backend=local-runner", rejected.stderr)

            co_storm = root / "co-storm"
            self.init_run(co_storm, mode="co-storm")
            rejected = self.sync(co_storm, expected_returncode=2)
            self.assertIn("Classic STORM", rejected.stderr)

            for version in ("1.1.0", "1.1.1garbage", "2.0.0"):
                with self.subTest(version=version):
                    unsupported = root / f"unsupported-version-{version}"
                    self.init_run(unsupported)
                    rejected = self.sync(
                        unsupported, runner_version=version, expected_returncode=2
                    )
                    self.assertIn("expected >=1.1.1,<1.2", rejected.stderr)

            nested = root / "nested-source"
            self.init_run(nested)
            nested_source = nested / "private-official"
            shutil.copytree(FIXTURE, nested_source)
            rejected = self.sync(nested, nested_source, expected_returncode=2)
            self.assertIn("must not overlap the guarded output tree", rejected.stderr)

            ancestor_source = root / "ancestor-source"
            shutil.copytree(FIXTURE, ancestor_source)
            ancestor_run = ancestor_source / "guarded-run"
            self.init_run(ancestor_run)
            rejected = self.sync(ancestor_run, ancestor_source, expected_returncode=2)
            self.assertIn("must not overlap the guarded output tree", rejected.stderr)

    def test_polished_reference_map_is_required_and_draft_map_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(FIXTURE, source)
            (source / "polished_url_to_info.json").unlink()
            output = root / "run"
            self.init_run(output)
            self.sync_and_advance_until(output, source, "polish_article")
            before_run = self.run_path(output).read_bytes()
            rejected = self.sync(output, source, expected_returncode=2)
            self.assertIn("polished_url_to_info.json", rejected.stderr)
            self.assertEqual(before_run, self.run_path(output).read_bytes())
            self.assertFalse(
                (output / ".storm-run" / "staging" / "storm_gen_article_polished.html").exists()
            )

    def test_conflicting_outputs_invalid_utf8_and_blank_queries_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "conflict"
            self.init_run(output)
            self.sync(output)
            manifest = output / ".storm-run" / "runner-manifest.json"
            manifest.write_text("tampered\n", encoding="utf-8")
            before_events = (output / ".storm-run" / "event-log.jsonl").read_bytes()
            rejected = self.sync(output, expected_returncode=2)
            self.assertIn("conflicts with existing adapter output", rejected.stderr)
            self.assertEqual(
                before_events, (output / ".storm-run" / "event-log.jsonl").read_bytes()
            )

            changed_source = root / "changed-source"
            shutil.copytree(FIXTURE, changed_source)
            changed_run = root / "changed-run"
            self.init_run(changed_run)
            first = json.loads(self.sync(changed_run, changed_source).stdout)
            self.state(changed_run, "advance", "--event", first["suggested_event"])
            (changed_source / "direct_gen_outline.txt").write_text(
                "# Changed\n", encoding="utf-8"
            )
            rejected = self.sync(changed_run, changed_source, expected_returncode=2)
            self.assertIn("source changed after manifest capture", rejected.stderr)

            bad_utf8_source = root / "bad-utf8-source"
            shutil.copytree(FIXTURE, bad_utf8_source)
            (bad_utf8_source / "conversation_log.json").write_bytes(b"\xff\xfe")
            bad_utf8_run = root / "bad-utf8-run"
            self.init_run(bad_utf8_run)
            first = json.loads(self.sync(bad_utf8_run, bad_utf8_source).stdout)
            self.state(bad_utf8_run, "advance", "--event", first["suggested_event"])
            rejected = self.sync(bad_utf8_run, bad_utf8_source, expected_returncode=2)
            self.assertIn("strict UTF-8", rejected.stderr)

            blank_source = root / "blank-query-source"
            shutil.copytree(FIXTURE, blank_source)
            conversation_path = blank_source / "conversation_log.json"
            conversation = json.loads(conversation_path.read_text(encoding="utf-8"))
            conversation[0]["dlg_turns"][0]["search_queries"] = ["", "  "]
            conversation_path.write_text(
                json.dumps(conversation, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            blank_run = root / "blank-query-run"
            self.init_run(blank_run)
            self.sync_and_advance_until(blank_run, blank_source, "run_interviews")
            rejected = self.sync(blank_run, blank_source, expected_returncode=2)
            self.assertIn("non-empty search query", rejected.stderr)

    @staticmethod
    def run_path(output: Path) -> Path:
        return output / ".storm-run" / "run.json"

    @staticmethod
    def load_adapter_module():
        spec = importlib.util.spec_from_file_location("runner_adapter_under_test", ADAPTER_CLI)
        if spec is None or spec.loader is None:
            raise AssertionError("unable to load runner adapter")
        module = importlib.util.module_from_spec(spec)
        script_path = str(SCRIPTS)
        inserted = script_path not in sys.path
        if inserted:
            sys.path.insert(0, script_path)
        try:
            spec.loader.exec_module(module)
        finally:
            if inserted:
                sys.path.remove(script_path)
        return module


if __name__ == "__main__":
    unittest.main()
