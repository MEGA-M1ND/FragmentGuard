"""Strict validation for label-free synthetic event records and the trusted policy.

Events are inert records, not instructions. Nothing here executes an action.
Invalid input raises ``SchemaError``; it is never sorted, repaired, or scored.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

FIELDS = frozenset({"event_id", "tick", "agent_id", "operation", "inputs", "outputs", "audience"})
STREAM_FIELDS = frozenset({"stream_id", "events"})
OPERATIONS = ("read", "transform", "publish", "note")
AUDIENCES = ("internal", "public")
CLASSIFICATIONS = ("public", "restricted")

# Short, opaque identifiers. Stream IDs must be neutral workspace names such as
# ``stream01`` so a stream identifier cannot smuggle a campaign or attack label.
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
STREAM_ID = re.compile(r"stream[0-9]{2,6}")


class SchemaError(ValueError):
    """Raised when a stream, event, or policy violates the input contract."""


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise SchemaError(f"{field} must be an identifier matching {IDENTIFIER.pattern!r}")
    return value


@dataclass(frozen=True)
class Event:
    event_id: str
    tick: int
    agent_id: str
    operation: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    audience: str | None

    @classmethod
    def from_dict(cls, record: Any) -> "Event":
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise SchemaError("Event fields must match the label-free event schema exactly")
        _identifier(record["event_id"], "event_id")
        _identifier(record["agent_id"], "agent_id")
        if type(record["tick"]) is not int or record["tick"] < 0:
            raise SchemaError("tick must be a nonnegative integer")
        for key in ("inputs", "outputs"):
            values = record[key]
            if not isinstance(values, list):
                raise SchemaError(f"{key} must be a list of resource identifiers")
            for value in values:
                _identifier(value, f"{key} entry")
            if len(values) != len(set(values)):
                raise SchemaError(f"{key} contains repeated identifiers")
        operation = record["operation"]
        if operation not in OPERATIONS:
            raise SchemaError(f"Unsupported synthetic operation: {operation!r}")
        inputs, outputs, audience = record["inputs"], record["outputs"], record["audience"]
        if operation == "publish":
            if not inputs or outputs or audience not in AUDIENCES:
                raise SchemaError("publish needs inputs, no outputs, and an internal/public audience")
        elif audience is not None:
            raise SchemaError("Only publish has an audience")
        elif operation == "note" and (inputs or outputs):
            raise SchemaError("note has no resource effects")
        elif operation in ("read", "transform") and (not inputs or not outputs):
            raise SchemaError("read and transform need inputs and outputs")
        return cls(
            record["event_id"], record["tick"], record["agent_id"], operation,
            tuple(inputs), tuple(outputs), audience,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tick": self.tick,
            "agent_id": self.agent_id,
            "operation": self.operation,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "audience": self.audience,
        }


def parse_events(records: Any) -> list[Event]:
    """Validate one workspace's ordered records. Invalid order is rejected, not sorted."""
    if not isinstance(records, list):
        raise SchemaError("A stream's events must be a list")
    events = [Event.from_dict(record) for record in records]
    if len({event.event_id for event in events}) != len(events):
        raise SchemaError("Event IDs must be unique within a stream")
    if any(left.tick >= right.tick for left, right in zip(events, events[1:])):
        raise SchemaError("Events must have strictly increasing ticks")
    return events


def parse_stream(stream: Any) -> tuple[str, list[Event]]:
    """Validate one stream object: a neutral workspace ID and its events, nothing else."""
    if not isinstance(stream, dict) or set(stream) != STREAM_FIELDS:
        raise SchemaError("A stream may contain only 'stream_id' and 'events'")
    stream_id = stream["stream_id"]
    if not isinstance(stream_id, str) or not STREAM_ID.fullmatch(stream_id):
        raise SchemaError(f"stream_id must be neutral, matching {STREAM_ID.pattern!r}")
    return stream_id, parse_events(stream["events"])


def parse_streams(streams: Any) -> dict[str, list[Event]]:
    if not isinstance(streams, list) or not streams:
        raise SchemaError("Expected a nonempty list of streams")
    parsed: dict[str, list[Event]] = {}
    for stream in streams:
        stream_id, events = parse_stream(stream)
        if stream_id in parsed:
            raise SchemaError(f"Duplicate stream_id: {stream_id}")
        parsed[stream_id] = events
    return parsed


def validate_policy(policy: Any) -> dict[str, str]:
    """The trusted catalog: immutable root resources classified public or restricted."""
    if not isinstance(policy, dict) or not policy:
        raise SchemaError("Policy must be a nonempty object of resource classifications")
    for resource, classification in policy.items():
        _identifier(resource, "policy resource")
        if classification not in CLASSIFICATIONS:
            raise SchemaError("Policy classifications must be public or restricted")
    return dict(policy)


# event_id -> {input resource -> producing event_id, or None if nothing in the
# workspace wrote it before this event}.
Bindings = dict[str, dict[str, str | None]]


def input_bindings(events: list[Event]) -> Bindings:
    """Bind each input to the write it actually read: the latest earlier producer.

    This is observation metadata, equivalent to a logger recording which version
    of a resource each read saw. It is causal (a binding depends only on earlier
    events in the same workspace), label-free (producer IDs only, never
    classifications), and derived once from the complete ordered workspace log,
    so every evidence view receives the same bindings for the events it selects.
    """
    latest: dict[str, str] = {}
    bindings: Bindings = {}
    for event in events:
        bindings[event.event_id] = {resource: latest.get(resource) for resource in event.inputs}
        for resource in event.outputs:
            latest[resource] = event.event_id
    return bindings


def check_catalog_roots_immutable(events: list[Event], policy: dict[str, str]) -> None:
    for event in events:
        written = sorted(set(event.outputs) & set(policy))
        if written:
            raise SchemaError(
                f"Event {event.event_id} writes trusted catalog root(s) {written}; "
                "catalog roots are immutable in this toy schema"
            )


# Bundled fixtures. The evaluator-only expectations file lives beside them but is
# read only by reporting, after scanning; never by selection or the checker.
FIXTURE_DIR = resources.files("fragmentguard") / "fixtures"


def read_json(path: Path | Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_streams(path: Path | None = None) -> list[dict[str, Any]]:
    raw = read_json(path if path is not None else FIXTURE_DIR / "streams.json")
    parse_streams(raw)
    return raw


def load_policy(path: Path | None = None) -> dict[str, str]:
    return validate_policy(read_json(path if path is not None else FIXTURE_DIR / "policy.json"))
