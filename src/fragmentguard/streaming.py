"""Independent forward sensitivity propagation over exact producer references.

The caller supplies causal observation metadata, never evaluator ancestry/labels.
Versions are keyed by (producer event ID, resource), so an old handle can still
be resolved after display-name replacement. No selector or checker is imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import Event, SchemaError, validate_policy


@dataclass(frozen=True)
class Sensitivity:
    restricted: bool = False
    unresolved: frozenset[tuple[str, str | None]] = frozenset()

    def merge(self, other: Sensitivity) -> Sensitivity:
        return Sensitivity(self.restricted or other.restricted, self.unresolved | other.unresolved)


class StreamingSensitivity:
    """One workspace's state; call ``update`` exactly once per arriving event.

    Omitted referenced versions are unknown even if their resource name matches
    a catalog root. States for old versions are retained; no garbage collection
    or production recorder integration is claimed.
    """

    def __init__(self, policy: dict[str, str]):
        self.policy = validate_policy(policy)
        self.versions: dict[tuple[str, str], Sensitivity] = {}
        self.seen: dict[str, tuple[str, ...]] = {}
        self.last_tick = -1
        self.input_updates = 0
        self.state_writes = 0

    def update(self, event: Event, producers: dict[str, str | None]) -> dict[str, Any] | None:
        Event.from_dict(event.to_dict())
        if event.tick <= self.last_tick or event.event_id in self.seen:
            raise SchemaError("Streaming events must have unique IDs and increasing ticks")
        if set(producers) != set(event.inputs):
            raise SchemaError("Producer references must cover exactly the event inputs")
        if set(event.outputs) & set(self.policy):
            raise SchemaError("Catalog roots are immutable")
        state = Sensitivity()
        for resource in event.inputs:
            producer = producers[resource]
            if producer is not None and (not isinstance(producer, str) or producer == event.event_id):
                raise SchemaError("Invalid producer reference")
            if producer in self.seen and resource not in self.seen[producer]:
                raise SchemaError("Reference is not a producing event")
            if producer is None:
                classification = self.policy.get(resource)
                part = Sensitivity(classification == "restricted", frozenset() if classification else
                                   frozenset({(resource, None)}))
            else:
                part = self.versions.get((producer, resource),
                                         Sensitivity(unresolved=frozenset({(resource, producer)})))
            state = state.merge(part)
        self.seen[event.event_id] = event.outputs
        self.last_tick = event.tick
        self.input_updates += len(event.inputs)
        for output in event.outputs:
            self.versions[(event.event_id, output)] = state
            self.state_writes += 1
        if event.operation != "publish":
            return None
        status = ("clear" if event.audience == "internal" else "alert" if state.restricted else
                  "insufficient_evidence" if state.unresolved else "clear")
        return {
            "status": status,
            "unresolved_inputs": [{"resource": r, "bound_producer": p} for r, p in
                                  sorted(state.unresolved, key=lambda item: (item[0], item[1] or ""))],
            "known_restricted": state.restricted,
            "events_received": len(self.seen),
            "input_state_updates": self.input_updates,
            "state_writes": self.state_writes,
            "retained_versions": len(self.versions),
            "retained_identity_headers": len(self.seen),
            "retained_unresolved_entries": sum(len(s.unresolved) for s in self.versions.values()),
            "events_reviewed": 0,
            "evidence_ids": [],
            "note": "Forward state decision; no events presented to a checker. Counts are cumulative.",
        }
