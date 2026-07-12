from __future__ import annotations

import importlib.util
import json
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

        for relative_reference in VALIDATOR.REFERENCE_FILES | VALIDATOR.RUNTIME_FILES:
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


class GuardedRoutingRegressionTests(unittest.TestCase):
    def test_file_producing_modes_use_the_bundled_guarded_clis(self) -> None:
        skill_text = VALIDATOR.SKILL_FILE.read_text(encoding="utf-8")

        for runtime_path in (
            "scripts/storm_state.py",
            "scripts/validate_artifacts.py",
            "scripts/audit_citations.py",
            "scripts/retrieval_backend.py",
            "scripts/runner_adapter.py",
        ):
            self.assertIn(runtime_path, skill_text)
        self.assertIn("execute exactly `next_action`", skill_text)
        self.assertIn(
            "never edit `phase`, `status`, or `next_action`", skill_text.lower()
        )

    def test_prompt_only_fallback_and_local_runner_mapping_are_explicit(self) -> None:
        skill_text = VALIDATOR.SKILL_FILE.read_text(encoding="utf-8")
        local_runner_text = (
            VALIDATOR.SKILL_DIR / "references" / "local-runner.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Python is unavailable", skill_text)
        self.assertIn("explicitly requests chat-only", skill_text)
        self.assertIn("unified guarded state", local_runner_text)
        self.assertIn("citation audit", local_runner_text)

    def test_optional_retrieval_does_not_change_execution_backend_semantics(self) -> None:
        skill_text = VALIDATOR.SKILL_FILE.read_text(encoding="utf-8")
        retrieval_text = (
            VALIDATOR.SKILL_DIR / "references" / "retrieval-backends.md"
        ).read_text(encoding="utf-8")

        self.assertRegex(skill_text, r"not execution\s+backend\s+values")
        self.assertIn("zero-dependency deterministic fallback", retrieval_text)
        self.assertIn("explicit `--fallback lexical`", retrieval_text)
        self.assertIn("never installs", retrieval_text)

    def test_official_runner_adapter_is_optional_secret_safe_and_classic_only(self) -> None:
        skill_text = VALIDATOR.SKILL_FILE.read_text(encoding="utf-8")
        adapter_text = (
            VALIDATOR.SKILL_DIR / "references" / "knowledge-storm-adapter.md"
        ).read_text(encoding="utf-8")

        self.assertIn("scripts/runner_adapter.py", skill_text)
        self.assertIn("never installs or executes the runner", skill_text)
        self.assertIn("polished_url_to_info.json", adapter_text)
        self.assertIn("never copies prompts", adapter_text)
        self.assertIn("Classic `STORMWikiRunner`", adapter_text)

    def test_optional_features_route_from_user_intent_without_batch_labels(self) -> None:
        skill_text = VALIDATOR.SKILL_FILE.read_text(encoding="utf-8")
        retrieval_text = (
            VALIDATOR.SKILL_DIR / "references" / "retrieval-backends.md"
        ).read_text(encoding="utf-8")
        adapter_text = (
            VALIDATOR.SKILL_DIR / "references" / "knowledge-storm-adapter.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Default retrieval intent", skill_text)
        self.assertIn("Ordinary Agent-led research", skill_text)
        self.assertIn("user-provided local corpus", skill_text)
        self.assertIn("explicit embedding provider", skill_text)
        self.assertIn("official Classic STORM output directory", skill_text)
        self.assertIn("Do not ask the user for an internal batch", skill_text)
        self.assertNotRegex(
            "\n".join((skill_text, retrieval_text, adapter_text)), r"\bB[56]\b"
        )


class ForwardEvalSchemaRegressionTests(unittest.TestCase):
    def test_eval_fixture_has_executable_forward_oracles(self) -> None:
        fixture = json.loads(VALIDATOR.EVALS_FILE.read_text(encoding="utf-8"))

        self.assertEqual(fixture["schema_version"], 2)
        self.assertGreaterEqual(len(fixture["cases"]), 10)
        for case in fixture["cases"]:
            self.assertEqual(case["forward"]["executor"], "fixture")
            self.assertTrue(case["forward"]["assertions"])


if __name__ == "__main__":
    unittest.main()
