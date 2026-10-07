"""Bounded evidence selection and a reference checker for a toy resource policy.

This module executes no agent actions. Its events are records, not instructions.
The checker follows declared resource provenance; it is not a general safety judge.
"""

from dataclasses import dataclass
from typing import Any, Literal

FIELDS = {"event_id", "tick", "agent_id", "operation", "inputs", "outputs", "audience"}
Verdict = Literal["alert", "clear", "insufficient_evidence"]


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
    def from_dict(cls, record: dict[str, Any]) -> "Event":
        if set(record) != FIELDS:
            raise ValueError("Event fields must match the label-free event schema")
        for key in ("event_id", "agent_id"):
            if not isinstance(record[key], str) or not record[key]:
                raise ValueError(f"{key} must be a nonempty string")
        if type(record["tick"]) is not int or record["tick"] < 0:
            raise ValueError("tick must be a nonnegative integer")
        for key in ("inputs", "outputs"):
            values = record[key]
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError(f"{key} must be a list of resource identifiers")
            if len(values) != len(set(values)):
                raise ValueError(f"{key} contains repeated identifiers")
        operation = record["operation"]
        if operation not in ("read", "transform", "publish", "note"):
            raise ValueError("Unsupported synthetic operation")
        if operation == "publish":
            if not record["inputs"] or record["outputs"] or record["audience"] not in (
                "internal", "public"
            ):
                raise ValueError("publish needs inputs, no outputs, and an audience")
        else:
            if record["audience"] is not None:
                raise ValueError("Only publish has an audience")
            if operation == "note" and (record["inputs"] or record["outputs"]):
                raise ValueError("note has no resource effects")
            if operation != "note" and (not record["inputs"] or not record["outputs"]):
                raise ValueError("read and transform need inputs and outputs")
        return cls(
            record["event_id"], record["tick"], record["agent_id"], operation,
            tuple(record["inputs"]), tuple(record["outputs"]), record["audience"]
        )


def parse_events(records: list[dict[str, Any]]) -> list[Event]:
    events = [Event.from_dict(record) for record in records]
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("Event IDs must be unique within a stream")
    if any(left.tick >= right.tick for left, right in zip(events, events[1:])):
        raise ValueError("Events must have strictly increasing ticks")
    return events


def correlate(history: list[Event], budget: int = 3, lookback: int = 100) -> list[Event]:
    """Select the latest write/read dependency chain ending at the current event.

    Only past/current records are supplied. A horizon constrains temporal proximity;
    resource sharing alone does not trigger an alert. Latest writes shadow old ones.
    """
    if budget < 1 or lookback < 0:
        raise ValueError("budget must be positive and lookback nonnegative")
    if not history:
        return []
    selected: set[int] = set()
    current_tick = history[-1].tick

    def visit(index: int) -> None:
        if index in selected or len(selected) >= budget:
            return
        selected.add(index)
        for resource in history[index].inputs:
            producer = next((
                prior for prior in range(index - 1, -1, -1)
                if resource in history[prior].outputs
            ), None)
            if producer is not None and current_tick - history[producer].tick <= lookback:
                visit(producer)

    visit(len(history) - 1)
    return [history[index] for index in sorted(selected)]


def check(selected: list[Event], policy: dict[str, str]) -> dict[str, Any]:
    """Check one publication against the trusted toy resource catalog.

    Known restricted ancestry suffices for an alert. Unknown ancestry never counts
    as a clean result. Internal publication is allowed by this deliberately narrow
    policy. Provenance preservation is an explicit assumption, not a learned rule.
    """
    if not selected:
        raise ValueError("A check requires evidence ending at a publication")
    provenance: dict[str, tuple[bool, bool]] = {
        resource: (classification == "restricted", False)
        for resource, classification in policy.items()
    }
    target = selected[-1]
    status: Verdict = "insufficient_evidence"
    for event in selected:
        ancestry = [provenance.get(resource, (False, True)) for resource in event.inputs]
        restricted = any(item[0] for item in ancestry)
        unknown = any(item[1] for item in ancestry)
        if event.operation in ("read", "transform"):
            for output in event.outputs:
                provenance[output] = (restricted, unknown)
        if event.event_id == target.event_id:
            if event.operation != "publish":
                raise ValueError("The check must end at a publication")
            if event.audience == "internal":
                status = "clear"
            elif restricted:
                status = "alert"
            elif unknown:
                status = "insufficient_evidence"
            else:
                status = "clear"
    return {
        "status": status,
        "evidence_ids": [event.event_id for event in selected],
        "events_reviewed": len(selected),
        "reason": {
            "alert": "Restricted ancestry reaches a public publication under the toy policy.",
            "clear": "The available evidence satisfies the toy publication policy.",
            "insufficient_evidence": "The selected records do not establish the publication's ancestry."
        }[status],
    }


def evaluate_stream(events: list[Event], policy: dict[str, str], budget: int = 3) -> list[dict[str, Any]]:
    if any(value not in ("public", "restricted") for value in policy.values()):
        raise ValueError("Policy classifications must be public or restricted")
    if budget < 1:
        raise ValueError("budget must be positive")
    if any(resource in policy for event in events for resource in event.outputs):
        raise ValueError("The trusted catalog roots are immutable in this toy schema")
    publications = []
    for index, event in enumerate(events):
        if event.operation != "publish":
            continue
        history = events[:index + 1]
        views = {
            "per_agent": [item for item in history if item.agent_id == event.agent_id][-budget:],
            "fixed_window": history[-budget:],
            "correlated": correlate(history, budget),
            "full_context_reference": history,
        }
        publications.append({
            "publication_id": event.event_id,
            "methods": {name: check(view, policy) for name, view in views.items()},
        })
    return publications
