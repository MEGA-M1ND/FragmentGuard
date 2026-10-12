"""Inspect Scout integration: transcript storage, the decorated scanner, and both run modes.

Fixture records are stored as Inspect AI ``InfoEvent`` objects whose ``source`` is
``fragmentguard.synthetic``. They are labelled synthetic and are not presented as
executed tool calls. The scanner is deterministic and makes no generation calls.
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from inspect_ai.event import InfoEvent
from inspect_scout import (
    Result, Scanner, Transcript, TranscriptContent, scan, scan_results_df, scanner,
    transcripts_db, transcripts_from,
)

from .pipeline import PipelineConfig, evaluate_stream
from .schema import SchemaError, parse_events, parse_stream

SYNTHETIC_SOURCE = "fragmentguard.synthetic"
SOURCE_TYPE = "fragmentguard_synthetic"
# Where a stream's records came from. The bundled fixtures are hand-written;
# recorded traces are normalized from an application-side action recorder
# (fragmentguard.agentpilot). Either way the monitor itself calls no model.
SOURCE_KINDS = {
    "synthetic_fixture": (SYNTHETIC_SOURCE, SOURCE_TYPE),
    "agent_executed_trace": ("fragmentguard.recorded_trace", "fragmentguard_recorded_trace"),
}
SCANNER_NAME = "fragmentguard"
EPOCH = datetime(2026, 10, 7, tzinfo=timezone.utc)
MOCK_MODEL = "mockllm/model"


def event_uuid(stream_id: str, event_id: str) -> str:
    return f"{stream_id}.{event_id}"


def _source(source_kind: str) -> tuple[str, str]:
    if source_kind not in SOURCE_KINDS:
        raise SchemaError(f"Unknown source kind {source_kind!r}; expected one of {sorted(SOURCE_KINDS)}")
    return SOURCE_KINDS[source_kind]


def to_transcript(stream: dict[str, Any], source_kind: str = "synthetic_fixture") -> Transcript:
    stream_id, events = parse_stream(stream)
    event_source, source_type = _source(source_kind)
    return Transcript(
        transcript_id=stream_id,
        source_type=source_type,
        metadata={},
        events=[
            InfoEvent(
                uuid=event_uuid(stream_id, event.event_id),
                timestamp=EPOCH + timedelta(seconds=event.tick),
                source=event_source,
                data=event.to_dict(),
            )
            for event in events
        ],
    )


def records_from_transcript(
    transcript: Transcript, source_kind: str = "synthetic_fixture"
) -> list[dict[str, Any]]:
    """Extract and validate records of one source kind; reject anything else rather than skip it."""
    event_source, _ = _source(source_kind)
    if transcript.metadata:
        raise SchemaError("Transcripts must carry no metadata (labels stay evaluator-only)")
    records = []
    for event in transcript.events:
        if not isinstance(event, InfoEvent) or event.source != event_source:
            raise SchemaError(f"This scanner accepts only {event_source} info events")
        if not isinstance(event.data, dict):
            raise SchemaError("Expected a synthetic event object")
        if event.uuid != event_uuid(transcript.transcript_id, str(event.data.get("event_id"))):
            raise SchemaError("Event UUID does not belong to this transcript's workspace")
        records.append(event.data)
    return records


@scanner(name=SCANNER_NAME, events=["info"])
def fragmentguard(
    policy: dict[str, str], budget: int = 3, horizon: int = 100, source_kind: str = "synthetic_fixture"
) -> Scanner[Transcript]:
    config = PipelineConfig(budget, horizon)
    _source(source_kind)

    async def scan_transcript(transcript: Transcript) -> Result:
        events = parse_events(records_from_transcript(transcript, source_kind))
        publications = evaluate_stream(events, policy, config.budget, config.horizon)
        return Result(
            value={"publications": publications},
            explanation=f"Deterministic provenance checks on {source_kind} records; the monitor called no model.",
            metadata={
                "source_kind": source_kind,
                "synthetic_fixture": source_kind == "synthetic_fixture",
                "monitor_model_calls": 0,
                **config.to_dict(),
            },
        )

    return scan_transcript


async def write_database(
    location: Path, streams: list[dict[str, Any]], source_kind: str = "synthetic_fixture"
) -> None:
    database = transcripts_db(str(location))
    await database.connect()
    try:
        await database.insert([to_transcript(stream, source_kind) for stream in streams])
    finally:
        await database.disconnect()


async def read_database(location: Path) -> list[Transcript]:
    database = transcripts_db(str(location))
    transcripts = []
    await database.connect()
    try:
        async for info in database.select():
            transcripts.append(await database.read(info, TranscriptContent(events=["info"])))
    finally:
        await database.disconnect()
    return sorted(transcripts, key=lambda item: item.transcript_id)


async def run_direct(
    location: Path, policy: dict[str, str], config: PipelineConfig, source_kind: str = "synthetic_fixture"
) -> list[dict[str, Any]]:
    """Read transcripts back through Scout's database API and call the decorated scanner.

    This skips Scout's scheduler, model setup, and recorder. No model is created.
    """
    scan_fn = fragmentguard(policy, budget=config.budget, horizon=config.horizon, source_kind=source_kind)
    rows = []
    for transcript in await read_database(location):
        result = await scan_fn(transcript)
        rows.append({"transcript_id": transcript.transcript_id, **result.model_dump(mode="json")})
    return rows


def run_scheduled(
    transcripts: Path, scans: Path, policy: dict[str, str], config: PipelineConfig,
    expected_transcripts: int, max_processes: int = 1, source_kind: str = "synthetic_fixture",
) -> dict[str, Any]:
    """Run Scout's real scheduled scan and verify it before parsing recorded results.

    Returns a dict with ``complete`` and either ``rows`` or a recorded blocker.
    Exceptions are captured as an incomplete attempt; there is no fallback to direct mode.
    """
    attempt: dict[str, Any] = {"complete": False, "location": None, "errors": [], "checks": {}}
    try:
        status = scan(
            scanners={SCANNER_NAME: fragmentguard(
                policy, budget=config.budget, horizon=config.horizon, source_kind=source_kind)},
            transcripts=transcripts_from(str(transcripts)),
            scans=str(scans),
            model=MOCK_MODEL,
            max_processes=max_processes,
            display="none",
            fail_on_error=False,
        )
    except BaseException as error:  # noqa: BLE001 - recorded verbatim, then reported incomplete
        if isinstance(error, KeyboardInterrupt):
            raise
        attempt["errors"].append({
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        })
        attempt["blocker"] = f"Scout scan raised {type(error).__name__} before completion"
        return attempt

    attempt["location"] = status.location
    attempt["errors"] = [error.model_dump(mode="json") for error in status.errors]
    summary = status.summary.scanners.get(SCANNER_NAME)
    checks = {
        "status_complete": bool(status.complete),
        "no_errors": not status.errors,
        "scanner_in_summary": summary is not None,
        "all_transcripts_scanned": summary is not None and summary.scans == expected_transcripts,
        "all_results_recorded": summary is not None and summary.results == expected_transcripts,
        "zero_model_tokens": summary is not None and summary.tokens == 0,
        "no_model_usage": summary is not None and not summary.model_usage,
    }
    attempt["checks"] = checks
    attempt["summary"] = status.summary.model_dump(mode="json")
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        attempt["blocker"] = f"Scheduled scan did not pass completion checks: {failed}"
        return attempt

    frame = scan_results_df(status.location, scanner=SCANNER_NAME).scanners[SCANNER_NAME]
    rows = []
    for record in json.loads(frame.to_json(orient="records")):
        if record.get("scan_error"):
            attempt["blocker"] = f"Recorded scanner error for {record['transcript_id']}"
            attempt["errors"].append({"transcript_id": record["transcript_id"], "error": record["scan_error"]})
            return attempt
        for key in ("value", "metadata"):
            if isinstance(record.get(key), str):
                record[key] = json.loads(record[key])
        rows.append(record)
    if sorted(row["transcript_id"] for row in rows) != sorted(set(row["transcript_id"] for row in rows)) \
            or len(rows) != expected_transcripts:
        attempt["blocker"] = "Recorded results do not match the stored transcripts one-to-one"
        return attempt
    attempt["rows"] = sorted(rows, key=lambda row: row["transcript_id"])
    attempt["complete"] = True
    return attempt
