"""Deterministic reference checker for the toy publication policy.

The checker replays the selected records in order with the trusted catalog and
the causal input bindings for those records. Each input is resolved through its
binding, never by resource name alone:

- bound to a selected producer: inherit that producer's recorded ancestry;
- bound to a producer the view omitted: unresolved (the older selected write of
  the same name, if any, is not used);
- unbound (no earlier write in the workspace): a catalog root if the trusted
  policy lists it, otherwise unresolved.

Declared transformations are assumed to preserve restriction status. The checker
does not infer intent, recognise redaction, or implement declassification.

Outcomes:
- ``alert``: a public publication has established restricted ancestry.
- ``clear``: internal publication (allowed), or public publication whose ancestry
  is fully resolved and public.
- ``insufficient_evidence``: a public publication's ancestry is not established.

Known restricted ancestry justifies an alert even when another branch is
unresolved; unresolved ancestry never yields ``clear``. Invalid input raises
instead of becoming a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .schema import Bindings, Event, SchemaError

Verdict = Literal["alert", "clear", "insufficient_evidence"]
VERDICTS: tuple[Verdict, ...] = ("alert", "clear", "insufficient_evidence")


@dataclass(frozen=True)
class Ancestry:
    restricted_roots: frozenset[str] = frozenset()
    public_roots: frozenset[str] = frozenset()
    # (resource, bound producer or None): inputs whose origin the view cannot establish.
    unresolved: frozenset[tuple[str, str | None]] = frozenset()
    via: frozenset[str] = frozenset()  # selected event IDs that carried the lineage

    def merge(self, other: "Ancestry") -> "Ancestry":
        return Ancestry(
            self.restricted_roots | other.restricted_roots,
            self.public_roots | other.public_roots,
            self.unresolved | other.unresolved,
            self.via | other.via,
        )


def _fmt(values: frozenset[str] | set[str]) -> str:
    return ", ".join(sorted(values)) or "none"


def _fmt_unresolved(items: frozenset[tuple[str, str | None]]) -> str:
    return "; ".join(
        f"{resource} (its producer {producer} is not in the selected evidence)" if producer
        else f"{resource} (no earlier producer and not a catalog root)"
        for resource, producer in sorted(items, key=lambda item: (item[0], item[1] or ""))
    )


def _validate(selected: list[Event], bindings: Bindings) -> None:
    if not selected:
        raise SchemaError("A check requires evidence ending at a publication")
    if selected[-1].operation != "publish":
        raise SchemaError("The check must end at a publication")
    if any(left.tick >= right.tick for left, right in zip(selected, selected[1:], strict=False)):
        raise SchemaError("Selected evidence must be in strictly increasing tick order")
    by_id = {event.event_id: event for event in selected}
    for event in selected:
        bound = bindings.get(event.event_id)
        if bound is None or set(bound) != set(event.inputs):
            raise SchemaError(f"Bindings for {event.event_id} must cover exactly its inputs")
        for resource, producer in bound.items():
            if producer in by_id and (
                resource not in by_id[producer].outputs or by_id[producer].tick >= event.tick
            ):
                raise SchemaError(f"{event.event_id}: {resource} is bound to a non-producing or later event")


def check(selected: list[Event], policy: dict[str, str], bindings: Bindings) -> dict[str, Any]:
    """Check the publication that ends ``selected`` against the trusted catalog."""
    _validate(selected, bindings)
    target = selected[-1]
    selected_ids = {event.event_id for event in selected}
    produced: dict[tuple[str, str], Ancestry] = {}  # (producer event, resource) -> ancestry

    def resolve(event: Event, resource: str) -> Ancestry:
        producer = bindings[event.event_id][resource]
        if producer is None:
            classification = policy.get(resource)
            if classification == "restricted":
                return Ancestry(restricted_roots=frozenset({resource}))
            if classification == "public":
                return Ancestry(public_roots=frozenset({resource}))
            return Ancestry(unresolved=frozenset({(resource, None)}))
        if producer in selected_ids:
            return produced[(producer, resource)]
        return Ancestry(unresolved=frozenset({(resource, producer)}))

    for event in selected[:-1]:
        if event.operation not in ("read", "transform"):
            continue  # Notes and earlier publications have no resource effects.
        combined = Ancestry(via=frozenset({event.event_id}))
        for resource in event.inputs:
            combined = combined.merge(resolve(event, resource))
        for output in event.outputs:
            produced[(event.event_id, output)] = combined

    lineage = Ancestry()
    for resource in target.inputs:
        lineage = lineage.merge(resolve(target, resource))

    subject = f"{target.audience.capitalize()} publication {target.event_id} of {_fmt(set(target.inputs))}"
    via = f" via selected event(s) {_fmt(lineage.via)}" if lineage.via else " directly"
    if target.audience == "internal":
        status: Verdict = "clear"
        explanation = f"{subject}: internal audiences are allowed by the toy policy."
    elif lineage.restricted_roots:
        status = "alert"
        explanation = (
            f"{subject}: restricted ancestry from catalog root(s) "
            f"{_fmt(lineage.restricted_roots)}{via}."
        )
        if lineage.unresolved:
            explanation += f" Also unresolved: {_fmt_unresolved(lineage.unresolved)}."
    elif lineage.unresolved:
        status = "insufficient_evidence"
        explanation = f"{subject}: ancestry not established for {_fmt_unresolved(lineage.unresolved)}."
    else:
        status = "clear"
        explanation = (
            f"{subject}: all ancestry traces to public catalog root(s) "
            f"{_fmt(lineage.public_roots)}{via}."
        )
    return {
        "status": status,
        "evidence_ids": [event.event_id for event in selected],
        "events_reviewed": len(selected),
        "unresolved_inputs": [
            {"resource": resource, "bound_producer": producer}
            for resource, producer in sorted(lineage.unresolved, key=lambda item: (item[0], item[1] or ""))
        ],
        "explanation": explanation,
    }
