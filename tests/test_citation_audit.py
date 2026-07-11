import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "storm" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from audit_citations import audit_citations


class CitationAuditTests(unittest.TestCase):
    def test_supported_mapped_citations_produce_persisted_valid_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir, article_path, sources_path, claims_path = self._valid_inputs(
                Path(directory)
            )

            report = audit_citations(article_path, sources_path, claims_path)

            self.assertTrue(report["valid"])
            self.assertEqual(report["used_citation_ids"], [1, 2])
            audit_path = output_dir / ".storm-run" / "citation-audit.json"
            self.assertTrue(audit_path.is_file())
            persisted = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted, report)
            self.assertEqual(persisted["claims"][0]["support_status"], "supported")
            self.assertEqual(persisted["claims"][0]["evidence_note"], "Direct support")
            self.assertEqual(persisted["claims"][0]["action"], "keep")

    def test_source_ids_and_article_mappings_fail_closed(self):
        cases = ("duplicate", "nonconsecutive", "nonpositive", "out-of-range", "dangling")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                output_dir, article_path, sources_path, claims_path = self._valid_inputs(
                    Path(directory)
                )
                sources = json.loads(sources_path.read_text(encoding="utf-8"))
                if case == "duplicate":
                    sources["sources"][1]["id"] = 1
                elif case == "nonconsecutive":
                    sources["sources"][1]["id"] = 3
                    article_path.write_text("Claims [1][3].", encoding="utf-8")
                elif case == "nonpositive":
                    sources["sources"][0]["id"] = 0
                    article_path.write_text("Claims [0][2].", encoding="utf-8")
                elif case == "out-of-range":
                    article_path.write_text("Claims [1][3].", encoding="utf-8")
                else:
                    sources["sources"].append(
                        {"id": 3, "title": "Source three", "url": "https://example.com/3"}
                    )
                sources_path.write_text(json.dumps(sources), encoding="utf-8")

                report = audit_citations(article_path, sources_path, claims_path)

                self.assertFalse(report["valid"])
                self.assertTrue(report["errors"])
                persisted = json.loads(
                    (output_dir / ".storm-run" / "citation-audit.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(persisted, report)

    def test_explicit_unused_evidence_is_not_a_dangling_source(self):
        with tempfile.TemporaryDirectory() as directory:
            _, article_path, sources_path, claims_path = self._valid_inputs(Path(directory))
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
            sources["sources"].append(
                {
                    "id": 3,
                    "title": "Unused source",
                    "url": "https://example.com/3",
                    "unused_evidence": True,
                }
            )
            sources_path.write_text(json.dumps(sources), encoding="utf-8")

            report = audit_citations(article_path, sources_path, claims_path)

            self.assertTrue(report["valid"], report["errors"])

    def test_claim_support_decisions_fail_closed_when_incomplete_or_unsupported(self):
        cases = (
            "missing-claim",
            "missing-citations",
            "duplicate-citations",
            "mismatched-source-ids",
            "missing-evidence",
            "missing-action",
            "unsupported",
            "partial",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                output_dir, article_path, sources_path, claims_path = self._valid_inputs(
                    Path(directory)
                )
                document = json.loads(claims_path.read_text(encoding="utf-8"))
                if case == "missing-claim":
                    document["claims"].pop()
                elif case == "missing-citations":
                    document["claims"][0]["citation_ids"] = []
                elif case == "duplicate-citations":
                    document["claims"][0]["citation_ids"] = [1, 1]
                elif case == "mismatched-source-ids":
                    document["claims"][0]["source_ids"] = [2]
                elif case == "missing-evidence":
                    document["claims"][0]["evidence_note"] = ""
                elif case == "missing-action":
                    document["claims"][0]["action"] = ""
                elif case == "unsupported":
                    document["claims"][0]["support_status"] = "unsupported"
                else:
                    document["claims"][0]["support_status"] = "partial"
                    document["claims"][0]["action"] = "qualify"
                claims_path.write_text(json.dumps(document), encoding="utf-8")

                report = audit_citations(article_path, sources_path, claims_path)

                self.assertFalse(report["valid"])
                self.assertTrue(report["errors"])
                self.assertEqual(
                    json.loads(
                        (output_dir / ".storm-run" / "citation-audit.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    report,
                )

    def test_invalid_inputs_and_path_escapes_fail_closed(self):
        cases = ("bad-json", "missing-file", "non-utf8-article", "outside-sources")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                output_dir, article_path, sources_path, claims_path = self._valid_inputs(
                    workspace / "output"
                )
                if case == "bad-json":
                    sources_path.write_text("not json", encoding="utf-8")
                elif case == "missing-file":
                    claims_path.unlink()
                elif case == "non-utf8-article":
                    article_path.write_bytes(b"\xff\xfe")
                else:
                    outside = workspace / "sources.json"
                    outside.write_bytes(sources_path.read_bytes())
                    sources_path = outside

                report = audit_citations(article_path, sources_path, claims_path)

                self.assertFalse(report["valid"])
                self.assertTrue(report["errors"])
                audit_path = output_dir / ".storm-run" / "citation-audit.json"
                self.assertEqual(
                    json.loads(audit_path.read_text(encoding="utf-8")), report
                )
                self.assertEqual(list(audit_path.parent.glob("*.tmp")), [])

    def test_audit_output_cannot_escape_the_control_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            _, article_path, sources_path, claims_path = self._valid_inputs(
                workspace / "output"
            )
            outside_audit = workspace / "citation-audit.json"

            report = audit_citations(
                article_path,
                sources_path,
                claims_path,
                output_path=outside_audit,
            )

            self.assertFalse(report["valid"])
            self.assertFalse(outside_audit.exists())

    def test_cli_emits_json_and_fails_closed_for_unsupported_claims(self):
        script = SCRIPTS_DIR / "audit_citations.py"
        with tempfile.TemporaryDirectory() as directory:
            _, article_path, sources_path, claims_path = self._valid_inputs(Path(directory))
            command = [
                sys.executable,
                str(script),
                "--article",
                str(article_path),
                "--sources",
                str(sources_path),
                "--claims",
                str(claims_path),
            ]

            valid = subprocess.run(command, text=True, capture_output=True, check=False)

            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertTrue(json.loads(valid.stdout)["valid"])

            document = json.loads(claims_path.read_text(encoding="utf-8"))
            document["claims"][0]["support_status"] = "unsupported"
            claims_path.write_text(json.dumps(document), encoding="utf-8")
            invalid = subprocess.run(command, text=True, capture_output=True, check=False)

            self.assertEqual(invalid.returncode, 1, invalid.stderr)
            self.assertFalse(json.loads(invalid.stdout)["valid"])

    def test_only_visible_article_text_counts_as_citation_use(self):
        with tempfile.TemporaryDirectory() as directory:
            _, article_path, sources_path, claims_path = self._valid_inputs(Path(directory))
            article_path.write_text(
                '<p data-note="[2]">Visible claim [1].</p><!-- hidden [2] -->',
                encoding="utf-8",
            )
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
            sources["sources"][1]["unused_evidence"] = True
            sources_path.write_text(json.dumps(sources), encoding="utf-8")
            claims = json.loads(claims_path.read_text(encoding="utf-8"))
            claims["claims"] = claims["claims"][:1]
            claims_path.write_text(json.dumps(claims), encoding="utf-8")

            report = audit_citations(article_path, sources_path, claims_path)

            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["used_citation_ids"], [1])

    def _valid_inputs(self, output_dir):
        control_dir = output_dir / ".storm-run"
        control_dir.mkdir(parents=True)
        article_path = output_dir / "storm_gen_article_polished.html"
        article_path.write_text(
            "<p>First factual claim [1]. Second factual claim [2].</p>",
            encoding="utf-8",
        )
        sources_path = control_dir / "sources.json"
        sources_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {"id": 1, "title": "Source one", "url": "https://example.com/1"},
                        {"id": 2, "title": "Source two", "url": "https://example.com/2"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        claims_path = control_dir / "claim-support.json"
        claims_path.write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "claim": "First factual claim",
                            "citation_ids": [1],
                            "source_ids": [1],
                            "support_status": "supported",
                            "evidence_note": "Direct support",
                            "action": "keep",
                        },
                        {
                            "claim": "Second factual claim",
                            "citation_ids": [2],
                            "source_ids": [2],
                            "support_status": "supported",
                            "evidence_note": "Direct support",
                            "action": "keep",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        return output_dir, article_path, sources_path, claims_path


if __name__ == "__main__":
    unittest.main()
