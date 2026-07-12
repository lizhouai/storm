#!/usr/bin/env python3
"""Validate the STORM skill bundle without third-party Python packages."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "storm"
SKILL_FILE = SKILL_DIR / "SKILL.md"
OPENAI_FILE = SKILL_DIR / "agents" / "openai.yaml"
EVALS_FILE = ROOT / "evals" / "cases.json"
SCHEMA_FILES = {
    "references/co-storm-turn.schema.json",
    "references/run-state.schema.json",
}
REFERENCE_FILES = {
    "references/artifact-contract.md",
    "references/classic-storm.md",
    "references/co-storm.md",
    "references/co-storm-turn.schema.json",
    "references/local-runner.md",
    "references/knowledge-storm-adapter.md",
    "references/retrieval-backends.md",
    "references/run-state.schema.json",
    "references/safety-contract.md",
    "references/storm-method.md",
}
RUNTIME_FILES = {
    "scripts/audit_citations.py",
    "scripts/retrieval_backend.py",
    "scripts/runner_adapter.py",
    "scripts/storm_state.py",
    "scripts/validate_artifacts.py",
}
FORWARD_FIXTURES = {
    "artifact-complete",
    "chat-only",
    "checkpoint-partial",
    "claimed-complete-state-incomplete",
    "co-storm-conclusion-chat",
    "co-storm-follow-up",
    "co-storm-persisted-report",
    "co-storm-warm-start",
    "corpus-restricted",
    "overwrite-protected",
    "prompt-injection-rejected",
    "runner-safety",
}
FORWARD_ASSERTIONS = {
    "artifact_bundle_valid",
    "checkpoint_untrusted",
    "completion_state_matches_claim",
    "co_storm_artifact_boundary",
    "final_report_boundary",
    "mode_matches",
    "no_unauthorized_actions",
    "no_unrequested_artifacts",
    "previous_output_preserved",
    "recovery_explicit",
    "source_boundary_preserved",
    "speaker_cadence",
    "visible_roundtable",
}

FAILURES: list[str] = []

MOJIBAKE_SINGLETONS = ("\ufffd",)
MOJIBAKE_SEQUENCES = tuple(
    "".join(chr(codepoint) for codepoint in sequence)
    for sequence in (
        (0x951F, 0x65A4, 0x62F7),
        (0x00EF, 0x00BB, 0x00BF),
        (0x00E2, 0x20AC, 0x2122),
        (0x00E2, 0x20AC, 0x0153),
        (0x00E2, 0x20AC, 0x009D),
    )
)


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def read_utf8(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        FAILURES.append(f"missing required file: {path.relative_to(ROOT)}")
    except UnicodeDecodeError as error:
        FAILURES.append(
            f"invalid UTF-8 in {path.relative_to(ROOT)} at byte {error.start}"
        )
    return ""


def find_mojibake_markers(text: str) -> list[str]:
    markers = [
        f"U+{ord(character):04X}"
        for character in MOJIBAKE_SINGLETONS
        if character in text
    ]
    markers.extend(
        repr(sequence) for sequence in MOJIBAKE_SEQUENCES if sequence in text
    )
    return markers


def parse_scalar(raw: str, location: str) -> str:
    value = raw.strip()
    if not value:
        FAILURES.append(f"empty YAML scalar at {location}")
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            FAILURES.append(f"invalid quoted YAML scalar at {location}: {error.msg}")
            return ""
        if not isinstance(parsed, str):
            FAILURES.append(f"expected a string at {location}")
            return ""
        return parsed
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            FAILURES.append(f"unterminated quoted YAML scalar at {location}")
            return ""
        return value[1:-1].replace("''", "'")
    if re.search(r":(?:[ \t]|$)", value):
        FAILURES.append(
            f"unsafe plain YAML scalar at {location}: quote or fold values containing ':'"
        )
        return ""
    if re.search(r"[ \t]#", value):
        FAILURES.append(
            f"unsafe plain YAML scalar at {location}: quote or fold values containing '#'"
        )
        return ""
    return value


def parse_skill_frontmatter(text: str) -> tuple[dict[str, str], str]:
    normalized = text.replace("\r\n", "\n")
    match = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", normalized, re.DOTALL)
    if not match:
        FAILURES.append("SKILL.md must start with a complete YAML frontmatter block")
        return {}, normalized

    metadata: dict[str, str] = {}
    frontmatter_lines = match.group(1).splitlines()
    index = 0
    while index < len(frontmatter_lines):
        line_number = index + 2
        line = frontmatter_lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        field = re.fullmatch(r"([a-z][a-z0-9_-]*):[ \t]*(.*)", line)
        if not field:
            FAILURES.append(
                f"unsupported frontmatter syntax at SKILL.md:{line_number}; "
                "use one scalar field per line"
            )
            index += 1
            continue
        key, raw_value = field.groups()
        if key in metadata:
            FAILURES.append(f"duplicate frontmatter field: {key}")
            index += 1
            continue
        if raw_value in {">", ">-", ">+", "|", "|-", "|+"}:
            block_lines: list[str] = []
            index += 1
            while index < len(frontmatter_lines):
                block_line = frontmatter_lines[index]
                if block_line and not block_line.startswith((" ", "\t")):
                    break
                block_lines.append(block_line.lstrip())
                index += 1
            if not block_lines:
                FAILURES.append(f"empty YAML block scalar at SKILL.md:{line_number}")
                metadata[key] = ""
                continue
            separator = " " if raw_value.startswith(">") else "\n"
            metadata[key] = separator.join(block_lines).strip()
            continue
        metadata[key] = parse_scalar(raw_value, f"SKILL.md:{line_number}")
        index += 1
    return metadata, normalized[match.end() :]


def parse_openai_interface(text: str) -> dict[str, str]:
    normalized = text.replace("\r\n", "\n")
    lines = normalized.splitlines()
    try:
        interface_index = next(
            index for index, line in enumerate(lines) if line.strip() == "interface:"
        )
    except StopIteration:
        FAILURES.append("agents/openai.yaml is missing the interface mapping")
        return {}

    fields: dict[str, str] = {}
    for offset, line in enumerate(lines[interface_index + 1 :], interface_index + 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            break
        field = re.fullmatch(r"[ ]{2}([a-z][a-z0-9_]*):[ \t]*(.*)", line)
        if not field:
            FAILURES.append(
                f"unsupported interface syntax at agents/openai.yaml:{offset}"
            )
            continue
        key, raw_value = field.groups()
        if key in fields:
            FAILURES.append(f"duplicate agents/openai.yaml interface field: {key}")
            continue
        fields[key] = parse_scalar(raw_value, f"agents/openai.yaml:{offset}")
    return fields


def validate_frontmatter_and_bundle() -> tuple[str, str]:
    skill_text = read_utf8(SKILL_FILE)
    metadata, body = parse_skill_frontmatter(skill_text)

    allowed_fields = {"name", "description"}
    require(
        set(metadata) == allowed_fields,
        "SKILL.md frontmatter must contain only name and description; "
        f"found {sorted(metadata)}",
    )

    name = metadata.get("name", "")
    description = metadata.get("description", "")
    require(name == SKILL_DIR.name, "frontmatter name must match the skill directory")
    require(
        bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)),
        "frontmatter name must use lowercase letters, digits, and single hyphens",
    )
    require(
        1 <= len(description) <= 1024,
        "frontmatter description must be between 1 and 1024 characters",
    )

    relative_references = set(
        re.findall(
            r"(?<![A-Za-z0-9_./-])((?:references|agents|scripts)/[A-Za-z0-9._/-]+)",
            body,
        )
    )
    required_bundle_files = REFERENCE_FILES | RUNTIME_FILES
    require(
        required_bundle_files <= relative_references,
        "SKILL.md must route to every required supporting file; missing "
        f"{sorted(required_bundle_files - relative_references)}",
    )
    for reference in sorted(relative_references):
        target = (SKILL_DIR / reference).resolve()
        try:
            target.relative_to(SKILL_DIR.resolve())
        except ValueError:
            FAILURES.append(f"skill reference escapes the bundle: {reference}")
            continue
        require(target.is_file(), f"skill reference does not exist: {reference}")

    return skill_text, body


def validate_openai_metadata() -> str:
    text = read_utf8(OPENAI_FILE)
    fields = parse_openai_interface(text)
    required_fields = {"display_name", "short_description", "default_prompt"}
    missing = required_fields - fields.keys()
    require(not missing, f"agents/openai.yaml is missing fields: {sorted(missing)}")
    require(bool(fields.get("display_name", "").strip()), "display_name must not be empty")

    short_description = fields.get("short_description", "")
    require(
        25 <= len(short_description) <= 64,
        "short_description must be between 25 and 64 characters",
    )
    require(
        "$storm" in fields.get("default_prompt", ""),
        "default_prompt must explicitly invoke $storm",
    )
    return text


def validate_utf8_hygiene() -> None:
    text_suffixes = {".json", ".md", ".py", ".yaml", ".yml"}
    text_names = {".gitattributes", ".gitignore"}
    excluded_directories = {".git", ".results", ".venv", "__pycache__", "node_modules"}

    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(
            part in excluded_directories for part in relative.parts[:-1]
        ):
            continue
        if path.suffix.lower() not in text_suffixes and path.name not in text_names:
            continue
        text = read_utf8(path)
        require("\x00" not in text, f"NUL byte found in text file: {relative}")
        for marker in find_mojibake_markers(text):
            FAILURES.append(f"possible mojibake marker {marker} in {relative}")


def validate_json_schemas() -> None:
    for relative in sorted(SCHEMA_FILES):
        path = SKILL_DIR / relative
        try:
            schema = json.loads(read_utf8(path))
        except json.JSONDecodeError as error:
            FAILURES.append(
                f"invalid JSON in {relative}: {error.msg} at line {error.lineno}"
            )
            continue
        require(isinstance(schema, dict), f"{relative} must contain a JSON object")
        if isinstance(schema, dict):
            require(
                schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
                f"{relative} must use JSON Schema draft 2020-12",
            )


def is_nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def validate_eval_cases() -> None:
    text = read_utf8(EVALS_FILE)
    try:
        fixture = json.loads(text)
    except json.JSONDecodeError as error:
        FAILURES.append(f"invalid JSON in evals/cases.json: {error.msg} at line {error.lineno}")
        return

    require(isinstance(fixture, dict), "evals/cases.json must contain a JSON object")
    if not isinstance(fixture, dict):
        return
    require(
        set(fixture) == {"schema_version", "cases"},
        "eval fixture root must contain only schema_version and cases",
    )
    require(fixture.get("schema_version") == 2, "eval schema_version must equal 2")

    cases = fixture.get("cases")
    require(isinstance(cases, list) and bool(cases), "eval cases must be a non-empty list")
    if not isinstance(cases, list):
        return

    required_fields = {
        "id",
        "category",
        "description",
        "prompt",
        "expected_behavior",
        "forbidden_behavior",
        "forward",
    }
    required_categories = {
        "artifact",
        "chat",
        "co-storm",
        "corpus",
        "prompt-injection",
        "runner-safety",
        "overwrite",
        "recovery",
        "state-integrity",
    }
    seen_ids: set[str] = set()
    seen_categories: set[str] = set()
    co_storm_cases: list[dict[str, object]] = []

    for index, case in enumerate(cases):
        label = f"eval case #{index + 1}"
        if not isinstance(case, dict):
            FAILURES.append(f"{label} must be an object")
            continue
        require(set(case) == required_fields, f"{label} fields must equal {sorted(required_fields)}")

        case_id = case.get("id")
        category = case.get("category")
        require(
            isinstance(case_id, str)
            and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case_id)),
            f"{label} id must be lowercase kebab-case",
        )
        if isinstance(case_id, str):
            require(case_id not in seen_ids, f"duplicate eval id: {case_id}")
            seen_ids.add(case_id)
        require(
            isinstance(category, str) and category in required_categories,
            f"{label} has an unsupported category: {category!r}",
        )
        if isinstance(category, str):
            seen_categories.add(category)
            if category == "co-storm":
                co_storm_cases.append(case)
        require(
            isinstance(case.get("description"), str)
            and bool(case["description"].strip()),
            f"{label} description must be a non-empty string",
        )
        require(
            isinstance(case.get("prompt"), str) and bool(case["prompt"].strip()),
            f"{label} prompt must be a non-empty string",
        )
        require(
            is_nonempty_string_list(case.get("expected_behavior")),
            f"{label} expected_behavior must be a non-empty string list",
        )
        require(
            is_nonempty_string_list(case.get("forbidden_behavior")),
            f"{label} forbidden_behavior must be a non-empty string list",
        )
        forward = case.get("forward")
        require(isinstance(forward, dict), f"{label} forward must be an object")
        if isinstance(forward, dict):
            require(
                set(forward)
                == {"executor", "fixture", "expected_outcome", "assertions"},
                f"{label} forward fields are invalid",
            )
            require(
                forward.get("executor") == "fixture",
                f"{label} forward executor must equal fixture",
            )
            require(
                isinstance(forward.get("fixture"), str)
                and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", forward["fixture"])),
                f"{label} forward fixture must be lowercase kebab-case",
            )
            require(
                forward.get("fixture") in FORWARD_FIXTURES,
                f"{label} uses an unsupported forward fixture",
            )
            require(
                forward.get("expected_outcome") in {"pass", "violation_detected"},
                f"{label} forward expected_outcome is invalid",
            )
            require(
                is_nonempty_string_list(forward.get("assertions")),
                f"{label} forward assertions must be a non-empty string list",
            )
            assertions = forward.get("assertions")
            if isinstance(assertions, list):
                require(
                    set(assertions) <= FORWARD_ASSERTIONS,
                    f"{label} uses unsupported forward assertions: "
                    f"{sorted(set(assertions) - FORWARD_ASSERTIONS)}",
                )

    missing_categories = required_categories - seen_categories
    require(not missing_categories, f"eval coverage is missing categories: {sorted(missing_categories)}")
    require(
        len(co_storm_cases) >= 4,
        "eval coverage must include warm-start, follow-up, chat conclusion, and persisted-report Co-STORM cases",
    )
    require(len(cases) >= 10, "eval coverage must contain at least 10 executable cases")
    co_storm_expected = "\n".join(
        item
        for case in co_storm_cases
        for item in case.get("expected_behavior", [])
        if isinstance(item, str)
    ).lower()
    co_storm_forbidden = "\n".join(
        item
        for case in co_storm_cases
        for item in case.get("forbidden_behavior", [])
        if isinstance(item, str)
    ).lower()
    require(
        "primary speaker" in co_storm_expected
        and "different participant" in co_storm_expected
        and "moderator" in co_storm_expected,
        "Co-STORM evals must cover a visible primary speaker, respondent, and moderator",
    )
    require(
        "unlabeled" in co_storm_forbidden,
        "Co-STORM evals must reject an unlabeled single-voice response",
    )
    require(
        "final report in chat" in co_storm_expected
        and "write only .results/rag-technology/co_storm_report.html" in co_storm_expected,
        "Co-STORM evals must cover chat-only conclusion and report-only file output",
    )


def validate_behavior_contracts(skill_text: str, openai_text: str) -> None:
    readme_text = read_utf8(ROOT / "README.md")
    method_text = read_utf8(SKILL_DIR / "references" / "storm-method.md")
    classic_text = read_utf8(SKILL_DIR / "references" / "classic-storm.md")
    co_storm_text = read_utf8(SKILL_DIR / "references" / "co-storm.md")
    co_storm_turn_schema = read_utf8(
        SKILL_DIR / "references" / "co-storm-turn.schema.json"
    )
    artifact_text = read_utf8(SKILL_DIR / "references" / "artifact-contract.md")
    safety_text = read_utf8(SKILL_DIR / "references" / "safety-contract.md")
    local_runner_text = read_utf8(SKILL_DIR / "references" / "local-runner.md")
    runner_adapter_text = read_utf8(
        SKILL_DIR / "references" / "knowledge-storm-adapter.md"
    )
    retrieval_text = read_utf8(SKILL_DIR / "references" / "retrieval-backends.md")
    combined = "\n".join(
        (
            skill_text,
            method_text,
            classic_text,
            co_storm_text,
            co_storm_turn_schema,
            artifact_text,
            safety_text,
            local_runner_text,
            runner_adapter_text,
            retrieval_text,
            readme_text,
            openai_text,
        )
    )
    combined_lower = combined.lower()

    require(
        "prompt-native co-storm preview" in readme_text.lower(),
        "README must label Co-STORM as a prompt-native preview",
    )
    require(
        "does not bundle" in readme_text.lower()
        or "not a bundled" in readme_text.lower(),
        "README must disclose that no executable Co-STORM runner is bundled",
    )

    forbidden_claims = {
        "co-storm mode is available": "unqualified Co-STORM availability claim",
        "co-storm is available": "unqualified Co-STORM availability claim",
        "interactive co-storm exploration": "unqualified Co-STORM capability claim",
        "full co-storm implementation": "unbundled implementation claim",
        "executable co-storm runner is bundled": "unbundled runner claim",
    }
    for phrase, explanation in forbidden_claims.items():
        require(phrase not in combined_lower, f"forbidden {explanation}: {phrase!r}")

    require(
        re.search(r"untrusted.{0,180}(retriev|source|corpus|document|web)", combined_lower, re.DOTALL)
        is not None
        or re.search(
            r"(retriev|source|corpus|document|web).{0,180}untrusted",
            combined_lower,
            re.DOTALL,
        )
        is not None,
        "skill contract must treat retrieved or provided material as untrusted input",
    )
    require(
        "silently overwrite" in combined_lower,
        "skill contract must forbid silently overwriting an existing output directory",
    )
    require(
        "remote write" in combined_lower and "dependenc" in combined_lower,
        "runner safety contract must cover remote writes and dependency installation",
    )
    require(
        "never restore authorization" in combined_lower,
        "checkpoint recovery must not restore authorization for side effects",
    )
    require(
        "visible roundtable" in skill_text.lower()
        and "primary speaker" in co_storm_text.lower()
        and "named respondent" in skill_text.lower(),
        "Co-STORM contract must render visible primary and respondent voices",
    )
    require(
        "last_spoke_turn" in skill_text
        and "last_spoke_turn" in co_storm_text
        and "second consecutive expert-led turn" in co_storm_text.lower(),
        "Co-STORM contract must track speaker rotation and moderator cadence",
    )
    require(
        "co_storm_mind_map.<format>" in co_storm_text
        and "co_storm_report.<format>" in co_storm_text
        and "write both only" in co_storm_text.lower(),
        "Co-STORM contract must define standardized, request-scoped file output",
    )
    require(
        "classic artifact validator does not" in skill_text.lower()
        and "classic artifact validator does not" in co_storm_text.lower(),
        "Co-STORM contract must disclose the report-content validation boundary",
    )
    require(
        "record-turn" in skill_text
        and "record-turn" in co_storm_text
        and "co-storm-turn.schema.json" in skill_text,
        "persistent Co-STORM must route structured turns through the state CLI",
    )
    require(
        "direct_gen_outline.html" in artifact_text
        and "storm_gen_article_polished.html" in artifact_text
        and "guarded publication path supports html only" in artifact_text.lower(),
        "guarded Classic output must remain an HTML-only four-artifact contract",
    )
    require(
        "publication.json" in skill_text
        and "publication.json" in artifact_text
        and "publication.json" in readme_text,
        "Classic completion must document its atomic publication hash receipt",
    )
    require(
        "--staging" in skill_text and ".storm-run/staging" in artifact_text,
        "guarded Classic validation must remain staging-first",
    )
    require(
        "scripts/retrieval_backend.py" in skill_text
        and "retrieval-backends.md" in skill_text
        and re.search(r"not execution\s+backend\s+values", skill_text.lower()) is not None,
        "optional retrieval must be bundled without changing execution backend semantics",
    )
    require(
        "zero-dependency deterministic fallback" in retrieval_text.lower()
        and "explicit `--fallback lexical`" in retrieval_text.lower()
        and "never installs" in retrieval_text.lower(),
        "retrieval contract must keep lexical zero-dependency and embedding fallback explicit",
    )
    require(
        "scripts/runner_adapter.py" in skill_text
        and "knowledge-storm-adapter.md" in skill_text
        and "never installs or executes the runner" in skill_text.lower(),
        "official runner adapter must remain optional and non-executing",
    )
    require(
        "polished_url_to_info.json" in runner_adapter_text
        and "never guesses" in runner_adapter_text.lower()
        and "never copies prompts" in runner_adapter_text.lower()
        and "classic `stormwikirunner`" in runner_adapter_text.lower(),
        "official runner adapter must preserve polished citations, secrets, and Classic scope",
    )
    require(
        "compatibility index" in method_text.lower()
        and "classic-storm.md" in method_text
        and "co-storm.md" in method_text,
        "storm-method.md must remain a compatibility index for split references",
    )


def main() -> int:
    skill_text, _ = validate_frontmatter_and_bundle()
    openai_text = validate_openai_metadata()
    validate_utf8_hygiene()
    validate_json_schemas()
    validate_eval_cases()
    validate_behavior_contracts(skill_text, openai_text)

    if FAILURES:
        print("Skill validation failed:", file=sys.stderr)
        for failure in FAILURES:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Skill validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
