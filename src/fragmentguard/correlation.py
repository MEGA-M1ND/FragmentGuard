"""Bounded causal resource-lineage selection.

For a publication, follow each input's binding to the event that actually
produced it, then that producer's bindings, until the selected-event budget or
the tick horizon is hit. Bindings come from ``schema.input_bindings`` and only
point backwards in the same workspace, so future events cannot influence a
selection. A producer that is absent, beyond the horizon, or cut by the budget
is simply not selected; the checker then sees that binding as unresolved.

Branch priority is deterministic and naive: depth-first, in the order inputs are
listed on each event. With a tight budget the first-listed input's lineage can
consume the budget before later inputs are visited. That is a known limitation,
not an optimised policy; see docs/assumptions.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import Bindings, Event, input_bindings

DEFAULT_BUDGET = 3
DEFAULT_HORIZON = 100


@dataclass(frozen=True)
class Selection:
    events: list[Event]
    # Distinct history records the selector dereferenced: the publication and
    # every bound producer it looked up, whether or not it was then selected.
    # Deriving the bindings is one shared pass over the log and is not counted.
    # This is an operation count, not wall-clock time or model tokens.
    records_examined: int


def correlate_selection(
    history: list[Event], budget: int = DEFAULT_BUDGET, horizon: int = DEFAULT_HORIZON,
    bindings: Bindings | None = None,
) -> Selection:
    if budget < 1 or horizon < 0:
        raise ValueError("budget must be positive and horizon nonnegative")
    if not history:
        return Selection([], 0)
    if bindings is None:
        bindings = input_bindings(history)
    position = {event.event_id: index for index, event in enumerate(history)}
    current_tick = history[-1].tick
    selected: set[int] = set()
    examined: set[int] = {len(history) - 1}

    def visit(index: int) -> None:
        if index in selected or len(selected) >= budget:
            return
        selected.add(index)
        for resource in history[index].inputs:
            producer = bindings[history[index].event_id][resource]
            if producer is None:
                continue  # Catalog root, or never written in this workspace.
            producer_index = position[producer]
            examined.add(producer_index)
            if current_tick - history[producer_index].tick <= horizon:
                visit(producer_index)

    visit(len(history) - 1)
    return Selection([history[index] for index in sorted(selected)], len(examined))


def correlate(
    history: list[Event], budget: int = DEFAULT_BUDGET, lookback: int = DEFAULT_HORIZON
) -> list[Event]:
    """Selected events in chronological order (``lookback`` is the tick horizon)."""
    return correlate_selection(history, budget, lookback).events
