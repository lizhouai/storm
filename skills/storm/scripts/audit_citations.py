#!/usr/bin/env python3
"""Audit STORM citation mappings and persist claim-support decisions."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


CITATION_RE = re.compile(r"\[(\d+)\]")


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            self.parts.append(data)


def audit_citations(
    article_path: str | Path,
    sources_path: str | Path,
    claims_path: str | Path,
    *,
    output_path: str | Path | None = None,
    run_path: str | Path | None = None,
    staging: bool = False,
) -> dict[str, Any]:
    """Audit one article and atomically write ``citation-audit.json``."""

    article = Path(article_path)
    sources_file = Path(sources_path)
    claims_file = Path(claims_path)
    if run_path is not None:
        selected_run_path = Path(run_path)
        output_root = selected_run_path.parent.parent
        control_dir = output_root / ".storm-run"
        root = control_dir / "staging" if staging else output_root
        run_path_is_safe = (
            selected_run_path.absolute() == (control_dir / "run.json").absolute()
            and not selected_run_path.is_symlink()
            and selected_run_path.is_file()
        )
    else:
        root = article.parent
        control_dir = root / ".storm-run"
        run_path_is_safe = not staging
    audit_path = (
        Path(output_path)
        if output_path is not None
        else control_dir / "citation-audit.json"
    )
    errors: list[str] = []
    if not run_path_is_safe:
        errors.append("staging citation audit requires the in-scope .storm-run/run.json")
    audit_path_is_safe = (
        audit_path.absolute() == (control_dir / "citation-audit.json").absolute()
        and not audit_path.is_symlink()
        and not control_dir.is_symlink()
        and control_dir.is_dir()
    )
    if not audit_path_is_safe:
        errors.append("citation audit output must be .storm-run/citation-audit.json")

    if article.name not in {"storm_gen_article.html", "storm_gen_article_polished.html"}:
        errors.append("article must use a public STORM article filename")
    if not _is_direct_non_symlink_file(article, root):
        errors.append("article must be a direct non-symlink file in the output directory")
        article_text = ""
    else:
        try:
            article_text = article.read_bytes().decode("utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"article: {exc}")
            article_text = ""

    sources = _load_json_list(sources_file, control_dir, "sources", errors)
    claims = _load_json_list(claims_file, control_dir, "claims", errors)
    try:
        visible_text = _visible_article_text(article_text)
    except Exception as exc:  # A malformed document must not pass citation gates.
        errors.append(f"article: unable to parse visible text: {exc}")
        visible_text = ""
    used_ids = sorted({int(value) for value in CITATION_RE.findall(visible_text)})

    if not used_ids:
        errors.append("article contains no citation ids")

    source_counts: dict[int, int] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"source {index}: must be an object")
            continue
        source_id = source.get("id", source.get("source_id"))
        if isinstance(source_id, bool) or not isinstance(source_id, int):
            errors.append(f"source {index}: id must be a positive integer")
            continue
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        if source_id <= 0:
            errors.append(f"source {index}: id must be positive")
        if not str(source.get("title", "")).strip():
            errors.append(f"source {source_id}: missing title")
        if not any(
            str(source.get(field, "")).strip()
            for field in ("url", "url_or_doc_id", "document_id", "doc_id")
        ):
            errors.append(f"source {source_id}: missing URL or document id")

    duplicate_ids = sorted(source_id for source_id, count in source_counts.items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate source ids: {duplicate_ids}")
    unique_source_ids = sorted(source_counts)
    if unique_source_ids != list(range(1, len(unique_source_ids) + 1)):
        errors.append("source ids must be consecutive positive integers starting at 1")

    if used_ids and used_ids != list(range(1, max(used_ids) + 1)):
        errors.append("used citation ids must be consecutive positive integers starting at 1")
    for citation_id in used_ids:
        if citation_id <= 0:
            errors.append(f"citation id {citation_id} is out of range")
        if source_counts.get(citation_id, 0) != 1:
            errors.append(f"citation id {citation_id} does not map to exactly one source")

    used_id_set = set(used_ids)
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("id", source.get("source_id"))
        explicitly_unused = (
            source.get("unused_evidence") is True or source.get("status") == "unused"
        )
        if isinstance(source_id, int) and source_id not in used_id_set and not explicitly_unused:
            errors.append(f"source id {source_id} is dangling and not marked unused evidence")

    audited_ids: set[int] = set()
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty list")
        claims = []
    for index, claim in enumerate(claims):
        label = f"claim {index}"
        if not isinstance(claim, dict):
            errors.append(f"{label}: must be an object")
            continue
        if not str(claim.get("claim", "")).strip():
            errors.append(f"{label}: missing claim text")
        citation_ids = claim.get("citation_ids")
        source_mapping_ids = claim.get("source_ids")
        if not _is_positive_integer_list(citation_ids):
            errors.append(f"{label}: citation_ids must be a non-empty positive integer list")
            citation_ids = []
        elif len(citation_ids) != len(set(citation_ids)):
            errors.append(f"{label}: citation_ids must be unique")
        if not _is_positive_integer_list(source_mapping_ids):
            errors.append(f"{label}: source_ids must be a non-empty positive integer list")
            source_mapping_ids = []
        elif len(source_mapping_ids) != len(set(source_mapping_ids)):
            errors.append(f"{label}: source_ids must be unique")
        if set(citation_ids) != set(source_mapping_ids):
            errors.append(f"{label}: citation_ids and source_ids must map one-to-one")
        for citation_id in citation_ids:
            audited_ids.add(citation_id)
            if citation_id not in used_id_set:
                errors.append(f"{label}: citation id {citation_id} is not used by the article")
            if source_counts.get(citation_id, 0) != 1:
                errors.append(f"{label}: citation id {citation_id} lacks exactly one source")
        if claim.get("support_status") != "supported":
            errors.append(f"{label}: support_status must be supported")
        if not str(claim.get("evidence_note", "")).strip():
            errors.append(f"{label}: missing evidence_note")
        if not str(claim.get("action", "")).strip():
            errors.append(f"{label}: missing action")

    missing_claim_decisions = sorted(used_id_set - audited_ids)
    if missing_claim_decisions:
        errors.append(f"citation ids without persisted claim decisions: {missing_claim_decisions}")

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "valid": not errors,
        "article": article.name,
        "used_citation_ids": used_ids,
        "sources": sources,
        "claims": claims,
        "errors": errors,
    }
    if audit_path_is_safe:
        try:
            _atomic_write_json(audit_path, report)
        except OSError as exc:
            errors.append(f"citation audit atomic write failed: {exc}")
            report["valid"] = False
    return report


def _is_direct_non_symlink_file(path: Path, parent: Path) -> bool:
    return (
        path.parent.absolute() == parent.absolute()
        and not path.is_symlink()
        and not parent.is_symlink()
        and path.is_file()
    )


def _visible_article_text(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts)


def _load_json_list(
    path: Path, control_dir: Path, key: str, errors: list[str]
) -> list[Any]:
    if not _is_direct_non_symlink_file(path, control_dir):
        errors.append(f"{key}: input must be a direct non-symlink file in .storm-run")
        return []
    try:
        document = json.loads(path.read_bytes().decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{key}: {exc}")
        return []
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        errors.append(f"{key}: JSON must contain a {key} list")
        return []
    return document[key]


def _is_positive_integer_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in value
        )
    )


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=False, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--output", dest="output_path")
    parser.add_argument("--run", dest="run_path")
    parser.add_argument("--staging", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = audit_citations(
        args.article,
        args.sources,
        args.claims,
        output_path=args.output_path,
        run_path=args.run_path,
        staging=args.staging,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
