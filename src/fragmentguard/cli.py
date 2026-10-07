"""Command-line entry point: ``fragmentguard demo`` and ``fragmentguard replay``.

``demo`` runs streams through Inspect Scout in ``direct`` or ``scout`` mode. It uses
the bundled fixtures by default; ``--streams``, ``--policy``, ``--labels``,
``--budget`` and ``--horizon`` run custom inputs through the same two paths.

Exit codes for ``demo``:
- 0: the run completed, and the gated methods matched the labels (or there were no labels);
- 1: the run completed, but a gated method did not match its label;
- 3: the selected execution path did not complete (artifacts and the blocker are
  still written).

Invalid input, a missing labels file, and an existing output directory stop the
run before any scanning.
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


def _input_record(path: Path | None, bundled: str) -> dict[str, str]:
    source = path if path is not None else FIXTURE_DIR / bundled
    return {"source": str(path) if path is not None else f"bundled:{bundled}",
            "sha256": reporting.sha256_file(source)}


def run_demo(
    mode: str, output: Path, max_processes: int = 1, *, streams_path: Path | None = None,
    policy_path: Path | None = None, labels_path: Path | None = None,
    config: PipelineConfig = PipelineConfig(),
    gate_methods: tuple[str, ...] = reporting.EVALUATED_METHODS,
) -> int:
    if output.exists():
        raise SystemExit(
            f"Refusing to write to existing path {output}. Choose a new --output directory; "
            "earlier runs are preserved as separate attempts."
        )
    # Bundled fixtures carry bundled labels; custom streams are unlabelled unless
    # --labels is given. Labels are only located here, never read before scanning.
    use_bundled_labels = streams_path is None and labels_path is None
    if labels_path is not None and not labels_path.is_file():
        raise SystemExit(f"Labels file not found: {labels_path}")
    started = utc_now()
    streams, policy = load_streams(streams_path), load_policy(policy_path)
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
    labels = None
    if complete:
        reporting.write_json(output / "scanner-results.json", rows)
        stream_results = reporting.stream_results_from_rows(rows)
        # Evaluator labels enter only now, after scanner outputs have been produced.
        if use_bundled_labels or labels_path is not None:
            labels = reporting.load_ground_truth(labels_path)
            evaluation = reporting.evaluate(stream_results, labels, gate_methods)

    report = reporting.build_report(
        mode=mode, complete=complete, path_completed=PATHS[mode] if complete else None,
        config=config.to_dict(), stream_results=stream_results, evaluation=evaluation, blocker=blocker,
    )
    reporting.write_json(output / "report.json", report)
    (output / "report.md").write_text(reporting.render_markdown(report, labels), encoding="utf-8")

    inputs = {
        "streams": _input_record(streams_path, "streams.json"),
        "policy": _input_record(policy_path, "policy.json"),
        "labels (evaluator-only, read after scanning)": (
            _input_record(labels_path, "ground_truth.json") if labels is not None else None
        ),
    }
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
            "evaluator_gate_methods": list(gate_methods) if evaluation else None,
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
        "inputs": inputs,
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
    print(f"{'stream':9} {'pub':5} {'label':10} " + " ".join(f"{m:24}" for m in METHODS))
    for stream_id, publications in stream_results.items():
        for publication in publications:
            label = reporting.expectation(labels, stream_id, publication["publication_id"],
                                          len(publications) == 1) or "-"
            cells = " ".join(f"{publication['methods'][m]['status']:24}" for m in METHODS)
            print(f"{stream_id:9} {publication['publication_id']:5} {label:10} {cells}")
    print("Model generation calls: none (" + manifest["model_generation"]["basis"] + ")")
    if evaluation is None:
        print("Evaluator check: not performed (no labels supplied)")
        code = EXIT_OK
    else:
        gate = ", ".join(gate_methods) or "none"
        print(f"Evaluator check (gated: {gate}): {'matched' if evaluation['all_match'] else 'MISMATCH'}")
        code = EXIT_OK if evaluation["all_match"] else EXIT_MISMATCH
    print(f"Report: {output / 'report.md'}")
    return code


def run_replay(streams_path: Path | None, policy_path: Path | None, budget: int, horizon: int) -> int:
    """Evaluate a streams file with the core pipeline only (no Scout, no labels)."""
    config = PipelineConfig(budget, horizon)
    results = evaluate_streams(load_streams(streams_path), load_policy(policy_path), config)
    json.dump({"config": config.to_dict(), "streams": results}, sys.stdout, indent=2)
    print()
    return EXIT_OK


def _gate(value: str) -> tuple[str, ...]:
    if value.strip().lower() == "none":
        return ()
    methods = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = [method for method in methods if method not in METHODS]
    if unknown or not methods:
        raise argparse.ArgumentTypeError(f"choose from {', '.join(METHODS)}, or 'none'")
    return methods


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fragmentguard", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser("demo", help="Run streams through Scout (bundled fixtures by default)")
    demo.add_argument("--mode", choices=("direct", "scout"), required=True,
                      help="direct: DB round trip + direct scanner call; scout: real scheduled scan")
    demo.add_argument("--output", type=Path, required=True, help="New run directory (must not exist)")
    demo.add_argument("--max-processes", type=int, default=1, help="Scout worker processes (scout mode)")
    demo.add_argument("--streams", type=Path, default=None, help="Custom streams JSON (default: bundled)")
    demo.add_argument("--policy", type=Path, default=None, help="Custom policy JSON (default: bundled)")
    demo.add_argument("--labels", type=Path, default=None,
                      help="Evaluator labels JSON, read only after scanning (default: bundled labels "
                           "for bundled streams; none for custom streams)")
    demo.add_argument("--budget", type=int, default=PipelineConfig.budget)
    demo.add_argument("--horizon", type=int, default=PipelineConfig.horizon)
    demo.add_argument("--gate", type=_gate, default=reporting.EVALUATED_METHODS,
                      help="Comma-separated methods whose label agreement sets the exit code, or 'none' "
                           "(default: correlated,full_context_reference)")

    replay = commands.add_parser("replay", help="Evaluate a streams file with the core pipeline only")
    replay.add_argument("--streams", type=Path, default=None, help="Streams JSON (default: bundled fixtures)")
    replay.add_argument("--policy", type=Path, default=None, help="Policy JSON (default: bundled policy)")
    replay.add_argument("--budget", type=int, default=PipelineConfig.budget)
    replay.add_argument("--horizon", type=int, default=PipelineConfig.horizon)

    args = parser.parse_args(argv)
    if args.command == "demo":
        if args.max_processes < 1:
            parser.error("--max-processes must be positive")
        return run_demo(
            args.mode, args.output, args.max_processes, streams_path=args.streams,
            policy_path=args.policy, labels_path=args.labels,
            config=PipelineConfig(args.budget, args.horizon), gate_methods=args.gate,
        )
    return run_replay(args.streams, args.policy, args.budget, args.horizon)


if __name__ == "__main__":
    raise SystemExit(main())
