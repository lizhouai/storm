from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_skill", ROOT / "scripts" / "validate_skill.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load scripts/validate_skill.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class FrontmatterRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        VALIDATOR.FAILURES.clear()

    def tearDown(self) -> None:
        VALIDATOR.FAILURES.clear()

    def test_folded_description_is_parsed_as_one_string(self) -> None:
        metadata, body = VALIDATOR.parse_skill_frontmatter(
            "---\n"
            "name: storm\n"
            "description: >-\n"
            "  Conduct cited research.\n"
            "  Use for technical surveys.\n"
            "---\n"
            "# STORM Research\n"
        )

        self.assertEqual(metadata["name"], "storm")
        self.assertEqual(
            metadata["description"],
            "Conduct cited research. Use for technical surveys.",
        )
        self.assertIn("# STORM Research", body)
        self.assertEqual(VALIDATOR.FAILURES, [])

    def test_unquoted_colon_space_is_rejected(self) -> None:
        metadata, _ = VALIDATOR.parse_skill_frontmatter(
            "---\n"
            "name: storm\n"
            "description: Produce these files: outline and article\n"
            "---\n"
        )

        self.assertEqual(metadata["description"], "")
        self.assertTrue(
            any("unsafe plain YAML scalar" in failure for failure in VALIDATOR.FAILURES)
        )

    def test_unexpected_frontmatter_field_remains_visible_to_contract_check(self) -> None:
        metadata, _ = VALIDATOR.parse_skill_frontmatter(
            "---\n"
            "name: storm\n"
            "version: 0.3.0\n"
            "description: >-\n"
            "  Conduct cited research.\n"
            "---\n"
        )

        self.assertEqual(set(metadata), {"name", "version", "description"})
        self.assertNotEqual(set(metadata), {"name", "description"})


class OpenAIMetadataRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        VALIDATOR.FAILURES.clear()

    def tearDown(self) -> None:
        VALIDATOR.FAILURES.clear()

    def test_interface_strings_are_read_without_yaml_dependency(self) -> None:
        fields = VALIDATOR.parse_openai_interface(
            'interface:\n'
            '  display_name: "STORM Research"\n'
            '  short_description: "Source-grounded STORM research and reports"\n'
            '  default_prompt: "Use $storm for cited research."\n'
        )

        self.assertEqual(fields["display_name"], "STORM Research")
        self.assertIn("$storm", fields["default_prompt"])
        self.assertEqual(VALIDATOR.FAILURES, [])


class UTF8RegressionTests(unittest.TestCase):
    def test_legitimate_cjk_characters_are_not_mojibake_by_themselves(self) -> None:
        self.assertEqual(VALIDATOR.find_mojibake_markers("这是一段浓缩内容。"), [])

    def test_replacement_character_is_reported(self) -> None:
        self.assertEqual(VALIDATOR.find_mojibake_markers("broken \ufffd text"), ["U+FFFD"])


class SplitReferenceRegressionTests(unittest.TestCase):
    def test_every_routed_reference_is_installed_in_the_bundle(self) -> None:
        skill_text = VALIDATOR.SKILL_FILE.read_text(encoding="utf-8")

        for relative_reference in VALIDATOR.REFERENCE_FILES:
            self.assertIn(relative_reference, skill_text)
            self.assertTrue((VALIDATOR.SKILL_DIR / relative_reference).is_file())

    def test_legacy_method_file_is_a_compatibility_index(self) -> None:
        method_text = (
            VALIDATOR.SKILL_DIR / "references" / "storm-method.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Compatibility Index", method_text)
        self.assertIn("classic-storm.md", method_text)
        self.assertIn("co-storm.md", method_text)
        self.assertNotIn("## Classic STORM Algorithm", method_text)


if __name__ == "__main__":
    unittest.main()
