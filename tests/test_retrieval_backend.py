from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_CLI = ROOT / "skills" / "storm" / "scripts" / "retrieval_backend.py"
STATE_CLI = ROOT / "skills" / "storm" / "scripts" / "storm_state.py"
FIXTURES = ROOT / "tests" / "fixtures" / "retrieval"
CLASSIC_FIXTURES = ROOT / "tests" / "fixtures" / "classic-run"
CORPUS = FIXTURES / "corpus.jsonl"
HOST_RESULTS = FIXTURES / "host-results.jsonl"


class RetrievalBackendTests(unittest.TestCase):
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
            msg=f"command: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def run_cli(
        self, *args: str, expected_returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        return self.run_python(
            RETRIEVAL_CLI, *args, expected_returncode=expected_returncode
        )

    def build_index(
        self,
        directory: Path,
        *,
        backend: str = "lexical",
        extra_args: tuple[str, ...] = (),
    ) -> tuple[Path, dict[str, object]]:
        index_path = directory / f"{backend}-index.json"
        result = self.run_cli(
            "index",
            "--backend",
            backend,
            "--corpus",
            str(CORPUS),
            "--output",
            str(index_path),
            "--chunk-size",
            "500",
            "--chunk-overlap",
            "0",
            *extra_args,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report, json.loads(index_path.read_text(encoding="utf-8")))
        return index_path, report

    def test_lexical_top_k_and_trace_are_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path, index = self.build_index(root)
            self.assertEqual(index["backend_requested"], "lexical")
            self.assertEqual(index["backend_used"], "lexical")
            self.assertEqual(index["algorithm"], "bm25-unicode-v1")

            reports = []
            traces = []
            query = "citation audit unsupported claims retrieval"
            for attempt in (1, 2):
                trace_path = root / f"retrieval-{attempt}.jsonl"
                result = self.run_cli(
                    "search",
                    "--index",
                    str(index_path),
                    "--query",
                    query,
                    "--top-k",
                    "2",
                    "--trace",
                    str(trace_path),
                )
                reports.append(json.loads(result.stdout))
                traces.append(
                    [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
                )

            self.assertEqual(reports[0], reports[1])
            self.assertEqual(traces[0], traces[1])
            self.assertEqual(reports[0]["results"][0]["source_id"], "S2")
            self.assertEqual(reports[0]["backend_used"], "lexical")
            self.assertEqual(reports[0]["top_k"], 2)
            self.assertEqual(reports[0]["chunking"], {"size": 500, "overlap": 0})
            self.assertEqual(len(traces[0]), 2)
            self.assertEqual(traces[0][0]["rank"], 1)
            self.assertEqual(traces[0][0]["query"], query)
            self.assertEqual(traces[0][0]["algorithm"], "bm25-unicode-v1")
            self.assertEqual(len(traces[0][0]["snippet_hash"]), 64)
            self.assertIsInstance(traces[0][0]["score"], float)

    def test_lexical_backend_handles_chinese_without_an_english_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path, _ = self.build_index(root)
            result = self.run_cli(
                "search",
                "--index",
                str(index_path),
                "--query",
                "中文检索 查询参数",
                "--top-k",
                "1",
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["results"][0]["source_id"], "S3")

    def test_dynamic_embedding_provider_surface_is_not_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rejected_backend = self.run_cli(
                "index",
                "--backend",
                "embedding",
                "--corpus",
                str(CORPUS),
                "--output",
                str(root / "embedding.json"),
                expected_returncode=2,
            )
            self.assertIn("invalid choice", rejected_backend.stderr)

            index_path, _ = self.build_index(root)
            rejected_provider = self.run_cli(
                "search",
                "--index",
                str(index_path),
                "--query",
                "citation audit",
                "--embedding-provider",
                "untrusted.py:embed",
                expected_returncode=2,
            )
            self.assertIn("unrecognized arguments", rejected_provider.stderr)

    def test_tampered_index_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path, index = self.build_index(root)
            index["chunks"][0]["snippet_hash"] = "0" * 64
            index_path.write_text(
                json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            rejected = self.run_cli(
                "search",
                "--index",
                str(index_path),
                "--query",
                "retrieval",
                expected_returncode=2,
            )
            self.assertIn("snippet hash is invalid", rejected.stderr)

    def test_host_backend_requires_and_records_explicit_ranked_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path, _ = self.build_index(root, backend="host")
            rejected = self.run_cli(
                "search",
                "--index",
                str(index_path),
                "--query",
                "host semantic selection",
                expected_returncode=2,
            )
            self.assertIn("host backend requires --host-results", rejected.stderr)

            result = self.run_cli(
                "search",
                "--index",
                str(index_path),
                "--query",
                "host semantic selection",
                "--top-k",
                "2",
                "--host-results",
                str(HOST_RESULTS),
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["backend_used"], "host")
            self.assertEqual(report["algorithm"], "host-ranked-passthrough-v1")
            self.assertEqual(
                [result["source_id"] for result in report["results"]],
                ["S3", "S1"],
            )

            multi_chunk_index = root / "host-multi-chunk.json"
            self.run_cli(
                "index",
                "--backend",
                "host",
                "--corpus",
                str(CORPUS),
                "--output",
                str(multi_chunk_index),
                "--chunk-size",
                "32",
                "--chunk-overlap",
                "0",
            )
            rejected = self.run_cli(
                "search",
                "--index",
                str(multi_chunk_index),
                "--query",
                "host semantic selection",
                "--host-results",
                str(HOST_RESULTS),
                expected_returncode=2,
            )
            self.assertIn("must include chunk_id for a multi-chunk source", rejected.stderr)

    def test_index_and_search_outputs_require_explicit_replace_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path, original = self.build_index(root)
            rejected = self.run_cli(
                "index",
                "--backend",
                "host",
                "--corpus",
                str(CORPUS),
                "--output",
                str(index_path),
                expected_returncode=2,
            )
            self.assertIn("already exists", rejected.stderr)
            self.assertEqual(original, json.loads(index_path.read_text(encoding="utf-8")))
            replaced = self.run_cli(
                "index",
                "--backend",
                "host",
                "--corpus",
                str(CORPUS),
                "--output",
                str(index_path),
                "--replace",
            )
            self.assertEqual(json.loads(replaced.stdout)["backend_used"], "host")

            search_root = root / "search-case"
            search_root.mkdir()
            lexical_path, _ = self.build_index(search_root, backend="lexical")
            report_path = root / "search.json"
            self.run_cli(
                "search",
                "--index",
                str(lexical_path),
                "--query",
                "retrieval",
                "--output",
                str(report_path),
            )
            before = report_path.read_bytes()
            rejected = self.run_cli(
                "search",
                "--index",
                str(lexical_path),
                "--query",
                "citation audit",
                "--output",
                str(report_path),
                expected_returncode=2,
            )
            self.assertIn("already exists", rejected.stderr)
            self.assertEqual(before, report_path.read_bytes())
            self.run_cli(
                "search",
                "--index",
                str(lexical_path),
                "--query",
                "citation audit",
                "--output",
                str(report_path),
                "--replace-output",
            )
            self.assertNotEqual(before, report_path.read_bytes())

    def test_rich_retrieval_trace_satisfies_the_existing_guarded_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "run"
            run_path = output / ".storm-run" / "run.json"
            control = run_path.parent
            self.run_python(
                STATE_CLI,
                "init",
                "--mode",
                "classic",
                "--topic",
                "Retrieval fixture",
                "--output",
                str(output),
            )
            self.run_python(
                STATE_CLI, "advance", "--run", str(run_path), "--event", "scope_defined"
            )
            shutil.copyfile(CLASSIC_FIXTURES / "perspectives.json", control / "perspectives.json")
            self.run_python(
                STATE_CLI,
                "advance",
                "--run",
                str(run_path),
                "--event",
                "perspectives_ready",
            )

            index_path, _ = self.build_index(root)
            trace_path = control / "retrieval-log.jsonl"
            for query in (
                "deterministic retrieval fixed evidence",
                "citation audit unsupported claims",
            ):
                self.run_cli(
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
            shutil.copyfile(CLASSIC_FIXTURES / "interviews.jsonl", control / "interviews.jsonl")

            advanced = self.run_python(
                STATE_CLI,
                "advance",
                "--run",
                str(run_path),
                "--event",
                "interviews_completed",
            )
            state = json.loads(advanced.stdout)
            self.assertEqual(state["phase"], "INTERVIEWS_COMPLETE")
            trace_rows = [
                json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([row["source_id"] for row in trace_rows], ["S1", "S2"])
            self.assertTrue(all(row["backend_used"] == "lexical" for row in trace_rows))


if __name__ == "__main__":
    unittest.main()
