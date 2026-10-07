"""Common evaluation logic: build each evidence view and feed it to the same checker.

At each publication only past and current events of that workspace are used.
Evaluator labels are never read here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .correlation import DEFAULT_BUDGET, DEFAULT_HORIZON, correlate_selection
from .monitor import check
from .schema import Event, SchemaError, check_catalog_roots_immutable, parse_streams, validate_policy

METHODS = ("per_agent", "fixed_window", "correlated", "full_context_reference")


@dataclass(frozen=True)
class PipelineConfig:
    budget: int = DEFAULT_BUDGET
    horizon: int = DEFAULT_HORIZON

    def __post_init__(self) -> None:
        if type(self.budget) is not int or self.budget < 1:
            raise SchemaError("budget must be a positive integer")
        if type(self.horizon) is not int or self.horizon < 0:
            raise SchemaError("horizon must be a nonnegative integer")

    def to_dict(self) -> dict[str, Any]:
        return {"methods": list(METHODS), **asdict(self)}

    def sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def select_views(history: list[Event], config: PipelineConfig) -> dict[str, tuple[list[Event], int]]:
    """Return each view's selected events and the number of history records examined."""
    publication = history[-1]
    budget = config.budget
    correlated = correlate_selection(history, budget, config.horizon)
    return {
        "per_agent": ([e for e in history if e.agent_id == publication.agent_id][-budget:], len(history)),
        "fixed_window": (history[-budget:], min(budget, len(history))),
        "correlated": (correlated.events, correlated.records_examined),
        "full_context_reference": (list(history), len(history)),
    }


def evaluate_stream(
    events: list[Event], policy: dict[str, str], budget: int = DEFAULT_BUDGET,
    horizon: int = DEFAULT_HORIZON,
) -> list[dict[str, Any]]:
    config = PipelineConfig(budget, horizon)
    policy = validate_policy(policy)
    check_catalog_roots_immutable(events, policy)
    publications = []
    for index, event in enumerate(events):
        if event.operation != "publish":
            continue
        history = events[: index + 1]
        methods = {}
        for name, (view, examined) in select_views(history, config).items():
            methods[name] = {**check(view, policy), "records_examined": examined}
        publications.append({
            "publication_id": event.event_id,
            "publishing_agent": event.agent_id,
            "audience": event.audience,
            "tick": event.tick,
            "methods": methods,
        })
    return publications


def evaluate_streams(
    streams: list[dict[str, Any]], policy: dict[str, str], config: PipelineConfig = PipelineConfig()
) -> dict[str, list[dict[str, Any]]]:
    """Evaluate each workspace independently; resource state never crosses streams."""
    return {
        stream_id: evaluate_stream(events, policy, config.budget, config.horizon)
        for stream_id, events in parse_streams(streams).items()
    }
