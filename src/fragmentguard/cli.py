"""Command-line entry point: ``fragmentguard demo`` and ``fragmentguard replay``.

Exit codes for ``demo``: 0 complete and evaluator check matched; 1 complete but an
evaluator expectation did not match; 3 the selected execution path did not
complete (artifacts and the blocker are still written). Invalid input and an
existing output directory stop the run before scanning.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import reporting
from .pipeline import METHODS, PipelineConfig, evaluate_streams
from .schema import FIXTURE_DIR, load_policy, load_streams

EXIT_OK, EXIT_MISMATCH, EXIT_INCOMPLETE = 0, 1, 3
PATHS = {
    "direct": "direct: Scout transcript database round trip, then direct invocation of the "
              "decorated scanner (Scout scheduler and recorder skipped; no model created)",
    "scout": "scout: Scout scheduled scan with the mock model setting and Scout's recorder",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_demo(mode: str, output: Path, max_processes: int = 1) -> int:
    if output.exists():
        raise SystemExit(
            f"Refusing to write to existing path {output}. Choose a new --output directory; "
            "earlier runs are preserved as separate attempts."
        )
    started = utc_now()
    streams, policy, config = load_streams(), load_policy(), PipelineConfig()
    output.mkdir(parents=True)
    transcripts = output / "transcripts"

    rows: list[dict[str, Any]] | None = None
    scheduled: dict[str, Any] | str = "not attempted (direct mode)"
    blocker = None
    try:
        from . import scout  # Imported here so the core stays usable without Scout.

        asyncio.run(scout.write_database(transcripts, streams))
        if mode == "direct":
            rows = asyncio.run(scout.run_direct(transcripts, policy, config))
        else:
            attempt = scout.run_scheduled(
                transcripts, output / "scans", policy, config, len(streams), max_processes
            )
            scheduled = {key: value for key, value in attempt.items() if key != "rows"}
            if attempt["location"]:
                scheduled["location"] = Path(attempt["location"]).resolve().relative_to(
                    output.resolve()).as_posix()
            reporting.write_json(output / "scheduled-attempt.json", scheduled)
            if attempt["complete"]:
                rows = attempt["rows"]
            else:
                blocker = attempt.get("blocker", "Scheduled scan incomplete")
    except Exception as error:  # noqa: BLE001 - preserved as an incomplete attempt
        blocker = f"{type(error).__name__}: {error}"
        (output / "execution-error.txt").write_text(traceback.format_exc(), encoding="utf-8")

    complete = rows is not None
    stream_results = None
    evaluation = None
    expected = None
    if complete:
        reporting.write_json(output / "scanner-results.json", rows)
        stream_results = reporting.stream_results_from_rows(rows)
        # Evaluator labels enter only now, after scanner outputs have been produced.
        expected = reporting.load_ground_truth()
        evaluation = reporting.evaluate(stream_results, expected)

    report = reporting.build_report(
        mode=mode, complete=complete, path_completed=PATHS[mode] if complete else None,
        config=config.to_dict(), stream_results=stream_results, evaluation=evaluation, blocker=blocker,
    )
    reporting.write_json(output / "report.json", report)
    (output / "report.md").write_text(reporting.render_markdown(report, expected), encoding="utf-8")

    manifest = {
        "run_id": output.name,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "execution_mode": mode,
        "completion": {
            "status": report["run_status"],
            "path_completed": report["path_completed"],
            "blocker": blocker,
            "scheduled_scan": scheduled,
            "evaluator_check_all_match": evaluation["all_match"] if evaluation else None,
        },
        "model_generation": {
            "invoked": False if mode == "direct" or complete else None,
            "basis": (
                "design: direct mode constructs no model and the scanner makes no generate calls (not instrumented)"
                if mode == "direct" else
                "measured: Scout summary reported 0 tokens and empty model_usage" if complete else
                "unknown: scheduled scan did not complete"
            ),
        },
        "inputs": {
            "streams.json": reporting.sha256_file(FIXTURE_DIR / "streams.json"),
            "policy.json": reporting.sha256_file(FIXTURE_DIR / "policy.json"),
            "ground_truth.json (evaluator-only, read after scanning)":
                reporting.sha256_file(FIXTURE_DIR / "ground_truth.json"),
        },
        "config": {**config.to_dict(), "sha256": config.sha256(), "max_processes": max_processes},
        "source": reporting.source_fingerprint(),
        "environment": reporting.environment(),
        "artifacts": reporting.artifact_hashes(output),
        "integrity_note": (
            "Hashes establish file identity, not authenticity against a malicious logger. Scout "
            "recorder files may contain absolute paths written by Scout itself."
        ),
    }
    reporting.write_json(output / "manifest.json", manifest)

    print(f"FragmentGuard demo ({mode} mode): {report['run_status']}")
    if not complete:
        print(f"Blocker: {blocker}")
        print("No outcomes were recorded. This run is incomplete; it did not fall back to another mode.")
        print(f"Artifacts: {output}")
        return EXIT_INCOMPLETE
    print(f"Path completed: {PATHS[mode]}")
    print(f"{'stream':9} {'expected':10} " + " ".join(f"{m:24}" for m in METHODS))
    for stream_id, publications in stream_results.items():
        for publication in publications:
            cells = " ".join(f"{publication['methods'][m]['status']:24}" for m in METHODS)
            print(f"{stream_id:9} {expected.get(stream_id, '-'):10} {cells}")
    print("Model generation calls: none (" + manifest["model_generation"]["basis"] + ")")
    print(f"Evaluator check (correlated, full context): {'matched' if evaluation['all_match'] else 'MISMATCH'}")
    print(f"Report: {output / 'report.md'}")
    return EXIT_OK if evaluation["all_match"] else EXIT_MISMATCH


def run_replay(streams_path: Path | None, policy_path: Path | None, budget: int, horizon: int) -> int:
    """Evaluate a streams file with the core pipeline only (no Scout, no labels)."""
    results = evaluate_streams(load_streams(streams_path), load_policy(policy_path), PipelineConfig(budget, horizon))
    json.dump({"config": PipelineConfig(budget, horizon).to_dict(), "streams": results}, sys.stdout, indent=2)
    print()
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fragmentguard", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="Run the four bundled synthetic fixtures through Scout")
    demo.add_argument("--mode", choices=("direct", "scout"), required=True,
                      help="direct: DB round trip + direct scanner call; scout: real scheduled scan")
    demo.add_argument("--output", type=Path, required=True, help="New run directory (must not exist)")
    demo.add_argument("--max-processes", type=int, default=1, help="Scout worker processes (scout mode)")

    replay = commands.add_parser("replay", help="Evaluate a streams file with the core pipeline only")
    replay.add_argument("--streams", type=Path, default=None, help="Streams JSON (default: bundled fixtures)")
    replay.add_argument("--policy", type=Path, default=None, help="Policy JSON (default: bundled policy)")
    replay.add_argument("--budget", type=int, default=PipelineConfig.budget)
    replay.add_argument("--horizon", type=int, default=PipelineConfig.horizon)

    args = parser.parse_args(argv)
    if args.command == "demo":
        if args.max_processes < 1:
            parser.error("--max-processes must be positive")
        return run_demo(args.mode, args.output, args.max_processes)
    return run_replay(args.streams, args.policy, args.budget, args.horizon)


if __name__ == "__main__":
    raise SystemExit(main())
