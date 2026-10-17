"""Forward sensitivity state with recorded parent pointers and bounded witnesses.

No checker, selector or evaluator supplies the cached verdict. The shared payload
archive and observation bindings are supplied by the caller. Additional state
retains parent references and the independent streaming sensitivity cache.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .schema import Event
from .streaming import StreamingSensitivity


@dataclass(frozen=True)
class Witness:
    events: list[Event]
    payload_records_examined: int
    parent_edges_examined: int
    cached_state_reads: int


class StreamingProvenance:
    """One fresh state per visible workspace; all old versions are retained.

    Retrieval prioritizes a known-restricted parent, then preserves input order.
    This uses propagated state, not evaluator/root ancestry. It does not optimize
    the original correlation selector or change any historical report schema.
    """

    def __init__(self, policy: dict[str, str]):
        self.sensitivity = StreamingSensitivity(policy)
        self.parents: dict[str, tuple[tuple[str, str | None], ...]] = {}
        self.input_references_ingested = 0

    def update(self, event: Event, producers: dict[str, str | None]):
        verdict = self.sensitivity.update(event, producers)
        self.parents[event.event_id] = tuple((resource, producers[resource]) for resource in event.inputs)
        self.input_references_ingested += len(event.inputs)
        return verdict

    def witness(self, publication: Event, archive: dict[str, Event], budget: int, horizon: int) -> Witness:
        if type(budget) is not int or budget < 1 or type(horizon) is not int or horizon < 0:
            raise ValueError("Positive integer budget and nonnegative integer horizon required")
        selected: dict[str, Event] = {}
        examined: set[str] = set()
        edge_reads = state_reads = 0

        def restricted(edge):
            nonlocal state_reads
            resource, producer = edge
            state_reads += 1
            if producer is None:
                return self.sensitivity.policy.get(resource) == "restricted"
            state = self.sensitivity.versions.get((producer, resource))
            return bool(state and state.restricted)

        def visit(eid):
            nonlocal edge_reads
            if eid in selected or len(selected) >= budget:
                return
            event = archive.get(eid)
            if event is None:
                return  # Trusted pointer survives; its payload does not.
            examined.add(eid)
            if publication.tick - event.tick > horizon:
                return
            selected[eid] = event
            parents = self.parents[eid]
            edge_reads += len(parents)
            # Stable sort retains declared input order within either priority.
            for _, producer in sorted(parents, key=lambda edge: not restricted(edge)):
                if producer is not None:
                    visit(producer)

        visit(publication.event_id)
        return Witness(sorted(selected.values(), key=lambda e: e.tick), len(examined), edge_reads, state_reads)

    def retained_state(self):
        """Logical slots and canonical serialization bytes, NOT resident memory."""
        state = self.sensitivity
        serialized = {
            "versions": [[eid, resource, value.restricted, sorted(value.unresolved,
                           key=lambda ref: (ref[0], ref[1] or ""))]
                          for (eid, resource), value in sorted(state.versions.items())],
            "identity_headers": state.seen, "parents": self.parents,
        }
        return {
            "version_state_slots": len(state.versions), "identity_headers": len(state.seen),
            "parent_edges": self.input_references_ingested,
            "unresolved_reference_entries": sum(len(v.unresolved) for v in state.versions.values()),
            "canonical_state_bytes": len(json.dumps(serialized, sort_keys=True, separators=(",", ":")).encode()),
        }
