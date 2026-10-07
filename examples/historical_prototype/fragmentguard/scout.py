"""A real Scout scanner wrapping the deterministic synthetic checker."""

from inspect_ai.event import InfoEvent
from inspect_scout import Result, Scanner, Transcript, scanner

from .core import evaluate_stream, parse_events


@scanner(events=["info"])
def fragmentguard(policy: dict[str, str], budget: int = 3) -> Scanner[Transcript]:
    async def scan(transcript: Transcript) -> Result:
        records = []
        for event in transcript.events:
            if not isinstance(event, InfoEvent) or event.source != "fragmentguard.synthetic":
                raise ValueError("This smoke scanner accepts only FragmentGuard synthetic records")
            if not isinstance(event.data, dict):
                raise ValueError("Expected an event object")
            records.append(event.data)
        publications = evaluate_stream(parse_events(records), policy, budget)
        return Result(
            value={"publications": publications},
            explanation="Deterministic provenance checks on synthetic events; no model was called.",
            metadata={"fixture_only": True, "event_budget": budget},
        )

    return scan
