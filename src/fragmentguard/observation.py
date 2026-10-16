"""Explicit trusted-pointer contract for unavailable event payloads.

Complete-log validation/binding is unchanged. Partial observations carry only
visible records and their declared pointers, plus trusted identity headers:
event IDs, ticks and produced resource/version IDs, with no hidden inputs,
agents, operations, ancestry or sensitivity state. Header availability is a
strong assumption, not robustness to dishonest or unlogged execution.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schema import (
    IDENTIFIER, Bindings, Event, SchemaError, check_catalog_roots_immutable, input_bindings,
    parse_stream, validate_policy,
)


def freeze_complete(stream: dict[str, Any], policy: dict[str, str]) -> dict[str, Any]:
    """Bind BEFORE hiding. Returns the complete observation for masking."""
    sid, events = parse_stream(stream)
    check_catalog_roots_immutable(events, validate_policy(policy))
    bindings = input_bindings(events)
    return {
        "schema_version": 1, "stream_id": sid, "events": [e.to_dict() for e in events],
        "identities": {e.event_id: {"tick": e.tick, "outputs": list(e.outputs)} for e in events},
        "bindings": {eid: {r: {"stream_id": sid, "event_id": p} if p is not None else None
                           for r, p in refs.items()} for eid, refs in bindings.items()},
    }


def hide(frozen: dict[str, Any], hidden: set[str]) -> dict[str, Any]:
    """Remove payloads and their input edges, retaining only allowed pointer metadata."""
    result = deepcopy(frozen)
    if not hidden <= set(result["identities"]):
        raise SchemaError("Mask names unknown events")
    result["events"] = [e for e in result["events"] if e["event_id"] not in hidden]
    result["bindings"] = {e["event_id"]: result["bindings"][e["event_id"]] for e in result["events"]}
    return result


def validate_observation(raw: Any, policy: dict[str, str]) -> tuple[list[Event], Bindings]:
    """Reject integrity failures instead of manufacturing a monitoring verdict.

    A reference to an absent but declared earlier producer is unresolved. Missing
    pointer metadata, cross-workspace references, future producers, mismatched
    output identities, and catalog-root writes are integrity errors. Explicit
    references to old versions are legal; the latest-name binder is never used.
    """
    fields = {"schema_version", "stream_id", "events", "identities", "bindings"}
    if not isinstance(raw, dict) or set(raw) != fields or type(raw["schema_version"]) is not int:
        raise SchemaError("Observation fields must match schema version 1 exactly")
    if raw["schema_version"] != 1:
        raise SchemaError("Unsupported observation schema")
    sid, events = parse_stream({"stream_id": raw["stream_id"], "events": raw["events"]})
    policy = validate_policy(policy)
    headers, pointers = raw["identities"], raw["bindings"]
    if not isinstance(headers, dict) or not isinstance(pointers, dict):
        raise SchemaError("Identity headers and pointers must be objects")
    ticks = set()
    for eid, header in headers.items():
        if not isinstance(eid, str) or not IDENTIFIER.fullmatch(eid):
            raise SchemaError("Malformed event identity")
        if not isinstance(header, dict) or set(header) != {"tick", "outputs"}:
            raise SchemaError("Headers may contain only tick and output identities")
        tick, outputs = header["tick"], header["outputs"]
        if type(tick) is not int or tick < 0 or tick in ticks:
            raise SchemaError("Identity ticks must be unique nonnegative integers")
        ticks.add(tick)
        if (not isinstance(outputs, list) or any(not isinstance(r, str) or not IDENTIFIER.fullmatch(r)
                                                for r in outputs) or len(set(outputs)) != len(outputs)):
            raise SchemaError("Malformed output identities")
        if set(outputs) & set(policy):
            raise SchemaError("Catalog root identities cannot be produced versions")
    if set(pointers) != {e.event_id for e in events}:
        raise SchemaError("Pointers must cover exactly the visible events; hidden input edges are forbidden")
    bindings: Bindings = {}
    for event in events:
        header = headers.get(event.event_id)
        if header != {"tick": event.tick, "outputs": list(event.outputs)}:
            raise SchemaError("Visible event disagrees with its immutable identity")
        refs = pointers[event.event_id]
        if not isinstance(refs, dict) or set(refs) != set(event.inputs):
            raise SchemaError("Pointers must cover exactly each visible event's inputs")
        bindings[event.event_id] = {}
        for resource, ref in refs.items():
            if ref is None:
                # None denotes a root/unknown external input, never a missing pointer.
                if any(h["tick"] < event.tick and resource in h["outputs"] for h in headers.values()):
                    raise SchemaError("Produced input is missing its producer reference")
                producer = None
            else:
                if (not isinstance(ref, dict) or set(ref) != {"stream_id", "event_id"}
                        or ref["stream_id"] != sid or not isinstance(ref["event_id"], str)):
                    raise SchemaError("Malformed or cross-workspace producer reference")
                producer = ref["event_id"]
                produced = headers.get(producer)
                if produced is None or produced["tick"] >= event.tick or resource not in produced["outputs"]:
                    raise SchemaError("Unknown, later or non-producing event reference")
            bindings[event.event_id][resource] = producer
    return events, bindings


def evaluate_observation(raw: dict[str, Any], policy: dict[str, str]) -> list[dict[str, Any]]:
    """All methods receive the same visible payloads and validated pointer metadata."""
    from .experiments.evaluate import evaluate

    events, bindings = validate_observation(raw, policy)
    return evaluate(events, policy, bindings)
