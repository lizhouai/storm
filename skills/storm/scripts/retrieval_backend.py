#!/usr/bin/env python3
"""Build and query traceable STORM retrieval indexes without required packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "1.0"
BACKENDS = ("host", "lexical")
ALGORITHMS = {
    "host": "host-ranked-passthrough-v1",
    "lexical": "bm25-unicode-v1",
}
DOCUMENT_FIELDS = {"source_id", "title", "url", "text"}
INDEX_FIELDS = {
    "schema_version",
    "backend_requested",
    "backend_used",
    "algorithm",
    "model",
    "provider_version",
    "fallback_reason",
    "chunking",
    "corpus_hash",
    "chunks",
}
CHUNK_FIELDS = {"source_id", "chunk_id", "title", "url", "snippet", "snippet_hash"}


class RetrievalError(ValueError):
    """Raised when retrieval inputs or optional backends are unsafe or invalid."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
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


def require_output_permission(path: Path, *, replace: bool, label: str) -> None:
    if (path.exists() or path.is_symlink()) and not replace:
        raise RetrievalError(f"{label} already exists; pass the explicit replace flag")
    if path.exists() and path.is_dir():
        raise RetrievalError(f"{label} must be a file path, not a directory")


def read_text(path: Path, label: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError as exc:
        raise RetrievalError(f"{label} does not exist: {path}") from exc
    except UnicodeDecodeError as exc:
        raise RetrievalError(f"{label} must be strict UTF-8: {path}") from exc
    except OSError as exc:
        raise RetrievalError(f"cannot read {label}: {path}: {exc}") from exc


def read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(read_text(path, label).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RetrievalError(f"{label} line {line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise RetrievalError(f"{label} line {line_number} must be an object")
        rows.append(row)
    if not rows:
        raise RetrievalError(f"{label} must contain at least one object")
    return rows


def require_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise RetrievalError(f"{label} must be a non-empty string")
    return value.strip() if not allow_empty else value


def load_documents(path: Path) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    source_ids: set[str] = set()
    for index, row in enumerate(read_jsonl(path, "corpus"), start=1):
        unknown = set(row) - DOCUMENT_FIELDS
        missing = {"source_id", "text"} - set(row)
        if unknown or missing:
            raise RetrievalError(
                f"corpus row {index} fields are invalid; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        source_id = require_string(row["source_id"], f"corpus row {index} source_id")
        if source_id in source_ids:
            raise RetrievalError(f"duplicate corpus source_id: {source_id!r}")
        source_ids.add(source_id)
        text = require_string(row["text"], f"corpus row {index} text")
        title = row.get("title", source_id)
        url = row.get("url", "")
        if not isinstance(title, str) or not title.strip():
            raise RetrievalError(f"corpus row {index} title must be a non-empty string")
        if not isinstance(url, str):
            raise RetrievalError(f"corpus row {index} url must be a string")
        documents.append(
            {"source_id": source_id, "title": title.strip(), "url": url.strip(), "text": text}
        )
    return documents


def chunk_documents(
    documents: list[dict[str, str]], chunk_size: int, chunk_overlap: int
) -> list[dict[str, Any]]:
    if chunk_size < 32:
        raise RetrievalError("chunk size must be at least 32 Unicode code points")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise RetrievalError("chunk overlap must be non-negative and smaller than chunk size")
    step = chunk_size - chunk_overlap
    chunks: list[dict[str, Any]] = []
    for document in documents:
        text = document["text"]
        chunk_number = 0
        for offset in range(0, len(text), step):
            snippet = text[offset : offset + chunk_size].strip()
            if not snippet:
                continue
            chunk_number += 1
            chunks.append(
                {
                    "source_id": document["source_id"],
                    "chunk_id": f"{document['source_id']}#{chunk_number:04d}",
                    "title": document["title"],
                    "url": document["url"],
                    "snippet": snippet,
                    "snippet_hash": sha256_text(snippet),
                }
            )
            if offset + chunk_size >= len(text):
                break
    if not chunks:
        raise RetrievalError("corpus did not produce any non-empty chunks")
    return chunks


def lexical_terms(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    terms = re.findall(r"[a-z0-9]+", normalized)
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        terms.extend(current)
        terms.extend("".join(current[index : index + 2]) for index in range(len(current) - 1))
        current.clear()

    for character in normalized:
        if ord(character) > 127 and unicodedata.category(character)[0] in {"L", "N"}:
            current.append(character)
        else:
            flush()
    flush()
    return terms


def lexical_scores(chunks: list[dict[str, Any]], query: str) -> list[float]:
    query_terms = Counter(lexical_terms(query))
    if not query_terms:
        raise RetrievalError("query must contain searchable letters or numbers")
    document_terms = [Counter(lexical_terms(chunk["snippet"])) for chunk in chunks]
    lengths = [sum(terms.values()) for terms in document_terms]
    average_length = sum(lengths) / len(lengths)
    document_frequency = {
        term: sum(1 for terms in document_terms if term in terms) for term in query_terms
    }
    scores: list[float] = []
    for terms, length in zip(document_terms, lengths):
        score = 0.0
        for term, query_frequency in query_terms.items():
            term_frequency = terms.get(term, 0)
            if term_frequency == 0:
                continue
            frequency = document_frequency[term]
            inverse_frequency = math.log(
                1.0 + (len(chunks) - frequency + 0.5) / (frequency + 0.5)
            )
            denominator = term_frequency + 1.2 * (
                1.0 - 0.75 + 0.75 * length / average_length
            )
            score += query_frequency * inverse_frequency * (
                term_frequency * (1.2 + 1.0) / denominator
            )
        scores.append(round(score, 12))
    return scores


def build_index(args: argparse.Namespace) -> dict[str, Any]:
    require_output_permission(args.output, replace=args.replace, label="retrieval index output")
    documents = load_documents(args.corpus)
    chunks = chunk_documents(documents, args.chunk_size, args.chunk_overlap)
    backend_requested = args.backend
    backend_used = backend_requested
    fallback_reason: str | None = None
    model: str | None = None
    provider_version = "python-stdlib" if backend_requested == "lexical" else "host-managed"

    index = {
        "schema_version": SCHEMA_VERSION,
        "backend_requested": backend_requested,
        "backend_used": backend_used,
        "algorithm": ALGORITHMS[backend_used],
        "model": model,
        "provider_version": provider_version,
        "fallback_reason": fallback_reason,
        "chunking": {
            "size": args.chunk_size,
            "overlap": args.chunk_overlap,
            "unit": "unicode-codepoints",
        },
        "corpus_hash": sha256_text(canonical_json(documents)),
        "chunks": chunks,
    }
    atomic_write_text(args.output, json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return index


def load_index(path: Path) -> dict[str, Any]:
    try:
        index = json.loads(read_text(path, "retrieval index"))
    except json.JSONDecodeError as exc:
        raise RetrievalError("retrieval index is not valid JSON") from exc
    if not isinstance(index, dict) or set(index) != INDEX_FIELDS:
        raise RetrievalError("retrieval index fields are invalid")
    if index["schema_version"] != SCHEMA_VERSION:
        raise RetrievalError(f"unsupported retrieval index schema: {index['schema_version']!r}")
    if index["backend_requested"] not in BACKENDS or index["backend_used"] not in BACKENDS:
        raise RetrievalError("retrieval index backend is invalid")
    if index["algorithm"] != ALGORITHMS[index["backend_used"]]:
        raise RetrievalError("retrieval index algorithm does not match its backend")
    backend_requested = index["backend_requested"]
    backend_used = index["backend_used"]
    fallback_reason = index["fallback_reason"]
    if backend_requested != backend_used or fallback_reason is not None:
        raise RetrievalError("retrieval index fallback metadata is inconsistent")
    if index["model"] is not None:
        raise RetrievalError("retrieval index must not record a model")
    if backend_requested == "lexical" and index["provider_version"] != "python-stdlib":
        raise RetrievalError("lexical retrieval index provider version is invalid")
    if backend_requested == "host" and index["provider_version"] != "host-managed":
        raise RetrievalError("host retrieval index provider version is invalid")
    corpus_hash = index["corpus_hash"]
    if not isinstance(corpus_hash, str) or re.fullmatch(r"[0-9a-f]{64}", corpus_hash) is None:
        raise RetrievalError("retrieval index corpus hash is invalid")
    chunking = index["chunking"]
    if not isinstance(chunking, dict) or set(chunking) != {"size", "overlap", "unit"}:
        raise RetrievalError("retrieval index chunking fields are invalid")
    if chunking["unit"] != "unicode-codepoints":
        raise RetrievalError("retrieval index chunk unit is unsupported")
    chunk_size = chunking["size"]
    chunk_overlap = chunking["overlap"]
    if (
        isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or chunk_size < 32
        or isinstance(chunk_overlap, bool)
        or not isinstance(chunk_overlap, int)
        or chunk_overlap < 0
        or chunk_overlap >= chunk_size
    ):
        raise RetrievalError("retrieval index chunk parameters are invalid")
    chunks = index["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise RetrievalError("retrieval index requires non-empty chunks")
    chunk_ids: set[str] = set()
    for position, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict) or set(chunk) != CHUNK_FIELDS:
            raise RetrievalError(f"retrieval index chunk {position} fields are invalid")
        for field in CHUNK_FIELDS - {"url"}:
            require_string(chunk[field], f"retrieval index chunk {position} {field}")
        if not isinstance(chunk["url"], str):
            raise RetrievalError(f"retrieval index chunk {position} url must be a string")
        if chunk["snippet_hash"] != sha256_text(chunk["snippet"]):
            raise RetrievalError(f"retrieval index chunk {position} snippet hash is invalid")
        if chunk["chunk_id"] in chunk_ids:
            raise RetrievalError(f"duplicate retrieval index chunk id: {chunk['chunk_id']!r}")
        chunk_ids.add(chunk["chunk_id"])
    return index


def host_scores(
    chunks: list[dict[str, Any]], host_results_path: Path | None
) -> list[tuple[dict[str, Any], float]]:
    if host_results_path is None:
        raise RetrievalError("host backend requires --host-results")
    by_chunk = {chunk["chunk_id"]: chunk for chunk in chunks}
    by_source: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk["source_id"], []).append(chunk)
    selected: list[tuple[dict[str, Any], float]] = []
    seen: set[str] = set()
    for position, row in enumerate(read_jsonl(host_results_path, "host results"), start=1):
        if set(row) - {"source_id", "chunk_id", "score"} or "source_id" not in row or "score" not in row:
            raise RetrievalError(f"host result {position} fields are invalid")
        source_id = require_string(row["source_id"], f"host result {position} source_id")
        chunk_id = row.get("chunk_id")
        if chunk_id is not None:
            chunk_id = require_string(chunk_id, f"host result {position} chunk_id")
            chunk = by_chunk.get(chunk_id)
            if chunk is None or chunk["source_id"] != source_id:
                raise RetrievalError(f"host result {position} does not resolve to an indexed chunk")
        else:
            candidates = by_source.get(source_id, [])
            if not candidates:
                raise RetrievalError(f"host result {position} source is not indexed: {source_id!r}")
            if len(candidates) != 1:
                raise RetrievalError(
                    f"host result {position} must include chunk_id for a multi-chunk source"
                )
            chunk = candidates[0]
        score = row["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            raise RetrievalError(f"host result {position} score must be a finite number")
        if chunk["chunk_id"] in seen:
            raise RetrievalError(f"duplicate host result chunk: {chunk['chunk_id']!r}")
        seen.add(chunk["chunk_id"])
        selected.append((chunk, float(score)))
    return selected


def ranked_chunks(
    index: dict[str, Any], args: argparse.Namespace
) -> tuple[list[tuple[dict[str, Any], float]], str, str | None]:
    chunks = index["chunks"]
    backend = index["backend_used"]
    fallback_reason = index["fallback_reason"]
    if backend == "host":
        return host_scores(chunks, args.host_results), "host", fallback_reason
    scores = lexical_scores(chunks, args.query)
    ranked = [(chunk, score) for chunk, score in zip(chunks, scores) if score > 0.0]
    ranked.sort(key=lambda item: (-item[1], item[0]["source_id"], item[0]["chunk_id"]))
    return ranked, backend, fallback_reason


def result_row(chunk: dict[str, Any], score: float, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "score": float(score),
        "source_id": chunk["source_id"],
        "chunk_id": chunk["chunk_id"],
        "title": chunk["title"],
        "url": chunk["url"],
        "snippet": chunk["snippet"],
        "snippet_hash": chunk["snippet_hash"],
    }


def write_trace(path: Path, records: list[dict[str, Any]], replace: bool) -> None:
    previous: list[dict[str, Any]] = []
    if path.exists() and not replace:
        previous = read_jsonl(path, "existing retrieval trace")
    lines = [canonical_json(record) for record in previous + records]
    atomic_write_text(path, "\n".join(lines) + "\n")


def search_index(args: argparse.Namespace) -> dict[str, Any]:
    query = require_string(args.query, "query")
    if args.top_k < 1:
        raise RetrievalError("top-k must be at least 1")
    if args.output is not None:
        require_output_permission(
            args.output, replace=args.replace_output, label="retrieval search output"
        )
    index = load_index(args.index)
    ranked, effective_backend, search_fallback = ranked_chunks(index, args)
    results = [
        result_row(chunk, score, rank)
        for rank, (chunk, score) in enumerate(ranked[: args.top_k], start=1)
    ]
    index_hash = sha256_text(canonical_json(index))
    fallback_reason = search_fallback or index["fallback_reason"]
    algorithm = ALGORITHMS[effective_backend]
    report = {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "backend_requested": index["backend_requested"],
        "backend_used": effective_backend,
        "algorithm": algorithm,
        "model": index["model"],
        "provider_version": index["provider_version"],
        "fallback_reason": fallback_reason,
        "top_k": args.top_k,
        "chunking": {"size": index["chunking"]["size"], "overlap": index["chunking"]["overlap"]},
        "index_hash": index_hash,
        "results": results,
    }
    if args.trace is not None:
        query_id = sha256_text(f"{index_hash}\n{query}")
        trace_records = [
            {
                "schema_version": SCHEMA_VERSION,
                "query_id": query_id,
                "query": query,
                "backend_requested": report["backend_requested"],
                "backend_used": effective_backend,
                "algorithm": algorithm,
                "model": report["model"],
                "provider_version": report["provider_version"],
                "fallback_reason": fallback_reason,
                "top_k": args.top_k,
                "chunk_size": index["chunking"]["size"],
                "chunk_overlap": index["chunking"]["overlap"],
                "chunk_unit": index["chunking"]["unit"],
                "index_hash": index_hash,
                **result,
            }
            for result in results
        ]
        write_trace(args.trace, trace_records, args.replace_trace)
    if args.output is not None:
        atomic_write_text(args.output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Build a traceable corpus index")
    index_parser.add_argument("--backend", choices=BACKENDS, required=True)
    index_parser.add_argument("--corpus", type=Path, required=True)
    index_parser.add_argument("--output", type=Path, required=True)
    index_parser.add_argument("--chunk-size", type=int, default=1200)
    index_parser.add_argument("--chunk-overlap", type=int, default=200)
    index_parser.add_argument("--replace", action="store_true")
    index_parser.set_defaults(handler=build_index)

    search_parser = subparsers.add_parser("search", help="Search an index and emit trace rows")
    search_parser.add_argument("--index", type=Path, required=True)
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--trace", type=Path)
    search_parser.add_argument("--replace-trace", action="store_true")
    search_parser.add_argument("--output", type=Path)
    search_parser.add_argument("--replace-output", action="store_true")
    search_parser.add_argument("--host-results", type=Path)
    search_parser.set_defaults(handler=search_index)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = args.handler(args)
    except (RetrievalError, OSError) as exc:
        print(f"retrieval backend error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
