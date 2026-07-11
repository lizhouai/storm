#!/usr/bin/env python3
"""Validate the public STORM artifact bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PUBLIC_ARTIFACT_NAMES = (
    "direct_gen_outline.html",
    "storm_gen_outline.html",
    "storm_gen_article.html",
    "storm_gen_article_polished.html",
)
KNOWN_MOJIBAKE_MARKERS = (
    "\ufffd",
    "\u00e2\u20ac\u2122",
    "\u00e2\u20ac\u0153",
    "\u00e2\u20ac",
    "\u00ef\u00bf\u00bd",
)
TRUNCATION_RE = re.compile(
    r"(?:\[\s*truncated\s*\]|<\s*truncated\s*>|output\s+truncated|content\s+truncated)",
    re.IGNORECASE,
)


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self._in_title = False
        self.doctype_html = False
        self.charset_utf8 = False
        self.tag_counts: dict[str, int] = {}
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self.reference_list_items = 0
        self._in_reference_section = False

    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _ACTIVE_TAGS = {"script", "iframe", "object", "embed", "form", "base"}
    _URL_ATTRIBUTES = {"href", "src", "action", "formaction", "poster", "xlink:href"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        normalized_attrs = {key.lower(): value for key, value in attrs}
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_tag = tag
            self._heading_parts = []
        if tag == "li" and self._in_reference_section:
            self.reference_list_items += 1

        if tag == "meta" and (normalized_attrs.get("charset") or "").lower() == "utf-8":
            self.charset_utf8 = True

        if tag in self._ACTIVE_TAGS:
            self.errors.append(f"unsafe active tag <{tag}>")
        for key, value in normalized_attrs.items():
            if key.startswith("on"):
                self.errors.append(f"unsafe event-handler attribute {key}")
            if key in self._URL_ATTRIBUTES and value and _has_unsafe_url_scheme(value):
                self.errors.append(f"unsafe URL scheme in {key}")

        if tag not in self._VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if self._heading_tag == tag:
            heading_text = " ".join("".join(self._heading_parts).split())
            self.headings.append((int(tag[1]), heading_text))
            self._in_reference_section = _is_reference_heading(heading_text)
            self._heading_tag = None
            self._heading_parts = []
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unbalanced closing tag </{tag}>")
            return
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._heading_tag is not None:
            self._heading_parts.append(data)

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() == "doctype html":
            self.doctype_html = True

    def finish(self) -> None:
        if self.stack:
            self.errors.append(f"unclosed tag <{self.stack[-1]}>")


def _has_unsafe_url_scheme(value: str) -> bool:
    candidate = "".join(character for character in value.strip() if ord(character) > 32)
    scheme = urlsplit(candidate).scheme.lower()
    return bool(scheme and scheme not in {"http", "https"})


def _normalize_heading(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_reference_heading(value: str) -> bool:
    return _normalize_heading(value) in {
        "reference",
        "references",
        "sources",
        "\u53c2\u8003\u6587\u732e",
        "\u53c2\u8003\u8d44\u6599",
    }


def validate_artifacts(
    output_dir: str | Path,
    *,
    topic: str | None = None,
    run_path: str | Path | None = None,
    staging: bool = False,
) -> dict[str, Any]:
    """Validate four HTML artifacts and return their SHA-256 hashes."""

    root = Path(output_dir)
    errors: list[str] = []
    artifacts: dict[str, dict[str, str]] = {}

    if root.is_symlink() or not root.is_dir():
        return {
            "valid": False,
            "errors": ["output directory must be an existing non-symlink directory"],
            "artifacts": {},
        }

    artifact_root = root / ".storm-run" / "staging" if staging else root
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        return {
            "valid": False,
            "errors": ["artifact directory must be an existing non-symlink directory"],
            "artifacts": {},
        }

    expected = set(PUBLIC_ARTIFACT_NAMES)
    actual = {
        entry.name
        for entry in artifact_root.iterdir()
        if staging or entry.name != ".storm-run"
    }
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            errors.append(f"missing public artifacts: {', '.join(missing)}")
        if extra:
            errors.append(f"unexpected public artifacts: {', '.join(extra)}")

    state: dict[str, Any] | None = None
    selected_run_path: Path | None = None
    default_run_path = root / ".storm-run" / "run.json"
    if run_path is not None or default_run_path.exists():
        selected_run_path = Path(run_path) if run_path is not None else default_run_path
        expected_run_path = root / ".storm-run" / "run.json"
        if (
            selected_run_path.absolute() != expected_run_path.absolute()
            or selected_run_path.is_symlink()
            or selected_run_path.parent.is_symlink()
        ):
            errors.append("run.json must be the non-symlink .storm-run/run.json inside output")
        else:
            try:
                state = json.loads(selected_run_path.read_bytes().decode("utf-8", errors="strict"))
                if not isinstance(state, dict) or not isinstance(state.get("artifacts"), dict):
                    raise ValueError("run.json must contain an artifacts object")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"run.json: {exc}")
                state = None

    resolved_topic = topic
    if resolved_topic is None and state is not None and isinstance(state.get("topic"), str):
        resolved_topic = state["topic"]

    for name in PUBLIC_ARTIFACT_NAMES:
        path = artifact_root / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.parent.resolve() != artifact_root.resolve()
        ):
            errors.append(f"{name}: artifact must be a direct non-symlink file")
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{name}: {exc}")
            continue

        if not text.strip():
            errors.append(f"{name}: artifact is empty")
            continue
        marker = next((item for item in KNOWN_MOJIBAKE_MARKERS if item in text), None)
        if marker is not None:
            errors.append(f"{name}: replacement or mojibake marker detected")
            continue
        if TRUNCATION_RE.search(text):
            errors.append(f"{name}: obvious truncation marker detected")
            continue

        parser = _DocumentParser()
        try:
            parser.feed(text)
            parser.close()
            parser.finish()
        except Exception as exc:  # HTMLParser errors must fail closed.
            errors.append(f"{name}: invalid HTML: {exc}")
            continue

        title = " ".join("".join(parser.title_parts).split())
        if not title or title.casefold() in {"untitled", "title", "document"}:
            errors.append(f"{name}: missing meaningful title")
            continue
        if not parser.doctype_html:
            errors.append(f"{name}: missing HTML doctype")
        if not parser.charset_utf8:
            errors.append(f"{name}: missing <meta charset=\"utf-8\">")
        for tag in ("html", "head", "body", "title"):
            if parser.tag_counts.get(tag, 0) != 1:
                errors.append(f"{name}: expected exactly one <{tag}> element")
        errors.extend(f"{name}: {error}" for error in parser.errors)
        if parser.errors:
            continue

        if not parser.headings:
            errors.append(f"{name}: missing heading structure")
        previous_level = 0
        for level, heading in parser.headings:
            if level > 3:
                errors.append(f"{name}: only h1 through h3 headings are allowed")
            if previous_level == 0 and level != 1:
                errors.append(f"{name}: heading structure must start at h1")
            elif previous_level and level > previous_level + 1:
                errors.append(f"{name}: heading level skips from h{previous_level} to h{level}")
            if not heading:
                errors.append(f"{name}: empty heading")
            previous_level = level

        if name in {"direct_gen_outline.html", "storm_gen_outline.html"}:
            for _, heading in parser.headings:
                if _is_reference_heading(heading):
                    errors.append(f"{name}: outline must not contain a References heading")
                if resolved_topic and _normalize_heading(heading) == _normalize_heading(
                    resolved_topic
                ):
                    errors.append(f"{name}: outline must not duplicate the topic heading")

        if name == "storm_gen_article_polished.html":
            has_references = any(_is_reference_heading(item) for _, item in parser.headings)
            if not has_references or parser.reference_list_items == 0:
                errors.append(f"{name}: polished article requires a non-empty reference list")

        artifacts[name] = {
            "format": "html",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    if not errors and state is not None and selected_run_path is not None:
        try:
            import storm_state

            storm_state.record_artifacts(selected_run_path, artifacts)
        except (OSError, ValueError, storm_state.StateError) as exc:
            errors.append(f"run.json: guarded artifact update failed: {exc}")

    return {"valid": not errors, "errors": errors, "artifacts": artifacts}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", help="Resolved STORM output directory")
    parser.add_argument("--format", default="html", choices=("html",))
    parser.add_argument("--topic", help="Display topic used to reject duplicate outline headings")
    parser.add_argument("--run", dest="run_path", help="In-scope .storm-run/run.json to update")
    parser.add_argument(
        "--staging",
        action="store_true",
        help="validate .storm-run/staging while keeping run.json rooted in output_dir",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_artifacts(
        args.output_dir,
        topic=args.topic,
        run_path=args.run_path,
        staging=args.staging,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
