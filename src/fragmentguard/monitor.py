"""Deterministic reference checker for the toy publication policy.

The checker replays the selected records in order with the trusted catalog.
Declared transformations are assumed to preserve restriction status, and the
latest selected write to a resource replaces earlier state. It does not infer
intent, recognise redaction, or implement declassification.

Outcomes:
- ``alert``: a public publication has established restricted ancestry.
- ``clear``: internal publication (allowed), or public publication whose ancestry
  is fully known and public.
- ``insufficient_evidence``: a public publication's ancestry is not established.

Known restricted ancestry justifies an alert even when another branch is unknown;
unknown ancestry never yields ``clear``. Invalid input raises instead of becoming
a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .schema import Event, SchemaError

Verdict = Literal["alert", "clear", "insufficient_evidence"]
VERDICTS: tuple[Verdict, ...] = ("alert", "clear", "insufficient_evidence")


@dataclass(frozen=True)
class Ancestry:
    restricted_roots: frozenset[str] = frozenset()
    public_roots: frozenset[str] = frozenset()
    unresolved: frozenset[str] = frozenset()  # resources with no selected producer
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


def check(selected: list[Event], policy: dict[str, str]) -> dict[str, Any]:
    """Check the publication that ends ``selected`` against the trusted catalog."""
    if not selected:
        raise SchemaError("A check requires evidence ending at a publication")
    target = selected[-1]
    if target.operation != "publish":
        raise SchemaError("The check must end at a publication")
    if any(left.tick >= right.tick for left, right in zip(selected, selected[1:])):
        raise SchemaError("Selected evidence must be in strictly increasing tick order")

    state: dict[str, Ancestry] = {}

    def ancestry_of(resource: str) -> Ancestry:
        if resource in state:
            return state[resource]
        classification = policy.get(resource)
        if classification == "restricted":
            return Ancestry(restricted_roots=frozenset({resource}))
        if classification == "public":
            return Ancestry(public_roots=frozenset({resource}))
        return Ancestry(unresolved=frozenset({resource}))

    for event in selected[:-1]:
        if event.operation not in ("read", "transform"):
            continue  # Notes and earlier publications have no resource effects.
        combined = Ancestry()
        for resource in event.inputs:
            combined = combined.merge(ancestry_of(resource))
        combined = combined.merge(Ancestry(via=frozenset({event.event_id})))
        for output in event.outputs:
            state[output] = combined  # Latest selected write replaces earlier state.

    lineage = Ancestry()
    for resource in target.inputs:
        lineage = lineage.merge(ancestry_of(resource))

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
            explanation += f" Unresolved resource(s): {_fmt(lineage.unresolved)}."
    elif lineage.unresolved:
        status = "insufficient_evidence"
        explanation = (
            f"{subject}: no selected producer or catalog root for "
            f"{_fmt(lineage.unresolved)}, so ancestry is not established."
        )
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
        "explanation": explanation,
    }
