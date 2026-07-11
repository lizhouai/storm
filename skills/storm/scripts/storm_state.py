from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "1.0"
EXECUTION_BACKENDS = ("guarded-agent", "prompt-only", "local-runner")
STATE_FIELDS = {
    "schema_version",
    "run_id",
    "mode",
    "execution_backend",
    "topic",
    "artifact_slug",
    "phase",
    "status",
    "attempt",
    "next_action",
    "created_at",
    "updated_at",
    "artifacts",
    "metrics",
    "errors",
    "last_event_id",
}
STATUS_VALUES = {"running", "blocked", "failed", "cancelled", "complete"}
EVENT_FIELDS = {
    "event_id",
    "run_id",
    "event",
    "idempotency_key",
    "timestamp",
    "before_phase",
    "after_phase",
    "before_status",
    "after_status",
    "before_state_hash",
    "after_state_hash",
    "artifact_hashes",
    "error",
}
PHASE_ACTIONS = {
    "classic": {
        "INITIALIZED": "define_scope",
        "SCOPED": "generate_perspectives",
        "PERSPECTIVES_READY": "run_interviews",
        "INTERVIEWS_COMPLETE": "build_information_table",
        "INFORMATION_TABLE_READY": "generate_direct_outline",
        "DIRECT_OUTLINE_READY": "refine_outline",
        "REFINED_OUTLINE_READY": "write_draft",
        "DRAFT_READY": "polish_article",
        "POLISHED": "verify_artifacts",
        "VERIFIED": "publish",
        "COMPLETE": None,
    },
    "co-storm": {
        "INITIALIZED": "run_warm_start",
        "WARM_START_RUNNING": "complete_warm_start",
        "INTERACTIVE": "continue_roundtable",
        "REPORTING": "verify_report",
        "VERIFIED": "publish",
        "COMPLETE": None,
    },
}
TRANSITIONS = {
    "classic": {
        "INITIALIZED": ("scope_defined", "SCOPED"),
        "SCOPED": ("perspectives_ready", "PERSPECTIVES_READY"),
        "PERSPECTIVES_READY": ("interviews_completed", "INTERVIEWS_COMPLETE"),
        "INTERVIEWS_COMPLETE": ("information_table_ready", "INFORMATION_TABLE_READY"),
        "INFORMATION_TABLE_READY": ("direct_outline_ready", "DIRECT_OUTLINE_READY"),
        "DIRECT_OUTLINE_READY": ("refined_outline_ready", "REFINED_OUTLINE_READY"),
        "REFINED_OUTLINE_READY": ("draft_ready", "DRAFT_READY"),
        "DRAFT_READY": ("polished", "POLISHED"),
        "POLISHED": ("verified", "VERIFIED"),
        "VERIFIED": ("completed", "COMPLETE"),
    },
    "co-storm": {
        "INITIALIZED": ("warm_start_started", "WARM_START_RUNNING"),
        "WARM_START_RUNNING": ("warm_start_completed", "INTERACTIVE"),
        "INTERACTIVE": ("reporting_started", "REPORTING"),
        "REPORTING": ("verified", "VERIFIED"),
        "VERIFIED": ("completed", "COMPLETE"),
    },
}


class StateError(ValueError):
    """Raised when guarded state cannot be safely read or changed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def slugify(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.casefold()).strip("-")
    return slug or "storm-research"


def atomic_write_text(path: Path, text: str) -> None:
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
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def initial_next_action(mode: str) -> str:
    return "define_scope" if mode == "classic" else "run_warm_start"


def artifact_hashes(state: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, metadata in state["artifacts"].items():
        if isinstance(metadata, dict) and isinstance(metadata.get("sha256"), str):
            hashes[name] = metadata["sha256"]
    return hashes


def parse_timestamp(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise StateError(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateError(f"{field} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise StateError(f"{field} must include a timezone")


def validate_state_shape(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise StateError("run state must be a JSON object")
    actual_fields = set(state)
    if actual_fields != STATE_FIELDS:
        missing = sorted(STATE_FIELDS - actual_fields)
        unknown = sorted(actual_fields - STATE_FIELDS)
        raise StateError(f"run state fields are invalid; missing={missing}, unknown={unknown}")
    if state["schema_version"] != SCHEMA_VERSION:
        raise StateError(f"unsupported schema_version: {state['schema_version']!r}")
    if not isinstance(state["run_id"], str) or not state["run_id"].startswith("storm-"):
        raise StateError("run_id is invalid")
    try:
        parsed_id = uuid.UUID(state["run_id"].removeprefix("storm-"))
    except (ValueError, AttributeError) as error:
        raise StateError("run_id is invalid") from error
    if str(parsed_id) != state["run_id"].removeprefix("storm-"):
        raise StateError("run_id must use the canonical lowercase UUID form")
    mode = state["mode"]
    if mode not in PHASE_ACTIONS:
        raise StateError(f"unknown mode: {mode!r}")
    if state["execution_backend"] not in EXECUTION_BACKENDS:
        raise StateError(f"unknown execution_backend: {state['execution_backend']!r}")
    if not isinstance(state["topic"], str) or not state["topic"].strip():
        raise StateError("topic must not be empty")
    if not isinstance(state["artifact_slug"], str) or not state["artifact_slug"].strip():
        raise StateError("artifact_slug must not be empty")
    phase = state["phase"]
    if phase not in PHASE_ACTIONS[mode]:
        raise StateError(f"unknown phase for {mode}: {phase!r}")
    status = state["status"]
    if status not in STATUS_VALUES:
        raise StateError(f"unknown status: {status!r}")
    if isinstance(state["attempt"], bool) or not isinstance(state["attempt"], int) or state["attempt"] < 1:
        raise StateError("attempt must be a positive integer")
    if state["next_action"] != PHASE_ACTIONS[mode][phase]:
        raise StateError(
            f"next_action {state['next_action']!r} does not match phase {phase!r}"
        )
    if phase == "COMPLETE" and status != "complete":
        raise StateError("COMPLETE phase requires complete status")
    if status == "complete" and phase != "COMPLETE":
        raise StateError("complete status requires COMPLETE phase")
    parse_timestamp(state["created_at"], "created_at")
    parse_timestamp(state["updated_at"], "updated_at")
    if not isinstance(state["artifacts"], dict) or not all(
        isinstance(name, str) and isinstance(metadata, dict)
        for name, metadata in state["artifacts"].items()
    ):
        raise StateError("artifacts must map names to objects")
    if not isinstance(state["metrics"], dict) or not all(
        isinstance(name, str)
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        for name, value in state["metrics"].items()
    ):
        raise StateError("metrics must map names to non-negative integers")
    if not isinstance(state["errors"], list) or not all(
        isinstance(error, dict) for error in state["errors"]
    ):
        raise StateError("errors must be an array of objects")
    if (
        isinstance(state["last_event_id"], bool)
        or not isinstance(state["last_event_id"], int)
        or state["last_event_id"] < 0
    ):
        raise StateError("last_event_id must be a non-negative integer")
    return state


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StateError(f"missing {label}: {path}") from error
    except UnicodeDecodeError as error:
        raise StateError(f"{label} is not strict UTF-8: {path}") from error
    except json.JSONDecodeError as error:
        raise StateError(f"{label} is not valid JSON: {path}: {error.msg}") from error


def read_event_log(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise StateError(f"missing event log: {path}") from error
    except UnicodeDecodeError as error:
        raise StateError(f"event log is not strict UTF-8: {path}") from error
    if not lines:
        raise StateError("event log must not be empty")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise StateError(f"event log contains a blank line at {line_number}")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise StateError(
                f"event log line {line_number} is not valid JSON: {error.msg}"
            ) from error
        if not isinstance(event, dict):
            raise StateError(f"event log line {line_number} must be an object")
        events.append(event)
    return events


def validate_event_log(state: dict[str, Any], events: list[dict[str, Any]]) -> None:
    previous_after_hash = content_hash(None)
    previous_phase: str | None = None
    previous_status: str | None = None
    seen_keys: set[str] = set()
    for expected_id, event in enumerate(events, start=1):
        if set(event) != EVENT_FIELDS:
            raise StateError(f"event {expected_id} has invalid fields")
        if event.get("event_id") != expected_id:
            raise StateError("event ids must be monotonic and contiguous")
        if event.get("run_id") != state["run_id"]:
            raise StateError(f"event {expected_id} has the wrong run_id")
        key = event.get("idempotency_key")
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise StateError(f"event {expected_id} has an invalid idempotency_key")
        if key in seen_keys:
            raise StateError("event idempotency keys must be unique")
        seen_keys.add(key)
        if event.get("before_state_hash") != previous_after_hash:
            raise StateError(f"event {expected_id} breaks the state hash chain")
        after_hash = event.get("after_state_hash")
        if not isinstance(after_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", after_hash):
            raise StateError(f"event {expected_id} has an invalid after_state_hash")
        hashes = event.get("artifact_hashes")
        if not isinstance(hashes, dict) or not all(
            isinstance(name, str)
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for name, value in hashes.items()
        ):
            raise StateError(f"event {expected_id} has invalid artifact_hashes")
        parse_timestamp(event.get("timestamp"), f"event {expected_id} timestamp")
        before_phase = event.get("before_phase")
        after_phase = event.get("after_phase")
        before_status = event.get("before_status")
        after_status = event.get("after_status")
        event_name = event.get("event")
        if expected_id == 1:
            if (
                event_name != "initialized"
                or before_phase is not None
                or before_status is not None
                or after_phase != "INITIALIZED"
                or after_status != "running"
                or event.get("error") is not None
            ):
                raise StateError("invalid initial event")
        else:
            if before_phase != previous_phase or before_status != previous_status:
                raise StateError(f"event {expected_id} breaks phase/status continuity")
            transition = TRANSITIONS[state["mode"]].get(before_phase)
            if transition is not None and event_name == transition[0]:
                expected_after_status = "complete" if transition[1] == "COMPLETE" else "running"
                if (
                    after_phase != transition[1]
                    or after_status != expected_after_status
                    or event.get("error") is not None
                ):
                    raise StateError(f"event {expected_id} has invalid transition fields")
            elif event_name == "artifacts_validated":
                if (
                    after_phase != before_phase
                    or after_status != before_status
                    or event.get("error") is not None
                ):
                    raise StateError(
                        f"event {expected_id} has invalid artifact validation fields"
                    )
            elif event_name in {"failed", "blocked"}:
                expected_status = "failed" if event_name == "failed" else "blocked"
                error = event.get("error")
                if (
                    before_status != "running"
                    or after_phase != before_phase
                    or after_status != expected_status
                    or not isinstance(error, dict)
                    or error.get("kind") != expected_status
                ):
                    raise StateError(f"event {expected_id} has invalid interruption fields")
            elif event_name == "resumed":
                if (
                    before_status not in {"failed", "blocked"}
                    or after_phase != before_phase
                    or after_status != "running"
                    or event.get("error") is not None
                ):
                    raise StateError(f"event {expected_id} has invalid resume fields")
            else:
                raise StateError(f"event {expected_id} is invalid for phase {before_phase!r}")
        previous_after_hash = after_hash
        previous_phase = after_phase
        previous_status = after_status
    if len(events) != state["last_event_id"]:
        raise StateError("last_event_id does not match the event log")
    if previous_after_hash != content_hash(state):
        raise StateError("the current run state does not match the last event hash")
    if events[-1].get("after_phase") != state["phase"]:
        raise StateError("the current phase does not match the last event")
    if events[-1].get("after_status") != state["status"]:
        raise StateError("the current status does not match the last event")
    if events[-1].get("artifact_hashes") != artifact_hashes(state):
        raise StateError("artifact hashes do not match the last event")


def load_guarded_run(run_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = validate_state_shape(read_json(run_path, "run state"))
    events = read_event_log(run_path.parent / "event-log.jsonl")
    committed_count = state["last_event_id"]
    if len(events) < committed_count or len(events) > committed_count + 1:
        raise StateError("event log length is inconsistent with last_event_id")
    committed_events = events[:committed_count]
    validate_event_log(state, committed_events)
    if len(events) == committed_count + 1:
        pending = events[-1]
        if (
            pending.get("event_id") != committed_count + 1
            or pending.get("run_id") != state["run_id"]
            or pending.get("before_state_hash") != content_hash(state)
        ):
            raise StateError("event log contains an invalid uncommitted event")
    return state, committed_events


def status_run(args: argparse.Namespace) -> dict[str, Any]:
    state, _ = load_guarded_run(Path(args.run).resolve())
    return state


def validate_run(args: argparse.Namespace) -> dict[str, Any]:
    state, _ = load_guarded_run(Path(args.run).resolve())
    return {"valid": True, "run_id": state["run_id"]}


def event_key(command: str, payload: dict[str, Any]) -> str:
    return content_hash({"command": command, "payload": payload})


def load_perspectives(control_directory: Path) -> list[dict[str, Any]]:
    path = control_directory / "perspectives.json"
    raw = read_json(path, "perspective evidence")
    perspectives = raw.get("perspectives") if isinstance(raw, dict) else raw
    if not isinstance(perspectives, list) or not perspectives:
        raise StateError("perspectives.json must contain a non-empty perspective list")
    if not all(isinstance(item, dict) for item in perspectives):
        raise StateError("every perspective must be an object")
    role_ids: list[str] = []
    role_names: list[str] = []
    for perspective in perspectives:
        role_id = perspective.get("id", perspective.get("role_id"))
        role_name = perspective.get("role", perspective.get("display_name"))
        if not isinstance(role_id, str) or not role_id.strip():
            raise StateError("every perspective requires a stable non-empty id")
        if not isinstance(role_name, str) or not role_name.strip():
            raise StateError("every perspective requires a non-empty role")
        role_ids.append(role_id)
        role_names.append(role_name)
    if len(set(role_ids)) != len(role_ids):
        raise StateError("perspective role ids must be unique")
    if "basic fact writer" not in {name.casefold() for name in role_names}:
        raise StateError("perspectives must include Basic fact writer")
    return perspectives


def read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise StateError(f"missing {label}: {path}") from error
    except UnicodeDecodeError as error:
        raise StateError(f"{label} is not strict UTF-8: {path}") from error
    if not lines:
        raise StateError(f"{label} must not be empty: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise StateError(f"{label} contains a blank line at {line_number}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise StateError(
                f"{label} line {line_number} is not valid JSON: {error.msg}"
            ) from error
        if not isinstance(record, dict):
            raise StateError(f"{label} line {line_number} must be an object")
        records.append(record)
    return records


def check_interviews(control_directory: Path) -> None:
    perspectives = load_perspectives(control_directory)
    perspective_ids = {
        perspective.get("id", perspective.get("role_id"))
        for perspective in perspectives
    }
    retrieval_records = read_jsonl(
        control_directory / "retrieval-log.jsonl", "retrieval-log.jsonl"
    )
    source_ids = {
        record.get("source_id", record.get("id")) for record in retrieval_records
    }
    if None in source_ids or not all(
        isinstance(source_id, str) and source_id.strip() for source_id in source_ids
    ):
        raise StateError("every retrieval record requires a non-empty source_id")
    interviews = read_jsonl(
        control_directory / "interviews.jsonl", "interviews.jsonl"
    )
    observed_perspectives: set[str] = set()
    for turn in interviews:
        perspective_id = turn.get("perspective_id")
        if perspective_id not in perspective_ids:
            raise StateError(f"interview has unknown perspective_id: {perspective_id!r}")
        queries = turn.get("queries")
        if not isinstance(queries, list) or not any(
            isinstance(query, str) and query.strip() for query in queries
        ):
            raise StateError("every interview turn requires a non-empty query")
        turn_source_ids = turn.get("source_ids")
        if not isinstance(turn_source_ids, list) or not turn_source_ids:
            raise StateError("every interview turn requires at least one source_id")
        unresolved = set(turn_source_ids) - source_ids
        if unresolved:
            raise StateError(f"interview source ids are not resolvable: {sorted(unresolved)}")
        observed_perspectives.add(perspective_id)
    missing = perspective_ids - observed_perspectives
    if missing:
        raise StateError(f"required perspectives have no valid interview turn: {sorted(missing)}")


def check_information_table(control_directory: Path) -> None:
    retrieval_records = read_jsonl(
        control_directory / "retrieval-log.jsonl", "retrieval-log.jsonl"
    )
    source_ids = {
        record.get("source_id", record.get("id")) for record in retrieval_records
    }
    rows = read_jsonl(
        control_directory / "information-table.jsonl", "information-table.jsonl"
    )
    evidence_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        source_id = row.get("source_id")
        snippet = row.get("snippet")
        support_note = row.get(
            "claim_supported", row.get("support_note", row.get("claim"))
        )
        if not isinstance(source_id, str) or source_id not in source_ids:
            raise StateError(f"information-table source is not resolvable: {source_id!r}")
        if not isinstance(snippet, str) or not snippet.strip():
            raise StateError("every information-table row requires a non-empty snippet")
        if not isinstance(support_note, str) or not support_note.strip():
            raise StateError(
                "every information-table row requires a claim or support note"
            )
        key = (source_id, snippet.strip(), support_note.strip())
        if key in evidence_keys:
            raise StateError("information-table evidence must be deduplicated")
        evidence_keys.add(key)


def require_public_artifact(run_path: Path, base_name: str) -> Path:
    output_directory = run_path.parent.parent
    candidates = [
        candidate
        for candidate in output_directory.glob(f"{base_name}.*")
        if candidate.is_file()
    ]
    if len(candidates) != 1:
        raise StateError(
            f"expected exactly one non-empty {base_name} public artifact; found {len(candidates)}"
        )
    if candidates[0].stat().st_size == 0:
        raise StateError(f"public artifact is empty: {candidates[0]}")
    return candidates[0]


def check_transition_prerequisites(
    run_path: Path, state: dict[str, Any], event_name: str
) -> None:
    if state["mode"] == "classic" and event_name == "perspectives_ready":
        load_perspectives(run_path.parent)
    if state["mode"] == "classic" and event_name == "interviews_completed":
        check_interviews(run_path.parent)
    if state["mode"] == "classic" and event_name == "information_table_ready":
        check_information_table(run_path.parent)
    classic_artifact_events = {
        "direct_outline_ready": "direct_gen_outline",
        "refined_outline_ready": "storm_gen_outline",
        "draft_ready": "storm_gen_article",
        "polished": "storm_gen_article_polished",
    }
    if state["mode"] == "classic" and event_name in classic_artifact_events:
        require_public_artifact(run_path, classic_artifact_events[event_name])
    if state["mode"] == "classic" and event_name == "verified":
        for base_name in classic_artifact_events.values():
            require_public_artifact(run_path, base_name)
        read_json(run_path.parent / "citation-audit.json", "citation-audit.json")


def commit_state_change(
    run_path: Path,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    updated_state: dict[str, Any],
    event_name: str,
    idempotency_key: str,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = utc_now()
    updated_state["updated_at"] = timestamp
    updated_state["last_event_id"] = state["last_event_id"] + 1
    validate_state_shape(updated_state)
    event = {
        "event_id": updated_state["last_event_id"],
        "run_id": state["run_id"],
        "event": event_name,
        "idempotency_key": idempotency_key,
        "timestamp": timestamp,
        "before_phase": state["phase"],
        "after_phase": updated_state["phase"],
        "before_status": state["status"],
        "after_status": updated_state["status"],
        "before_state_hash": content_hash(state),
        "after_state_hash": content_hash(updated_state),
        "artifact_hashes": artifact_hashes(updated_state),
        "error": error,
    }
    event_log_path = run_path.parent / "event-log.jsonl"
    event_text = "".join(canonical_json(item) + "\n" for item in [*events, event])
    atomic_write_text(event_log_path, event_text)
    atomic_write_text(
        run_path, json.dumps(updated_state, ensure_ascii=False, indent=2) + "\n"
    )
    return updated_state


def record_artifacts(
    run_path: Path, artifacts: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Record validated public artifact metadata through the state hash chain."""
    run_path = run_path.resolve()
    state, events = load_guarded_run(run_path)
    normalized: dict[str, dict[str, str]] = {}
    for name, metadata in sorted(artifacts.items()):
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise StateError("artifact names must be direct relative filenames")
        if not isinstance(metadata, dict):
            raise StateError(f"artifact metadata must be an object: {name}")
        digest = metadata.get("sha256")
        artifact_format = metadata.get("format")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise StateError(f"artifact sha256 is invalid: {name}")
        if artifact_format != "html":
            raise StateError(f"artifact format is invalid: {name}")
        normalized[name] = {
            "path": name,
            "format": artifact_format,
            "sha256": digest,
        }

    updated_state = copy.deepcopy(state)
    for name, metadata in normalized.items():
        existing = updated_state["artifacts"].get(name, {})
        if not isinstance(existing, dict):
            existing = {}
        updated_state["artifacts"][name] = {**existing, **metadata}
    if updated_state["artifacts"] == state["artifacts"]:
        return state
    if state["status"] != "running":
        raise StateError(
            f"cannot change artifacts for a run with status {state['status']!r}"
        )

    key = event_key("record_artifacts", {"artifacts": normalized})
    if any(event.get("idempotency_key") == key for event in events):
        return state
    return commit_state_change(
        run_path,
        state,
        events,
        updated_state,
        "artifacts_validated",
        key,
    )


def advance_run(args: argparse.Namespace) -> dict[str, Any]:
    run_path = Path(args.run).resolve()
    state, events = load_guarded_run(run_path)
    key = event_key("advance", {"event": args.event})
    if any(event.get("idempotency_key") == key for event in events):
        return state
    known_events = {
        event_name
        for mode_transitions in TRANSITIONS.values()
        for event_name, _ in mode_transitions.values()
    }
    if args.event not in known_events:
        raise StateError(f"unknown transition event: {args.event!r}")
    if state["status"] != "running":
        raise StateError(f"cannot advance a run with status {state['status']!r}")
    transition = TRANSITIONS[state["mode"]].get(state["phase"])
    if transition is None or transition[0] != args.event:
        expected = transition[0] if transition is not None else None
        raise StateError(
            f"illegal transition from {state['phase']!r}: expected {expected!r}, got {args.event!r}"
        )
    check_transition_prerequisites(run_path, state, args.event)
    updated_state = copy.deepcopy(state)
    updated_state["phase"] = transition[1]
    updated_state["status"] = "complete" if transition[1] == "COMPLETE" else "running"
    updated_state["next_action"] = PHASE_ACTIONS[state["mode"]][transition[1]]
    return commit_state_change(
        run_path, state, events, updated_state, args.event, key
    )


def interrupt_run(
    run_path: Path, target_status: str, message: str
) -> dict[str, Any]:
    state, events = load_guarded_run(run_path)
    kind = "failure" if target_status == "failed" else "block"
    key = event_key(
        kind,
        {
            "message": message,
            "phase": state["phase"],
            "attempt": state["attempt"],
        },
    )
    if any(event.get("idempotency_key") == key for event in events):
        return state
    if state["status"] != "running":
        raise StateError(f"cannot {kind} a run with status {state['status']!r}")
    if state["phase"] == "COMPLETE":
        raise StateError("cannot interrupt a complete run")
    error_record = {
        "kind": target_status,
        "message": message,
        "phase": state["phase"],
        "attempt": state["attempt"],
        "timestamp": utc_now(),
    }
    updated_state = copy.deepcopy(state)
    updated_state["status"] = target_status
    updated_state["errors"].append(error_record)
    return commit_state_change(
        run_path,
        state,
        events,
        updated_state,
        "failed" if target_status == "failed" else "blocked",
        key,
        error_record,
    )


def fail_run(args: argparse.Namespace) -> dict[str, Any]:
    message = args.error.strip()
    if not message:
        raise StateError("error must not be empty")
    return interrupt_run(Path(args.run).resolve(), "failed", message)


def block_run(args: argparse.Namespace) -> dict[str, Any]:
    message = args.reason.strip()
    if not message:
        raise StateError("reason must not be empty")
    return interrupt_run(Path(args.run).resolve(), "blocked", message)


def resume_run(args: argparse.Namespace) -> dict[str, Any]:
    run_path = Path(args.run).resolve()
    state, events = load_guarded_run(run_path)
    if state["status"] == "running" and events[-1].get("event") == "resumed":
        return state
    if state["status"] not in {"failed", "blocked"}:
        raise StateError(
            f"only failed or blocked runs can resume; current status is {state['status']!r}"
        )
    key = event_key(
        "resume",
        {
            "from_status": state["status"],
            "phase": state["phase"],
            "attempt": state["attempt"],
        },
    )
    updated_state = copy.deepcopy(state)
    updated_state["status"] = "running"
    updated_state["attempt"] += 1
    return commit_state_change(
        run_path, state, events, updated_state, "resumed", key
    )


def initialize_run(args: argparse.Namespace) -> dict[str, Any]:
    topic = args.topic.strip()
    if not topic:
        raise StateError("topic must not be empty")
    output = Path(args.output).resolve()
    control_directory = output / ".storm-run"
    run_path = control_directory / "run.json"
    event_log_path = control_directory / "event-log.jsonl"
    if run_path.exists() or event_log_path.exists():
        raise StateError(f"refusing to overwrite existing run state in {control_directory}")

    timestamp = utc_now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"storm-{uuid.uuid4()}",
        "mode": args.mode,
        "execution_backend": args.execution_backend,
        "topic": topic,
        "artifact_slug": slugify(topic),
        "phase": "INITIALIZED",
        "status": "running",
        "attempt": 1,
        "next_action": initial_next_action(args.mode),
        "created_at": timestamp,
        "updated_at": timestamp,
        "artifacts": {},
        "metrics": {},
        "errors": [],
        "last_event_id": 1,
    }
    event = {
        "event_id": 1,
        "run_id": state["run_id"],
        "event": "initialized",
        "idempotency_key": content_hash(
            {"event": "initialized", "run_id": state["run_id"]}
        ),
        "timestamp": timestamp,
        "before_phase": None,
        "after_phase": "INITIALIZED",
        "before_status": None,
        "after_status": "running",
        "before_state_hash": content_hash(None),
        "after_state_hash": content_hash(state),
        "artifact_hashes": artifact_hashes(state),
        "error": None,
    }
    atomic_write_text(event_log_path, canonical_json(event) + "\n")
    atomic_write_text(run_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded STORM run state manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="initialize a guarded run")
    init_parser.add_argument("--mode", choices=("classic", "co-storm"), required=True)
    init_parser.add_argument("--topic", required=True)
    init_parser.add_argument("--output", required=True)
    init_parser.add_argument(
        "--execution-backend",
        choices=EXECUTION_BACKENDS,
        default="guarded-agent",
    )
    init_parser.set_defaults(handler=initialize_run)
    for command, handler in (("status", status_run), ("validate", validate_run)):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--run", required=True)
        command_parser.set_defaults(handler=handler)
    advance_parser = subparsers.add_parser("advance")
    advance_parser.add_argument("--run", required=True)
    advance_parser.add_argument("--event", required=True)
    advance_parser.set_defaults(handler=advance_run)
    fail_parser = subparsers.add_parser("fail")
    fail_parser.add_argument("--run", required=True)
    fail_parser.add_argument("--error", required=True)
    fail_parser.set_defaults(handler=fail_run)
    block_parser = subparsers.add_parser("block")
    block_parser.add_argument("--run", required=True)
    block_parser.add_argument("--reason", required=True)
    block_parser.set_defaults(handler=block_run)
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run", required=True)
    resume_parser.set_defaults(handler=resume_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except StateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
