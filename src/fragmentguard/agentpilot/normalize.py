"""Normalize recorded operations into FragmentGuard's seven-field events.

Each successful raw operation becomes exactly one event, in observed order:
``read`` -> ``read``; ``copy``/``combine``/``select_fields``/``format_summary`` ->
``transform``; ``publish`` -> ``publish``. Inputs and outputs are immutable
version IDs, so exact read/write relationships survive normalization. ``tick``
is a logical counter of successful operations, not elapsed time.

Nothing is inferred or repaired: failed operations produce no events, and a
missing operation is never guessed.
"""

from __future__ import annotations

import re
from typing import Any

from ..schema import input_bindings, parse_stream

TRANSFORMS = ("copy", "combine", "select_fields", "format_summary")
SCENARIO_ID = re.compile(r"(sc|dev)([0-9]{2})")


def stream_id_for(scenario_id: str) -> str:
    """Neutral FragmentGuard stream ID: sc07 -> stream07, dev01 -> stream901."""
    match = SCENARIO_ID.fullmatch(scenario_id or "")
    if not match:
        raise ValueError(f"Scenario IDs must look like sc07 or dev01, got {scenario_id!r}")
    return f"stream{'9' if match.group(1) == 'dev' else ''}{match.group(2)}"


def normalize_records(records: list[dict[str, Any]], stream_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if any(r.get("status") == "commit_failed" for r in records):
        raise ValueError("A recorded operation failed to commit; the trace cannot be normalized")
    successful = [r for r in records if r.get("status") == "ok"]
    seqs = [r["seq"] for r in successful]
    if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
        raise ValueError("Recorded operations are not in strictly increasing sequence order")
    events, mapping = [], {}
    for index, record in enumerate(successful, start=1):
        operation = record["operation"]
        event = {
            "event_id": f"e{index:03d}",
            "tick": index,
            "agent_id": record["agent_id"],
            "operation": "transform" if operation in TRANSFORMS else operation,
            "inputs": [item["version_id"] for item in record["inputs"]],
            "outputs": [record["output_version"]] if operation != "publish" else [],
            "audience": record.get("audience"),
        }
        events.append(event)
        mapping[event["event_id"]] = {"seq": record["seq"], "tool": record["tool"], "operation": operation,
                                      "actor_kind": record["actor_kind"]}
    stream = {"stream_id": stream_id, "events": events}
    parse_stream(stream)  # The existing strict contract applies unchanged.
    return stream, mapping


def check_bindings(stream: dict[str, Any], mapping: dict[str, Any], ledger: dict[str, Any],
                   records: list[dict[str, Any]]) -> dict[str, Any]:
    """FragmentGuard's derived bindings must equal the ledger's recorded versions."""
    _, events = parse_stream(stream)
    bindings = input_bindings(events)
    event_for_seq = {entry["seq"]: event_id for event_id, entry in mapping.items()}
    versions = ledger["versions"]
    mismatches = []
    for event in events:
        for resource in event.inputs:
            entry = versions.get(resource)
            if entry is None:
                mismatches.append(f"{event.event_id}: input {resource} is not in the ledger")
                continue
            expected = event_for_seq.get(entry["produced_by_seq"]) if entry["kind"] == "derived" else None
            if bindings[event.event_id][resource] != expected:
                mismatches.append(f"{event.event_id}: {resource} bound to {bindings[event.event_id][resource]}, "
                                  f"ledger says {expected}")
        for resource in event.outputs:
            entry = versions.get(resource)
            if entry is None or event_for_seq.get(entry["produced_by_seq"]) != event.event_id:
                mismatches.append(f"{event.event_id}: output {resource} not produced by this event per ledger")
    successful = sum(1 for r in records if r.get("status") == "ok")
    if successful != len(events):
        mismatches.append(f"{successful} successful operations but {len(events)} normalized events")
    return {"agree": not mismatches, "mismatches": mismatches, "events": len(events)}
