"""Read four fixtures through Scout's database and invoke its scanner without API calls."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

from inspect_ai.event import InfoEvent
from inspect_scout import (
    Transcript, TranscriptContent, scan, scan_results_df, transcripts_db, transcripts_from,
)

from .core import parse_events
from .scout import fragmentguard

ROOT = Path(__file__).resolve().parent.parent


async def prepare_database(location: Path, streams: list[dict]) -> None:
    database = transcripts_db(str(location))
    await database.connect()
    try:
        transcripts = []
        for stream in streams:
            if set(stream) != {"stream_id", "events"}:
                raise ValueError("Only stream identity and events may enter the scanner")
            parse_events(stream["events"])
            transcripts.append(Transcript(
                transcript_id=stream["stream_id"],
                source_type="fragmentguard_synthetic",
                events=[InfoEvent(
                    uuid=record["event_id"],
                    timestamp=datetime(2026, 10, 7, tzinfo=timezone.utc)
                    + timedelta(seconds=record["tick"]),
                    source="fragmentguard.synthetic",
                    data=record,
                ) for record in stream["events"]],
            ))
        await database.insert(transcripts)
    finally:
        await database.disconnect()


async def run_direct(location: Path, policy: dict[str, str]) -> list[dict]:
    """Invoke the decorated scanner after a real Scout database round trip.

    This skips Scout's scan scheduler, model setup, progress tracking, and recorder.
    It neither patches dependencies nor simulates a successful scheduled scan.
    """
    database = transcripts_db(str(location))
    scanner = fragmentguard(policy, budget=3)
    rows = []
    await database.connect()
    try:
        async for info in database.select():
            transcript = await database.read(info, TranscriptContent(events=["info"]))
            result = await scanner(transcript)
            rows.append({"transcript_id": transcript.transcript_id, **result.model_dump(mode="json")})
    finally:
        await database.disconnect()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "first-run")
    parser.add_argument("--max-processes", type=int, default=1,
                        help="Scout worker setting; must be positive")
    parser.add_argument("--mode", choices=("direct", "scout"), default="direct",
                        help="direct invokes the scanner; scout uses the full scheduler")
    args = parser.parse_args()
    if args.max_processes < 1:
        parser.error("--max-processes must be positive")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Output already exists. Choose a fresh --output directory to preserve run evidence.")
    output.mkdir(parents=True)
    streams = json.loads((ROOT / "fixtures" / "streams.json").read_text())
    policy = json.loads((ROOT / "fixtures" / "policy.json").read_text())
    asyncio.run(prepare_database(output / "transcripts", streams))
    scan_location = None
    if args.mode == "scout":
        status = scan(
            scanners={"fragmentguard": fragmentguard(policy, budget=3)},
            transcripts=transcripts_from(str(output / "transcripts")),
            scans=str(output / "scans"),
            model="mockllm/model",
            max_processes=args.max_processes,
            display="none",
            fail_on_error=True,
        )
        if not status.complete or status.errors:
            raise RuntimeError(f"Incomplete scan: {status.errors}")
        scan_location = status.location
        results = scan_results_df(status.location)
        frame = results.scanners["fragmentguard"]
        frame.to_json(output / "scanner-results.json", orient="records", indent=2)
        rows = json.loads((output / "scanner-results.json").read_text())
    else:
        rows = asyncio.run(run_direct(output / "transcripts", policy))
        (output / "scanner-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    # Ground truth enters only after scanning, for the evaluator's report.
    truth = json.loads((ROOT / "fixtures" / "ground_truth.json").read_text())["expected"]
    outcomes = []
    for row in rows:
        value = row["value"]
        if isinstance(value, str):
            value = json.loads(value)
        outcomes.append({
            "stream_id": row["transcript_id"],
            "expected_toy_policy_outcome": truth[row["transcript_id"]],
            "publications": value["publications"],
        })
    outcomes.sort(key=lambda item: item["stream_id"])
    if len(outcomes) != len(streams):
        raise RuntimeError("Missing or extra Scout result rows")
    for outcome in outcomes:
        publication = outcome["publications"]
        if len(publication) != 1:
            raise RuntimeError("Smoke fixtures must each have exactly one publication")
        for method in ("correlated", "full_context_reference"):
            if publication[0]["methods"][method]["status"] != outcome["expected_toy_policy_outcome"]:
                raise RuntimeError(f"Fixture expectation failed for {outcome['stream_id']} / {method}")
    report = {
        "purpose": "Integration smoke test; not a paper replication or real-world detection result.",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scanner": "Deterministic provenance reference checker",
        "model_api_calls": 0,
        "execution_mode": args.mode,
        "scanner_invocation_complete": True,
        "full_scout_scan_complete": args.mode == "scout",
        "max_processes": args.max_processes,
        "scan_location": scan_location,
        "fixture_hashes": {
            name: hashlib.sha256((ROOT / "fixtures" / name).read_bytes()).hexdigest()
            for name in ("streams.json", "policy.json", "ground_truth.json")
        },
        "runtime": {
            "python": platform.python_version(),
            "inspect-ai": importlib.metadata.version("inspect-ai"),
            "inspect-scout": importlib.metadata.version("inspect-scout"),
        },
        "outcomes": outcomes,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Scanner completed ({args.mode} mode): 4 synthetic streams; no model API calls.")
    print("stream     expected  per_agent              fixed_window           correlated")
    for outcome in outcomes:
        methods = outcome["publications"][0]["methods"]
        print(f"{outcome['stream_id']:10} {outcome['expected_toy_policy_outcome']:9} "
              f"{methods['per_agent']['status']:22} {methods['fixed_window']['status']:22} "
              f"{methods['correlated']['status']}")
    print(f"Report: {output / 'report.json'}")


if __name__ == "__main__":
    main()
