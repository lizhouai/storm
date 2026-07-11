import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "storm" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_artifacts import validate_artifacts


ARTIFACT_NAMES = (
    "direct_gen_outline.html",
    "storm_gen_outline.html",
    "storm_gen_article.html",
    "storm_gen_article_polished.html",
)


class ArtifactValidationTests(unittest.TestCase):
    def test_valid_bundle_returns_sha256_for_each_public_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            self._write_valid_bundle(output_dir)

            report = validate_artifacts(output_dir)

            self.assertTrue(report["valid"])
            self.assertEqual(set(report["artifacts"]), set(ARTIFACT_NAMES))
            for name in ARTIFACT_NAMES:
                expected = hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
                self.assertEqual(report["artifacts"][name]["sha256"], expected)

    def test_bundle_membership_must_be_exactly_the_four_html_artifacts(self):
        cases = ("missing", "wrong-format", "extra-public-file")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                self._write_valid_bundle(output_dir)
                if case == "missing":
                    (output_dir / ARTIFACT_NAMES[0]).unlink()
                elif case == "wrong-format":
                    path = output_dir / ARTIFACT_NAMES[0]
                    path.rename(path.with_suffix(".md"))
                else:
                    (output_dir / "notes.html").write_text("extra", encoding="utf-8")

                report = validate_artifacts(output_dir)

                self.assertFalse(report["valid"])
                self.assertTrue(report["errors"])

    def test_text_artifacts_reject_bad_encoding_empty_mojibake_and_truncation(self):
        cases = {
            "non-utf8": b"\xff\xfe",
            "empty": b"",
            "replacement-character": self._html(
                "Draft", "<h1>Methods</h1><p>Broken \ufffd text.</p>"
            ).encode("utf-8"),
            "known-mojibake": self._html(
                "Draft", "<h1>Methods</h1><p>It\u00e2\u20ac\u2122s broken.</p>"
            ).encode("utf-8"),
            "truncated": self._html(
                "Draft", "<h1>Methods</h1><p>[TRUNCATED]</p>"
            ).encode("utf-8"),
        }
        for case, raw in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                self._write_valid_bundle(output_dir)
                (output_dir / "storm_gen_article.html").write_bytes(raw)

                report = validate_artifacts(output_dir)

                self.assertFalse(report["valid"])

    def test_html_requires_charset_title_balanced_structure_and_static_content(self):
        cases = {
            "missing-charset": (
                "<!doctype html><html><head><title>Draft</title></head>"
                "<body><h1>Methods</h1></body></html>"
            ),
            "placeholder-title": self._html(
                "Untitled", "<h1>Methods</h1><p>Claim.</p>"
            ),
            "missing-body": (
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                "<title>Draft</title></head></html>"
            ),
            "unbalanced": (
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                "<title>Draft</title></head><body><h1>Methods</h1>"
            ),
            "script": self._html(
                "Draft", "<h1>Methods</h1><script>alert(1)</script>"
            ),
            "event-handler": self._html(
                "Draft", "<h1 onclick=\"alert(1)\">Methods</h1>"
            ),
            "unsafe-url": self._html(
                "Draft", "<h1>Methods</h1><a href=\"javascript:alert(1)\">x</a>"
            ),
        }
        for case, content in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                self._write_valid_bundle(output_dir)
                (output_dir / "storm_gen_article.html").write_text(
                    content, encoding="utf-8"
                )

                report = validate_artifacts(output_dir)

                self.assertFalse(report["valid"])

    def test_heading_gates_reject_invalid_outlines_and_missing_references(self):
        cases = (
            ("starts-at-h2", "direct_gen_outline.html", "<h2>Methods</h2>", None),
            (
                "skips-level",
                "direct_gen_outline.html",
                "<h1>Scope</h1><h3>Methods</h3>",
                None,
            ),
            ("h4", "direct_gen_outline.html", "<h1>Scope</h1><h4>Detail</h4>", None),
            (
                "outline-references",
                "storm_gen_outline.html",
                "<h1>Scope</h1><h1>References</h1>",
                None,
            ),
            (
                "outline-topic",
                "storm_gen_outline.html",
                "<h1>RAG evaluation</h1><h2>Methods</h2>",
                "RAG evaluation",
            ),
            (
                "polished-no-references",
                "storm_gen_article_polished.html",
                "<h1>Methods</h1><p>Claim.</p>",
                None,
            ),
            (
                "polished-empty-references",
                "storm_gen_article_polished.html",
                "<h1>Methods</h1><p>Claim.</p><h1>References</h1>",
                None,
            ),
        )
        for case, filename, body, topic in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                self._write_valid_bundle(output_dir)
                (output_dir / filename).write_text(
                    self._html("Artifact", body), encoding="utf-8"
                )

                report = validate_artifacts(output_dir, topic=topic)

                self.assertFalse(report["valid"])

    def test_valid_hashes_are_merged_atomically_into_in_scope_run_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            self._write_valid_bundle(output_dir)
            control_dir = output_dir / ".storm-run"
            control_dir.mkdir()
            run_path = control_dir / "run.json"
            original = {
                "topic": "RAG evaluation",
                "artifacts": {"existing": {"preserved": True}},
                "metrics": {"events": 1},
            }
            run_path.write_text(json.dumps(original), encoding="utf-8")

            report = validate_artifacts(output_dir, run_path=run_path)

            self.assertTrue(report["valid"])
            updated = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["metrics"], original["metrics"])
            self.assertEqual(updated["artifacts"]["existing"], {"preserved": True})
            for name in ARTIFACT_NAMES:
                self.assertEqual(
                    updated["artifacts"][name]["sha256"],
                    report["artifacts"][name]["sha256"],
                )
                self.assertEqual(updated["artifacts"][name]["path"], name)
            self.assertEqual(list(control_dir.glob("*.tmp")), [])

    def test_run_state_update_rejects_out_of_scope_or_malformed_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            output_dir = workspace / "output"
            output_dir.mkdir()
            self._write_valid_bundle(output_dir)
            outside_run = workspace / "run.json"
            outside_run.write_text('{"artifacts": {}}', encoding="utf-8")

            outside_report = validate_artifacts(output_dir, run_path=outside_run)

            self.assertFalse(outside_report["valid"])
            self.assertEqual(outside_run.read_text(encoding="utf-8"), '{"artifacts": {}}')

            control_dir = output_dir / ".storm-run"
            control_dir.mkdir()
            malformed_run = control_dir / "run.json"
            malformed_run.write_text("not json", encoding="utf-8")

            malformed_report = validate_artifacts(output_dir, run_path=malformed_run)

            self.assertFalse(malformed_report["valid"])
            self.assertEqual(malformed_run.read_text(encoding="utf-8"), "not json")

    def test_cli_emits_json_and_uses_failure_exit_status_for_invalid_bundle(self):
        script = SCRIPTS_DIR / "validate_artifacts.py"
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            self._write_valid_bundle(output_dir)

            valid = subprocess.run(
                [sys.executable, str(script), str(output_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertTrue(json.loads(valid.stdout)["valid"])

            (output_dir / ARTIFACT_NAMES[0]).unlink()
            invalid = subprocess.run(
                [sys.executable, str(script), str(output_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(invalid.returncode, 1, invalid.stderr)
            self.assertFalse(json.loads(invalid.stdout)["valid"])

    def _write_valid_bundle(self, output_dir):
        outline = self._html("Outline", "<h1>Scope</h1><h2>Methods</h2>")
        article = self._html("Draft", "<h1>Methods</h1><p>Claim [1].</p>")
        polished = self._html(
            "Polished",
            "<h1>Methods</h1><p>Claim [1].</p>"
            "<h1>References</h1><ol><li>Source one</li></ol>",
        )
        contents = (outline, outline, article, polished)
        for name, content in zip(ARTIFACT_NAMES, contents):
            (output_dir / name).write_text(content, encoding="utf-8")

    @staticmethod
    def _html(title, body):
        return (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body>{body}</body></html>"
        )


if __name__ == "__main__":
    unittest.main()
