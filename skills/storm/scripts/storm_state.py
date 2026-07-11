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
CO_STORM_TURN_PAYLOAD_FIELDS = {
    "turn_id",
    "input_event",
    "policy",
    "participants",
    "retrieval_records",
    "mind_map_delta",
    "citations",
    "next_actions",
}
CO_STORM_TURN_ENTRY_FIELDS = CO_STORM_TURN_PAYLOAD_FIELDS | {
    "run_id",
    "phase",
    "timestamp",
    "previous_turn_hash",
    "turn_hash",
}
CO_STORM_INPUT_EVENTS = {
    "USER_ASK",
    "USER_STEER",
    "USER_OBSERVE",
    "EXPERT_ANSWER",
    "SPECIALIST_RESPOND",
    "MODERATOR_BROADEN",
    "USER_CONCLUDE",
}
CO_STORM_POLICIES = {
    "QUESTION_ANSWERING",
    "QUESTION_ASKING",
    "MODERATOR_BROADENING",
    "FINAL_REPORT",
}
CO_STORM_RECORDABLE_PHASES = {
    "WARM_START_RUNNING",
    "INTERACTIVE",
}
ZERO_HASH = "0" * 64
CLASSIC_ARTIFACT_BASE_NAMES = (
    "direct_gen_outline",
    "storm_gen_outline",
    "storm_gen_article",
    "storm_gen_article_polished",
)
PUBLICATION_FIELDS = {
    "schema_version",
    "run_id",
    "published_at",
    "artifact_hashes",
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


def atomic_replace_bytes(path: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
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


def require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{label} must be a non-empty string")
    return value


def validate_co_storm_turn_payload(
    payload: Any,
    *,
    expected_turn_id: int,
    participant_registry: dict[str, tuple[str, str]],
    known_source_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != CO_STORM_TURN_PAYLOAD_FIELDS:
        raise StateError("Co-STORM turn payload fields are invalid")
    turn_id = payload["turn_id"]
    if (
        isinstance(turn_id, bool)
        or not isinstance(turn_id, int)
        or turn_id != expected_turn_id
    ):
        raise StateError(f"Co-STORM turn_id must be {expected_turn_id}")
    input_event = payload["input_event"]
    if input_event not in CO_STORM_INPUT_EVENTS:
        raise StateError(f"unknown Co-STORM input_event: {input_event!r}")
    policy = payload["policy"]
    if policy not in CO_STORM_POLICIES:
        raise StateError(f"unknown Co-STORM policy: {policy!r}")

    participants = payload["participants"]
    if not isinstance(participants, list) or not participants:
        raise StateError("Co-STORM participants must be a non-empty array")
    turn_participant_ids: set[str] = set()
    for index, participant in enumerate(participants):
        if not isinstance(participant, dict) or set(participant) != {
            "id",
            "display_name",
            "role",
        }:
            raise StateError(f"Co-STORM participant {index} fields are invalid")
        participant_id = require_non_empty_string(
            participant["id"], f"Co-STORM participant {index} id"
        )
        display_name = require_non_empty_string(
            participant["display_name"],
            f"Co-STORM participant {index} display_name",
        )
        role = require_non_empty_string(
            participant["role"], f"Co-STORM participant {index} role"
        )
        if participant_id in turn_participant_ids:
            raise StateError("Co-STORM participant ids must be unique per turn")
        turn_participant_ids.add(participant_id)
        identity = (display_name, role)
        if participant_id in participant_registry and participant_registry[participant_id] != identity:
            raise StateError(
                f"Co-STORM participant identity changed for id {participant_id!r}"
            )
        participant_registry[participant_id] = identity
    if expected_turn_id == 1 and not any(
        participant["role"].casefold() == "moderator" for participant in participants
    ):
        raise StateError("the persisted Co-STORM warm start must include Moderator")

    retrieval_records = payload["retrieval_records"]
    if not isinstance(retrieval_records, list):
        raise StateError("Co-STORM retrieval_records must be an array")
    for index, record in enumerate(retrieval_records):
        if not isinstance(record, dict) or set(record) != {"query", "source_ids"}:
            raise StateError(f"Co-STORM retrieval record {index} fields are invalid")
        require_non_empty_string(record["query"], f"Co-STORM retrieval record {index} query")
        source_ids = record["source_ids"]
        if not isinstance(source_ids, list) or not source_ids:
            raise StateError(
                f"Co-STORM retrieval record {index} source_ids must be non-empty"
            )
        for source_id in source_ids:
            known_source_ids.add(
                require_non_empty_string(source_id, "Co-STORM retrieval source id")
            )

    mind_map_delta = payload["mind_map_delta"]
    if not isinstance(mind_map_delta, dict) or set(mind_map_delta) != {
        "added",
        "updated",
        "removed",
    }:
        raise StateError("Co-STORM mind_map_delta fields are invalid")
    for action in ("added", "updated", "removed"):
        values = mind_map_delta[action]
        if not isinstance(values, list) or not all(
            (isinstance(value, str) and bool(value.strip())) or isinstance(value, dict)
            for value in values
        ):
            raise StateError(f"Co-STORM mind_map_delta.{action} must be an array")

    citations = payload["citations"]
    if not isinstance(citations, list) or not citations:
        raise StateError("Co-STORM citations must be a non-empty array")
    citation_ids: set[int] = set()
    for index, citation in enumerate(citations):
        if not isinstance(citation, dict) or set(citation) != {
            "citation_id",
            "source_id",
        }:
            raise StateError(f"Co-STORM citation {index} fields are invalid")
        citation_id = citation["citation_id"]
        if isinstance(citation_id, bool) or not isinstance(citation_id, int) or citation_id < 1:
            raise StateError("Co-STORM citation ids must be positive integers")
        if citation_id in citation_ids:
            raise StateError("Co-STORM citation ids must be unique per turn")
        citation_ids.add(citation_id)
        source_id = require_non_empty_string(
            citation["source_id"], f"Co-STORM citation {index} source_id"
        )
        if source_id not in known_source_ids:
            raise StateError(f"Co-STORM citation source is unknown: {source_id!r}")

    next_actions = payload["next_actions"]
    if not isinstance(next_actions, list) or not all(
        isinstance(action, str) and bool(action.strip()) for action in next_actions
    ):
        raise StateError("Co-STORM next_actions must be an array of non-empty strings")
    if policy == "FINAL_REPORT":
        if input_event != "USER_CONCLUDE" or next_actions:
            raise StateError(
                "FINAL_REPORT requires USER_CONCLUDE and no remaining next_actions"
            )
    elif not next_actions:
        raise StateError("non-final Co-STORM turns require at least one next action")
    return payload


def load_co_storm_turns(
    run_path: Path, state: dict[str, Any], *, required: bool = False
) -> list[dict[str, Any]]:
    turn_log_path = run_path.parent / "co-storm-turns.jsonl"
    if turn_log_path.is_symlink():
        raise StateError("Co-STORM turn log must not be a symlink")
    if not turn_log_path.exists():
        if required:
            raise StateError("a persisted Co-STORM warm-start turn is required")
        return []
    try:
        lines = turn_log_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise StateError("Co-STORM turn log is not strict UTF-8") from error
    if not lines:
        raise StateError("Co-STORM turn log must not be empty")
    entries: list[dict[str, Any]] = []
    participant_registry: dict[str, tuple[str, str]] = {}
    known_source_ids: set[str] = set()
    previous_turn_hash = ZERO_HASH
    for expected_turn_id, line in enumerate(lines, start=1):
        if not line.strip():
            raise StateError(
                f"Co-STORM turn log contains a blank line at {expected_turn_id}"
            )
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise StateError(
                f"Co-STORM turn log line {expected_turn_id} is invalid JSON"
            ) from error
        if not isinstance(entry, dict) or set(entry) != CO_STORM_TURN_ENTRY_FIELDS:
            raise StateError(f"Co-STORM turn {expected_turn_id} fields are invalid")
        if entry.get("run_id") != state["run_id"]:
            raise StateError(f"Co-STORM turn {expected_turn_id} has the wrong run_id")
        if entry.get("phase") not in CO_STORM_RECORDABLE_PHASES:
            raise StateError(f"Co-STORM turn {expected_turn_id} has an invalid phase")
        parse_timestamp(entry.get("timestamp"), f"Co-STORM turn {expected_turn_id} timestamp")
        if entry.get("previous_turn_hash") != previous_turn_hash:
            raise StateError(f"Co-STORM turn {expected_turn_id} breaks the hash chain")
        turn_hash = entry.get("turn_hash")
        unhashed_entry = {key: value for key, value in entry.items() if key != "turn_hash"}
        if turn_hash != content_hash(unhashed_entry):
            raise StateError(f"Co-STORM turn {expected_turn_id} has an invalid turn_hash")
        validate_co_storm_turn_payload(
            {key: entry[key] for key in CO_STORM_TURN_PAYLOAD_FIELDS},
            expected_turn_id=expected_turn_id,
            participant_registry=participant_registry,
            known_source_ids=known_source_ids,
        )
        entries.append(entry)
        previous_turn_hash = turn_hash
    return entries


def co_storm_turn_summary(
    state: dict[str, Any], entries: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "valid": True,
        "run_id": state["run_id"],
        "turn_count": len(entries),
        "latest_turn_hash": entries[-1]["turn_hash"] if entries else None,
    }


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
    if state["mode"] == "co-storm":
        load_co_storm_turns(
            run_path,
            state,
            required=state["phase"] in {"INTERACTIVE", "REPORTING", "VERIFIED", "COMPLETE"},
        )
    if state["mode"] == "classic":
        if state["phase"] == "COMPLETE":
            require_validated_classic_artifacts(
                run_path, state, CLASSIC_ARTIFACT_BASE_NAMES, published=True
            )
        validate_classic_publication_receipt(
            run_path, state, required=state["phase"] == "COMPLETE"
        )
    return state, committed_events


def status_run(args: argparse.Namespace) -> dict[str, Any]:
    state, _ = load_guarded_run(Path(args.run).resolve())
    return state


def validate_run(args: argparse.Namespace) -> dict[str, Any]:
    run_path = Path(args.run).resolve()
    state, _ = load_guarded_run(run_path)
    if state["mode"] == "co-storm":
        return co_storm_turn_summary(state, load_co_storm_turns(run_path, state))
    return {"valid": True, "run_id": state["run_id"]}


def event_key(command: str, payload: dict[str, Any]) -> str:
    return content_hash({"command": command, "payload": payload})


def record_co_storm_turn(args: argparse.Namespace) -> dict[str, Any]:
    run_path = Path(args.run).resolve()
    state, _ = load_guarded_run(run_path)
    if state["mode"] != "co-storm":
        raise StateError("record-turn is available only for Co-STORM runs")
    if state["status"] != "running" or state["phase"] not in CO_STORM_RECORDABLE_PHASES:
        raise StateError(
            f"cannot record a Co-STORM turn in phase/status {state['phase']!r}/{state['status']!r}"
        )
    payload_candidate = Path(args.turn)
    if payload_candidate.is_symlink():
        raise StateError("Co-STORM turn input must not be a symlink")
    payload_path = payload_candidate.resolve()
    if payload_path.parent != run_path.parent or not payload_path.is_file():
        raise StateError("Co-STORM turn input must be a direct file in .storm-run")
    payload = read_json(payload_path, "Co-STORM turn input")
    entries = load_co_storm_turns(run_path, state)
    if isinstance(payload, dict) and set(payload) == CO_STORM_TURN_PAYLOAD_FIELDS:
        turn_id = payload.get("turn_id")
        if (
            isinstance(turn_id, int)
            and not isinstance(turn_id, bool)
            and 1 <= turn_id <= len(entries)
        ):
            existing_payload = {
                key: entries[turn_id - 1][key] for key in CO_STORM_TURN_PAYLOAD_FIELDS
            }
            if payload == existing_payload:
                return co_storm_turn_summary(state, entries)
            raise StateError(
                f"Co-STORM turn {turn_id} is already recorded with different content"
            )
    participant_registry: dict[str, tuple[str, str]] = {}
    known_source_ids: set[str] = set()
    for expected_turn_id, entry in enumerate(entries, start=1):
        validate_co_storm_turn_payload(
            {key: entry[key] for key in CO_STORM_TURN_PAYLOAD_FIELDS},
            expected_turn_id=expected_turn_id,
            participant_registry=participant_registry,
            known_source_ids=known_source_ids,
        )
    expected_turn_id = len(entries) + 1
    validated_payload = validate_co_storm_turn_payload(
        payload,
        expected_turn_id=expected_turn_id,
        participant_registry=participant_registry,
        known_source_ids=known_source_ids,
    )
    if state["phase"] == "WARM_START_RUNNING" and (
        validated_payload["input_event"] == "USER_CONCLUDE"
        or validated_payload["policy"] == "FINAL_REPORT"
    ):
        raise StateError("the persisted Co-STORM warm start cannot be a final report")
    entry = {
        **validated_payload,
        "run_id": state["run_id"],
        "phase": state["phase"],
        "timestamp": utc_now(),
        "previous_turn_hash": entries[-1]["turn_hash"] if entries else ZERO_HASH,
    }
    entry["turn_hash"] = content_hash(entry)
    turn_log_path = run_path.parent / "co-storm-turns.jsonl"
    turn_log_text = "".join(canonical_json(item) + "\n" for item in [*entries, entry])
    atomic_write_text(turn_log_path, turn_log_text)
    recorded_entries = load_co_storm_turns(run_path, state, required=True)
    return co_storm_turn_summary(state, recorded_entries)


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


def classic_artifact_directory(run_path: Path, *, published: bool) -> Path:
    return run_path.parent.parent if published else run_path.parent / "staging"


def require_public_artifact(
    run_path: Path, base_name: str, *, published: bool = False
) -> Path:
    output_directory = classic_artifact_directory(run_path, published=published)
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


def require_validated_classic_artifacts(
    run_path: Path,
    state: dict[str, Any],
    base_names: Sequence[str],
    *,
    published: bool = False,
) -> None:
    expected_names = {f"{base_name}.html" for base_name in base_names}
    if set(state["artifacts"]) != expected_names:
        raise StateError(
            "validated artifact metadata must contain exactly the four canonical HTML files"
        )
    output_directory = classic_artifact_directory(run_path, published=published)
    for name in sorted(expected_names):
        metadata = state["artifacts"].get(name)
        if (
            not isinstance(metadata, dict)
            or metadata.get("path") != name
            or metadata.get("format") != "html"
            or not isinstance(metadata.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])
        ):
            raise StateError(f"validated artifact metadata is invalid: {name}")
        artifact_path = output_directory / name
        if artifact_path.is_symlink() or not artifact_path.is_file():
            raise StateError(f"validated public artifact is missing or unsafe: {name}")
        actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_hash != metadata["sha256"]:
            raise StateError(f"validated artifact hash does not match the file: {name}")


def require_valid_citation_audit(run_path: Path) -> None:
    citation_audit = read_json(
        run_path.parent / "citation-audit.json", "citation-audit.json"
    )
    required_fields = {
        "schema_version",
        "valid",
        "article",
        "used_citation_ids",
        "sources",
        "claims",
        "errors",
    }
    if not isinstance(citation_audit, dict) or set(citation_audit) != required_fields:
        raise StateError("citation audit fields are invalid")
    if (
        citation_audit["schema_version"] != "1.0"
        or citation_audit["valid"] is not True
        or citation_audit["article"] != "storm_gen_article_polished.html"
        or not isinstance(citation_audit["used_citation_ids"], list)
        or not citation_audit["used_citation_ids"]
        or not isinstance(citation_audit["sources"], list)
        or not isinstance(citation_audit["claims"], list)
        or citation_audit["errors"] != []
    ):
        raise StateError("citation audit must be valid before VERIFIED")


def validate_classic_publication_receipt(
    run_path: Path, state: dict[str, Any], *, required: bool
) -> dict[str, Any] | None:
    receipt_path = run_path.parent / "publication.json"
    if receipt_path.is_symlink():
        raise StateError("publication receipt must not be a symlink")
    if not receipt_path.exists():
        if required:
            raise StateError("missing publication.json for a COMPLETE Classic run")
        return None
    receipt = read_json(receipt_path, "publication.json")
    if not isinstance(receipt, dict) or set(receipt) != PUBLICATION_FIELDS:
        raise StateError("publication.json fields are invalid")
    if receipt["schema_version"] != 1 or receipt["run_id"] != state["run_id"]:
        raise StateError("publication.json does not match the guarded run")
    parse_timestamp(receipt["published_at"], "publication.json published_at")
    if receipt["artifact_hashes"] != artifact_hashes(state):
        raise StateError("publication.json artifact hashes do not match run state")
    return receipt


def publish_classic_artifacts(run_path: Path, state: dict[str, Any]) -> dict[str, Any]:
    staging_directory = classic_artifact_directory(run_path, published=False)
    output_directory = classic_artifact_directory(run_path, published=True)
    receipt_path = run_path.parent / "publication.json"
    existing_receipt = validate_classic_publication_receipt(
        run_path, state, required=False
    )
    if existing_receipt is not None:
        require_validated_classic_artifacts(
            run_path, state, CLASSIC_ARTIFACT_BASE_NAMES, published=True
        )
        return existing_receipt

    names_to_publish: list[str] = []
    for name, metadata in state["artifacts"].items():
        target = output_directory / name
        if target.exists():
            if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != metadata["sha256"]:
                raise StateError(f"refusing to replace an unexpected public artifact: {name}")
            continue
        names_to_publish.append(name)

    published_paths: list[Path] = []
    try:
        for name in sorted(names_to_publish):
            staged_path = staging_directory / name
            target = output_directory / name
            atomic_replace_bytes(target, staged_path.read_bytes())
            published_paths.append(target)
        require_validated_classic_artifacts(
            run_path, state, CLASSIC_ARTIFACT_BASE_NAMES, published=True
        )
        receipt = {
            "schema_version": 1,
            "run_id": state["run_id"],
            "published_at": utc_now(),
            "artifact_hashes": artifact_hashes(state),
        }
        atomic_write_text(
            receipt_path,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        validate_classic_publication_receipt(run_path, state, required=True)
        return receipt
    except (OSError, StateError) as error:
        receipt_path.unlink(missing_ok=True)
        for target in published_paths:
            target.unlink(missing_ok=True)
        raise StateError(f"atomic Classic publication failed: {error}") from error


def cleanup_classic_staging(run_path: Path) -> None:
    staging_directory = classic_artifact_directory(run_path, published=False)
    for name in (f"{base_name}.html" for base_name in CLASSIC_ARTIFACT_BASE_NAMES):
        (staging_directory / name).unlink(missing_ok=True)
    try:
        staging_directory.rmdir()
    except FileNotFoundError:
        pass


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
    if state["mode"] == "classic" and event_name in {"verified", "completed"}:
        for base_name in classic_artifact_events.values():
            require_public_artifact(run_path, base_name)
        require_valid_citation_audit(run_path)
        require_validated_classic_artifacts(
            run_path, state, tuple(classic_artifact_events.values())
        )
    if state["mode"] == "co-storm" and event_name == "warm_start_completed":
        turns = load_co_storm_turns(run_path, state, required=True)
        if turns[0]["phase"] != "WARM_START_RUNNING" or turns[0]["policy"] == "FINAL_REPORT":
            raise StateError("warm-start evidence must be a non-final persisted turn")
    if state["mode"] == "co-storm" and event_name == "reporting_started":
        turns = load_co_storm_turns(run_path, state, required=True)
        if (
            turns[-1]["input_event"] != "USER_CONCLUDE"
            or turns[-1]["policy"] != "FINAL_REPORT"
            or turns[-1]["phase"] != "INTERACTIVE"
            or turns[-1]["turn_id"] < 2
        ):
            raise StateError(
                "REPORTING requires a persisted USER_CONCLUDE with FINAL_REPORT turn"
            )


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
    classic_publication = state["mode"] == "classic" and args.event == "completed"
    if classic_publication:
        publish_classic_artifacts(run_path, state)
    updated_state = copy.deepcopy(state)
    updated_state["phase"] = transition[1]
    updated_state["status"] = "complete" if transition[1] == "COMPLETE" else "running"
    updated_state["next_action"] = PHASE_ACTIONS[state["mode"]][transition[1]]
    committed = commit_state_change(
        run_path, state, events, updated_state, args.event, key
    )
    if classic_publication:
        cleanup_classic_staging(run_path)
    return committed


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
    if args.mode == "classic":
        existing_public = [
            name
            for name in (f"{base_name}.html" for base_name in CLASSIC_ARTIFACT_BASE_NAMES)
            if (output / name).exists()
        ]
        if existing_public:
            raise StateError(
                "refusing to initialize over existing public artifacts: "
                f"{existing_public}"
            )
        (control_directory / "staging").mkdir(parents=True, exist_ok=True)

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
    record_turn_parser = subparsers.add_parser("record-turn")
    record_turn_parser.add_argument("--run", required=True)
    record_turn_parser.add_argument("--turn", required=True)
    record_turn_parser.set_defaults(handler=record_co_storm_turn)
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
