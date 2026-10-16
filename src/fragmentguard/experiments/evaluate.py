"""Compare forward state with the four existing views on shared metadata."""

from __future__ import annotations

from typing import Any

from ..monitor import check
from ..pipeline import PipelineConfig, select_views
from ..schema import Bindings, Event
from ..streaming import StreamingSensitivity

METHODS = ("per_agent", "fixed_window", "correlated", "full_context_reference", "streaming")


def evaluate(events: list[Event], policy: dict[str, str], bindings: Bindings) -> list[dict[str, Any]]:
    streaming = StreamingSensitivity(policy)
    publications = []
    for index, event in enumerate(events):
        propagated = streaming.update(event, bindings[event.event_id])
        if propagated is None:
            continue
        methods = {name: {**check(view, policy, bindings), "records_examined": examined}
                   for name, (view, examined) in select_views(events[:index + 1], PipelineConfig(), bindings).items()}
        methods["streaming"] = propagated
        publications.append({"publication_id": event.event_id, "methods": methods})
    return publications
