"""Bounded causal resource-lineage selection.

For a publication, follow each input to its latest preceding producer, then that
producer's inputs, until the selected-event budget or the tick horizon is hit.
Only past and current records are supplied, so future events cannot influence a
selection. A dependency that is absent, beyond the horizon, or cut by the budget
stays missing; the checker then sees an unresolved resource.

Branch priority is deterministic and naive: depth-first, in the order inputs are
listed on each event. With a tight budget the first-listed input's lineage can
consume the budget before later inputs are visited. That is a known limitation,
not an optimised policy; see docs/assumptions.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import Event

DEFAULT_BUDGET = 3
DEFAULT_HORIZON = 100


@dataclass(frozen=True)
class Selection:
    events: list[Event]
    # Distinct history records the selector looked at. This is an operation count
    # for the selection step only, not wall-clock time or model tokens.
    records_examined: int


def correlate_selection(
    history: list[Event], budget: int = DEFAULT_BUDGET, horizon: int = DEFAULT_HORIZON
) -> Selection:
    if budget < 1 or horizon < 0:
        raise ValueError("budget must be positive and horizon nonnegative")
    if not history:
        return Selection([], 0)
    current_tick = history[-1].tick
    selected: set[int] = set()
    examined: set[int] = {len(history) - 1}

    def latest_producer(index: int, resource: str) -> int | None:
        for prior in range(index - 1, -1, -1):
            if current_tick - history[prior].tick > horizon:
                return None  # Earlier producers are further outside the horizon.
            examined.add(prior)
            if resource in history[prior].outputs:
                return prior
        return None

    def visit(index: int) -> None:
        if index in selected or len(selected) >= budget:
            return
        selected.add(index)
        for resource in history[index].inputs:
            producer = latest_producer(index, resource)
            if producer is not None:
                visit(producer)

    visit(len(history) - 1)
    return Selection([history[index] for index in sorted(selected)], len(examined))


def correlate(
    history: list[Event], budget: int = DEFAULT_BUDGET, lookback: int = DEFAULT_HORIZON
) -> list[Event]:
    """Selected events in chronological order (``lookback`` is the tick horizon)."""
    return correlate_selection(history, budget, lookback).events
