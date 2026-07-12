#!/usr/bin/env python3
"""Import official Classic STORMWikiRunner outputs into the guarded runtime."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata as metadata
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


ADAPTER_SCHEMA_VERSION = "1.0"
RUNNER_DISTRIBUTION = "knowledge-storm"
RUNNER_IMPORT = "knowledge_storm"
REQUIREMENT = "knowledge-storm>=1.1.1,<1.2 (install only with current user approval)"
RECOGNIZED_INPUTS = (
    "conversation_log.json",
    "raw_search_results.json",
    "direct_gen_outline.txt",
    "storm_gen_outline.txt",
    "storm_gen_article.txt",
    "url_to_info.json",
    "storm_gen_article_polished.txt",
    "polished_url_to_info.json",
    "run_config.json",
    "llm_call_history.jsonl",
)
ACTION_EVENTS = {
    "define_scope": "scope_defined",
    "generate_perspectives": "perspectives_ready",
    "run_interviews": "interviews_completed",
    "build_information_table": "information_table_ready",
    "generate_direct_outline": "direct_outline_ready",
    "refine_outline": "refined_outline_ready",
    "write_draft": "draft_ready",
    "polish_article": "polished",
    "verify_artifacts": None,
    "publish": "completed",
}
SECRET_KEY_PARTS = (
    "apikey",
    "apibase",
    "baseurl",
    "endpoint",
    "secret",
    "password",
    "authorization",
    "credential",
)
ALLOWED_CONFIG_KEYS = {
    "model",
    "model_name",
    "provider",
    "temperature",
    "max_tokens",
    "max_output_tokens",
}
CITATION_RE = re.compile(r"\[(\d+)\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class AdapterError(ValueError):
    """Raised when runner output cannot be mapped without guessing or overwriting."""


def _load_storm_state():
    try:
        import storm_state as module

        return module
    except ModuleNotFoundError:
        path = Path(__file__).with_name("storm_state.py")
        specification = importlib.util.spec_from_file_location("storm_state", path)
        if specification is None or specification.loader is None:
            raise AdapterError("bundled storm_state.py could not be loaded")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module


storm_state = _load_storm_state()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def jsonl_bytes(values: list[dict[str, Any]]) -> bytes:
    return "".join(canonical_json(value) + "\n" for value in values).encode("utf-8")


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"{label} must be a non-empty string")
    return value.strip()


def validate_source_directory(source: Path, output_root: Path) -> Path:
    if source.is_symlink() or not source.is_dir():
        raise AdapterError("runner source must be an existing non-symlink directory")
    resolved = source.resolve()
    output_resolved = output_root.resolve()
    if (
        resolved == output_resolved
        or resolved in output_resolved.parents
        or output_resolved in resolved.parents
    ):
        raise AdapterError(
            "runner source must not overlap the guarded output tree in either direction"
        )
    return source


def read_source_bytes(source: Path, filename: str, *, required: bool = True) -> bytes | None:
    path = source / filename
    if not path.exists():
        if required:
            raise AdapterError(f"missing runner output: {filename}")
        return None
    if path.is_symlink() or not path.is_file() or path.parent.resolve() != source.resolve():
        raise AdapterError(f"runner output must be a direct non-symlink file: {filename}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AdapterError(f"cannot read runner output {filename}: {exc}") from exc


def read_source_text(source: Path, filename: str, *, required: bool = True) -> str | None:
    raw = read_source_bytes(source, filename, required=required)
    if raw is None:
        return None
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AdapterError(f"runner output must be strict UTF-8: {filename}") from exc


def read_source_json(source: Path, filename: str, *, required: bool = True) -> Any:
    text = read_source_text(source, filename, required=required)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"runner output is not valid JSON: {filename}") from exc


def write_outputs(outputs: dict[Path, bytes]) -> tuple[list[str], list[str]]:
    created: list[str] = []
    unchanged: list[str] = []
    for path, value in outputs.items():
        if path.is_symlink() or path.parent.is_symlink():
            raise AdapterError(f"adapter output path must not be a symlink: {path.name}")
        if path.exists():
            if not path.is_file():
                raise AdapterError(f"adapter output path is not a file: {path.name}")
            if path.read_bytes() != value:
                raise AdapterError(
                    f"{path.name} conflicts with existing adapter output; use a new guarded run"
                )
            unchanged.append(path.name)
    for path, value in outputs.items():
        if path.exists():
            continue
        atomic_write_bytes(path, value)
        created.append(path.name)
    return created, unchanged


def probe_dependency() -> dict[str, Any]:
    try:
        import_visible = importlib.util.find_spec(RUNNER_IMPORT) is not None
    except (ImportError, ValueError):
        import_visible = False
    try:
        version = metadata.version(RUNNER_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        version = None
    installed = bool(import_visible and version)
    supported = bool(version and supported_runner_version(version))
    available = bool(installed and supported)
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "distribution": RUNNER_DISTRIBUTION,
        "import_name": RUNNER_IMPORT,
        "classic_runner": "STORMWikiRunner",
        "installed": installed,
        "supported": supported,
        "available": available,
        "version": version,
        "version_source": "distribution-metadata" if version is not None else None,
        "requirement": REQUIREMENT,
        "automatic_install": False,
        "dspy_managed_by_runner": True,
    }


def supported_runner_version(version: str) -> bool:
    match = re.fullmatch(r"1\.1\.(\d+)(?:[A-Za-z0-9.+-]*)?", version)
    return match is not None and int(match.group(1)) >= 1


def summarize_config(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    selected: list[dict[str, Any]] = []
    redacted: set[str] = set()

    def visit(item: Any, path: list[str]) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                key_text = str(key)
                normalized = key_text.casefold().replace("-", "_")
                compact = re.sub(r"[^a-z0-9]", "", normalized)
                is_secret = normalized not in ALLOWED_CONFIG_KEYS and (
                    any(part in compact for part in SECRET_KEY_PARTS)
                    or compact == "token"
                    or compact.endswith("token")
                )
                if is_secret:
                    redacted.add(key_text)
                    continue
                next_path = [*path, key_text]
                if normalized in ALLOWED_CONFIG_KEYS and isinstance(
                    nested, (str, int, float, bool, type(None))
                ):
                    selected.append({"path": ".".join(next_path), "value": nested})
                else:
                    visit(nested, next_path)
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                visit(nested, [*path, str(index)])

    visit(value, [])
    selected.sort(key=lambda record: record["path"])
    return selected, sorted(redacted, key=str.casefold)


def summarize_lm_history(source: Path) -> dict[str, Any] | None:
    raw = read_source_bytes(source, "llm_call_history.jsonl", required=False)
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AdapterError("runner output must be strict UTF-8: llm_call_history.jsonl") from exc
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise AdapterError("llm_call_history.jsonl must contain non-blank JSON object lines")
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"llm_call_history.jsonl line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(record, dict):
            raise AdapterError(f"llm_call_history.jsonl line {line_number} must be an object")
    return {"line_count": len(lines), "sha256": sha256_bytes(raw)}


def input_file_inventory(source: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for filename in RECOGNIZED_INPUTS:
        raw = read_source_bytes(source, filename, required=False)
        if raw is not None:
            inventory[filename] = {"sha256": sha256_bytes(raw), "size_bytes": len(raw)}
    return inventory


def build_manifest(source: Path, args: argparse.Namespace) -> dict[str, Any]:
    dependency = probe_dependency()
    runner_version = args.runner_version or dependency["version"]
    if not runner_version:
        raise AdapterError(
            "runner version is unavailable; pass --runner-version for offline fixture import"
        )
    if not supported_runner_version(runner_version):
        raise AdapterError(
            f"unsupported knowledge-storm version {runner_version!r}; expected the 1.1.x contract"
        )
    input_files = input_file_inventory(source)
    config = read_source_json(source, "run_config.json", required=False)
    selected_config, redacted_fields = summarize_config(config)
    history = summarize_lm_history(source)
    if args.search_top_k is not None and args.search_top_k < 1:
        raise AdapterError("search top-k must be at least 1")
    retriever = {
        "name": args.retriever,
        "version": args.retriever_version,
        "top_k": args.search_top_k,
        "provenance": "explicit" if args.retriever else "not-recorded",
    }
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter": "knowledge-storm-classic",
        "distribution": RUNNER_DISTRIBUTION,
        "runner_class": "STORMWikiRunner",
        "runner_version": runner_version,
        "runner_version_source": "explicit" if args.runner_version else "distribution-metadata",
        "runner_exit_status": args.exit_status,
        "source_directory_name": source.name,
        "input_files": input_files,
        "model_configuration": selected_config,
        "redacted_fields": redacted_fields,
        "redacted_field_count": len(redacted_fields),
        "retriever": retriever,
        "lm_history": history,
        "post_run_observed": (source / "run_config.json").is_file()
        and (source / "llm_call_history.jsonl").is_file(),
        "polished_reference_map_captured": (source / "polished_url_to_info.json").is_file(),
        "workflow_traceable": True,
        "generated_content_reproducible": False,
        "automatic_install": False,
    }


def verify_source_snapshot(source: Path, control: Path) -> None:
    manifest_path = control / "runner-manifest.json"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.parent.resolve() != control.resolve()
    ):
        raise AdapterError("runner-manifest.json is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"runner-manifest.json is invalid: {exc}") from exc
    expected = manifest.get("input_files") if isinstance(manifest, dict) else None
    if not isinstance(expected, dict) or expected != input_file_inventory(source):
        raise AdapterError(
            "runner source changed after manifest capture; use a new guarded run"
        )


def normalize_information(value: Any, url: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AdapterError(f"{label} must be an object")
    recorded_url = value.get("url", url)
    if recorded_url != url:
        raise AdapterError(f"{label} URL does not match its mapping key")
    title = require_string(value.get("title"), f"{label} title")
    description = value.get("description", "")
    if not isinstance(description, str):
        raise AdapterError(f"{label} description must be a string")
    raw_snippets = value.get("snippets", [])
    if not isinstance(raw_snippets, list) or not all(
        isinstance(snippet, str) for snippet in raw_snippets
    ):
        raise AdapterError(f"{label} snippets must be a string array")
    snippets = [snippet.strip() for snippet in raw_snippets if snippet.strip()]
    if not snippets and description.strip():
        snippets = [description.strip()]
    if not snippets:
        raise AdapterError(f"{label} requires a non-empty snippet or description")
    return {
        "url": url,
        "title": title,
        "description": description.strip(),
        "snippets": snippets,
    }


def load_conversation(source: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = read_source_json(source, "conversation_log.json")
    if not isinstance(raw, list) or not raw:
        raise AdapterError("conversation_log.json must contain a non-empty array")
    perspectives: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for perspective_number, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise AdapterError(f"conversation perspective {perspective_number} must be an object")
        role = require_string(
            item.get("perspective"), f"conversation perspective {perspective_number}"
        )
        if role.casefold().startswith("basic fact writer"):
            role = "Basic fact writer"
        if role.casefold() in seen_roles:
            raise AdapterError(f"duplicate conversation perspective: {role!r}")
        seen_roles.add(role.casefold())
        perspective_id = f"P{perspective_number}"
        perspectives.append(
            {"id": perspective_id, "role": role, "source": "knowledge-storm"}
        )
        raw_turns = item.get("dlg_turns")
        if not isinstance(raw_turns, list) or not raw_turns:
            raise AdapterError(f"conversation perspective {role!r} has no dialogue turns")
        for turn_number, turn in enumerate(raw_turns, start=1):
            if not isinstance(turn, dict):
                raise AdapterError(f"conversation turn {role!r}/{turn_number} must be an object")
            question = require_string(
                turn.get("agent_utterance"), f"conversation turn {role!r}/{turn_number} question"
            )
            answer = require_string(
                turn.get("user_utterance"), f"conversation turn {role!r}/{turn_number} answer"
            )
            raw_queries = turn.get("search_queries")
            if not isinstance(raw_queries, list) or not all(
                isinstance(query, str) for query in raw_queries
            ):
                raise AdapterError(
                    f"conversation turn {role!r}/{turn_number} search_queries must be an array"
                )
            queries = [query.strip() for query in raw_queries if query.strip()]
            raw_results = turn.get("search_results")
            if not isinstance(raw_results, list) or not raw_results:
                raise AdapterError(f"conversation turn {role!r}/{turn_number} has no search results")
            results: list[dict[str, Any]] = []
            for result_number, result in enumerate(raw_results, start=1):
                url = require_string(
                    result.get("url") if isinstance(result, dict) else None,
                    f"conversation search result {role!r}/{turn_number}/{result_number} URL",
                )
                results.append(
                    normalize_information(
                        result,
                        url,
                        f"conversation search result {role!r}/{turn_number}/{result_number}",
                    )
                )
            turns.append(
                {
                    "perspective_id": perspective_id,
                    "perspective": role,
                    "turn": turn_number,
                    "question": question,
                    "answer": answer,
                    "queries": queries,
                    "results": results,
                }
            )
    if "basic fact writer" not in seen_roles:
        raise AdapterError("conversation_log.json must include Basic fact writer")
    return perspectives, turns


def source_id(url: str) -> str:
    return f"KS-{sha256_text(url)[:12]}"


def collect_sources(source: Path, turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    raw_search = read_source_json(source, "raw_search_results.json")
    if not isinstance(raw_search, dict) or not raw_search:
        raise AdapterError("raw_search_results.json must contain a non-empty object")
    sources: dict[str, dict[str, Any]] = {}
    for url, value in raw_search.items():
        normalized_url = require_string(url, "raw search result URL")
        sources[normalized_url] = normalize_information(
            value, normalized_url, f"raw search result {normalized_url!r}"
        )
    for turn in turns:
        for result in turn["results"]:
            sources.setdefault(result["url"], result)
    return sources


def perspective_outputs(source: Path) -> dict[str, Any]:
    perspectives, _ = load_conversation(source)
    return {"schema_version": ADAPTER_SCHEMA_VERSION, "perspectives": perspectives}


def interview_outputs(
    source: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _, turns = load_conversation(source)
    for turn in turns:
        if not turn["queries"]:
            raise AdapterError("every imported interview turn requires a non-empty search query")
    sources = collect_sources(source, turns)
    queries_by_url: dict[str, set[str]] = {url: set() for url in sources}
    interviews: list[dict[str, Any]] = []
    for turn in turns:
        turn_source_ids: list[str] = []
        for result in turn["results"]:
            url = result["url"]
            turn_source_ids.append(source_id(url))
            queries_by_url.setdefault(url, set()).update(turn["queries"])
        if not turn_source_ids:
            raise AdapterError("every imported interview turn requires a resolved source")
        interviews.append(
            {
                "perspective_id": turn["perspective_id"],
                "turn": turn["turn"],
                "question": turn["question"],
                "answer": turn["answer"],
                "queries": turn["queries"],
                "source_ids": list(dict.fromkeys(turn_source_ids)),
            }
        )
    retrieval: list[dict[str, Any]] = []
    for url in sorted(sources):
        information = sources[url]
        snippet = information["snippets"][0]
        queries = sorted(queries_by_url.get(url, set()))
        retrieval.append(
            {
                "schema_version": ADAPTER_SCHEMA_VERSION,
                "backend_requested": "knowledge-storm-runner",
                "backend_used": "knowledge-storm-runner",
                "algorithm": "upstream-runner-ranking",
                "model": None,
                "provider_version": None,
                "query": queries[0] if queries else None,
                "queries": queries,
                "top_k": None,
                "rank": None,
                "score": None,
                "source_id": source_id(url),
                "title": information["title"],
                "url": url,
                "snippet": snippet,
                "snippet_hash": sha256_text(snippet),
            }
        )
    return interviews, retrieval


def information_table(source: Path) -> list[dict[str, Any]]:
    _, turns = load_conversation(source)
    sources = collect_sources(source, turns)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for turn in turns:
        if not turn["queries"]:
            raise AdapterError("every imported interview turn requires a non-empty search query")
        for result in turn["results"]:
            information = sources[result["url"]]
            snippet = information["snippets"][0]
            key = (source_id(result["url"]), snippet, turn["answer"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "perspective": turn["perspective_id"],
                    "question": turn["question"],
                    "query": turn["queries"][0],
                    "source_id": key[0],
                    "url": result["url"],
                    "title": information["title"],
                    "snippet": snippet,
                    "claim_supported": turn["answer"],
                    "reliability_note": (
                        "Imported from knowledge-storm; semantic support still requires review."
                    ),
                }
            )
    if not rows:
        raise AdapterError("runner outputs did not produce information-table evidence")
    return rows


def markdown_body(
    value: str,
    label: str,
    *,
    outline_topic: str | None = None,
    forbid_references_heading: bool = False,
) -> str:
    if not value.strip():
        raise AdapterError(f"{label} must not be empty")
    blocks: list[str] = []
    paragraph: list[str] = []
    heading_count = 0
    previous_heading_level = 0

    def flush() -> None:
        if paragraph:
            blocks.append(f"<p>{html.escape(' '.join(paragraph), quote=True)}</p>")
            paragraph.clear()

    for line in value.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        heading = HEADING_RE.fullmatch(stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            if level > 3:
                raise AdapterError(f"{label} uses an unsupported heading level: h{level}")
            text = require_string(heading.group(2), f"{label} heading")
            if previous_heading_level == 0 and level != 1:
                raise AdapterError(f"{label} heading structure must start at h1")
            if previous_heading_level and level > previous_heading_level + 1:
                raise AdapterError(
                    f"{label} heading level skips from h{previous_heading_level} to h{level}"
                )
            if outline_topic is not None:
                normalized = " ".join(text.casefold().split())
                if normalized == " ".join(outline_topic.casefold().split()):
                    raise AdapterError(f"{label} outline must not duplicate the topic heading")
                if normalized in {"references", "sources", "参考文献", "参考资料"}:
                    raise AdapterError(f"{label} outline must not contain a References heading")
            elif forbid_references_heading and " ".join(text.casefold().split()) in {
                "references",
                "sources",
                "参考文献",
                "参考资料",
            }:
                raise AdapterError(
                    f"{label} must not include its own References heading before mapping"
                )
            blocks.append(f"<h{level}>{html.escape(text, quote=True)}</h{level}>")
            heading_count += 1
            previous_heading_level = level
        else:
            paragraph.append(stripped)
    flush()
    if heading_count == 0:
        raise AdapterError(f"{label} requires Markdown-style headings")
    return "\n    ".join(blocks)


def load_reference_map(
    source: Path, filename: str, article_text: str
) -> tuple[list[dict[str, Any]], set[int]]:
    raw = read_source_json(source, filename)
    if not isinstance(raw, dict) or set(raw) != {"url_to_unified_index", "url_to_info"}:
        raise AdapterError(f"{filename} fields are invalid")
    index_map = raw["url_to_unified_index"]
    info_map = raw["url_to_info"]
    if not isinstance(index_map, dict) or not index_map:
        raise AdapterError(f"{filename} requires a non-empty url_to_unified_index")
    if not isinstance(info_map, dict) or set(info_map) != set(index_map):
        raise AdapterError(f"{filename} URL maps are incomplete or inconsistent")
    indexes = list(index_map.values())
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indexes):
        raise AdapterError(f"{filename} citation indexes must be integers")
    if sorted(indexes) != list(range(1, len(indexes) + 1)):
        raise AdapterError(f"{filename} citation indexes must be consecutive from 1")
    used_ids = {int(value) for value in CITATION_RE.findall(article_text)}
    if not used_ids or sorted(used_ids) != list(range(1, max(used_ids) + 1)):
        raise AdapterError(f"{filename} article citations must be consecutive from 1")
    if not used_ids <= set(indexes):
        raise AdapterError(f"{filename} does not resolve every article citation")
    records: list[dict[str, Any]] = []
    for url, citation_id in sorted(index_map.items(), key=lambda item: item[1]):
        normalized_url = require_string(url, f"{filename} URL")
        information = normalize_information(
            info_map[url], normalized_url, f"{filename} source {citation_id}"
        )
        records.append(
            {
                "id": citation_id,
                "source_id": source_id(normalized_url),
                "title": information["title"],
                "url": normalized_url,
                "snippets": information["snippets"],
                "unused_evidence": citation_id not in used_ids,
            }
        )
    return records, used_ids


def render_html(
    *,
    title: str,
    markdown_text: str,
    label: str,
    references: list[dict[str, Any]] | None = None,
    outline_topic: str | None = None,
) -> str:
    body = markdown_body(
        markdown_text,
        label,
        outline_topic=outline_topic,
        forbid_references_heading=references is not None,
    )
    reference_html = ""
    if references is not None:
        used = [record for record in references if not record["unused_evidence"]]
        items = "\n".join(
            "      <li><strong>"
            + html.escape(record["title"], quote=True)
            + "</strong>. "
            + html.escape(record["url"], quote=True)
            + ".</li>"
            for record in used
        )
        reference_html = f'\n    <h1>References</h1>\n    <ol>\n{items}\n    </ol>'
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{html.escape(title, quote=True)}</title>\n"
        "</head>\n"
        "<body>\n"
        f"    {body}{reference_html}\n"
        "</body>\n"
        "</html>\n"
    )


def claims_from_article(article_text: str, used_ids: set[int]) -> dict[str, Any]:
    paragraphs = [
        " ".join(part.strip().split())
        for part in re.split(r"\n\s*\n", article_text)
        if part.strip()
    ]
    claims: list[dict[str, Any]] = []
    covered_ids: set[int] = set()
    for paragraph in paragraphs:
        citation_ids = list(
            dict.fromkeys(int(value) for value in CITATION_RE.findall(paragraph))
        )
        if not citation_ids:
            continue
        if not set(citation_ids) <= used_ids:
            raise AdapterError("polished article paragraph contains an unresolved citation")
        claim = CITATION_RE.sub("", paragraph)
        claim = re.sub(r"^#{1,6}\s+", "", claim).strip()
        claim = re.sub(r"\s+([.,;:!?])", r"\1", claim)
        claim = require_string(claim, "polished article cited claim")
        claims.append(
            {
                "claim": claim,
                "citation_ids": citation_ids,
                "source_ids": citation_ids,
                "support_status": "unreviewed",
                "evidence_note": "Adapter candidate only; no semantic support decision was made.",
                "action": "review",
            }
        )
        covered_ids.update(citation_ids)
    if covered_ids != used_ids:
        missing = sorted(used_ids - covered_ids)
        raise AdapterError(
            f"polished article citations are not attached to reviewable paragraphs: {missing}"
        )
    return {"schema_version": ADAPTER_SCHEMA_VERSION, "claims": claims}


def action_outputs(
    action: str,
    *,
    state: dict[str, Any],
    source: Path,
    control: Path,
    args: argparse.Namespace,
) -> tuple[dict[Path, bytes], bool, list[str]]:
    staging = control / "staging"
    if action == "define_scope":
        return {
            control / "runner-manifest.json": json_bytes(build_manifest(source, args))
        }, True, []
    if action == "generate_perspectives":
        return {
            control / "perspectives.json": json_bytes(perspective_outputs(source))
        }, True, []
    if action == "run_interviews":
        interviews, retrieval = interview_outputs(source)
        return {
            control / "interviews.jsonl": jsonl_bytes(interviews),
            control / "retrieval-log.jsonl": jsonl_bytes(retrieval),
        }, True, []
    if action == "build_information_table":
        return {
            control / "information-table.jsonl": jsonl_bytes(information_table(source))
        }, True, []
    if action in {"generate_direct_outline", "refine_outline"}:
        filename = (
            "direct_gen_outline.txt" if action == "generate_direct_outline" else "storm_gen_outline.txt"
        )
        output_name = filename.replace(".txt", ".html")
        text = read_source_text(source, filename)
        assert text is not None
        rendered = render_html(
            title=f"{state['topic']} - {'Direct' if action == 'generate_direct_outline' else 'Refined'} outline",
            markdown_text=text,
            label=filename,
            outline_topic=state["topic"],
        )
        return {staging / output_name: rendered.encode("utf-8")}, True, []
    if action == "write_draft":
        text = read_source_text(source, "storm_gen_article.txt")
        assert text is not None
        references, _ = load_reference_map(source, "url_to_info.json", text)
        rendered = render_html(
            title=f"{state['topic']} - Draft",
            markdown_text=text,
            label="storm_gen_article.txt",
            references=references,
        )
        return {
            staging / "storm_gen_article.html": rendered.encode("utf-8"),
            control / "runner-draft-sources.json": json_bytes(
                {"schema_version": ADAPTER_SCHEMA_VERSION, "sources": references}
            ),
        }, True, []
    if action == "polish_article":
        text = read_source_text(source, "storm_gen_article_polished.txt")
        assert text is not None
        references, used_ids = load_reference_map(
            source, "polished_url_to_info.json", text
        )
        rendered = render_html(
            title=f"{state['topic']} - Polished article",
            markdown_text=text,
            label="storm_gen_article_polished.txt",
            references=references,
        )
        return {
            staging / "storm_gen_article_polished.html": rendered.encode("utf-8"),
            control / "sources.json": json_bytes(
                {"schema_version": ADAPTER_SCHEMA_VERSION, "sources": references}
            ),
            control / "claim-support-candidates.json": json_bytes(
                claims_from_article(text, used_ids)
            ),
        }, True, []
    if action == "verify_artifacts":
        return {}, False, [
            "Review claim-support-candidates.json and write claim-support.json.",
            "Run audit_citations.py against the staged polished article.",
            "Run validate_artifacts.py with --staging before advancing verified.",
        ]
    if action == "publish":
        return {}, True, [
            "Use storm_state.py advance --event completed; the adapter never publishes directly."
        ]
    raise AdapterError(f"runner adapter does not support next_action: {action!r}")


def sync_run(args: argparse.Namespace) -> dict[str, Any]:
    run_path = args.run
    if (
        run_path.name != "run.json"
        or run_path.parent.name != ".storm-run"
        or run_path.is_symlink()
        or run_path.parent.is_symlink()
    ):
        raise AdapterError("--run must be the non-symlink .storm-run/run.json")
    try:
        state, _ = storm_state.load_guarded_run(run_path)
    except (OSError, ValueError, storm_state.StateError) as exc:
        raise AdapterError(f"guarded run is invalid: {exc}") from exc
    if state["mode"] != "classic":
        raise AdapterError("knowledge-storm adapter supports Classic STORM only")
    if state["execution_backend"] != "local-runner":
        raise AdapterError("knowledge-storm adapter requires execution_backend=local-runner")
    if state["status"] != "running":
        raise AdapterError("knowledge-storm adapter requires a running guarded state")
    action = state["next_action"]
    if action not in ACTION_EVENTS:
        raise AdapterError(f"guarded run has unsupported next_action: {action!r}")
    control = run_path.parent
    output_root = control.parent
    source = validate_source_directory(args.source, output_root)
    if action != "define_scope":
        verify_source_snapshot(source, control)
    outputs, ready, instructions = action_outputs(
        action, state=state, source=source, control=control, args=args
    )
    created, unchanged = write_outputs(outputs)
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter": "knowledge-storm-classic",
        "run_id": state["run_id"],
        "phase": state["phase"],
        "next_action": action,
        "ready_for_event": ready,
        "suggested_event": ACTION_EVENTS[action] if ready else None,
        "created_files": sorted(created),
        "unchanged_files": sorted(unchanged),
        "instructions": instructions,
        "state_advanced": False,
        "automatic_install": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe_parser = subparsers.add_parser("probe", help="Detect knowledge-storm lazily")
    probe_parser.set_defaults(handler=lambda _args: probe_dependency())

    sync_parser = subparsers.add_parser(
        "sync", help="Import exactly the evidence required by the guarded next_action"
    )
    sync_parser.add_argument("--run", type=Path, required=True)
    sync_parser.add_argument("--source", type=Path, required=True)
    sync_parser.add_argument("--runner-version")
    sync_parser.add_argument("--retriever")
    sync_parser.add_argument("--retriever-version")
    sync_parser.add_argument("--search-top-k", type=int)
    sync_parser.add_argument("--exit-status", type=int)
    sync_parser.set_defaults(handler=sync_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        report = args.handler(args)
    except (AdapterError, OSError) as exc:
        print(f"runner adapter error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
