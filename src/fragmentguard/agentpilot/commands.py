"""CLI commands for the agent-executed pilot (new in this milestone):

- ``agent-run``: execute one scenario (scripted by default; live only with explicit limits)
  and write a development inspection next to the episode evidence;
- ``pilot-freeze``: freeze code, inputs, generation settings, and run order;
- ``pilot-run``: execute the frozen twelve scenarios once each;
- ``pilot-analyze``: compare the saved direct/scheduled replays and join labels post hoc.

Existing commands (``demo``, ``replay``) replay the saved dataset; see docs/agent_pilot.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .backends import Budget, LiveBackend, LiveLimits, LiveNotAuthorized, ScriptedBackend


def _sibling(scenario: Path, name: str) -> Path:
    for directory in (scenario.parent, scenario.parent.parent):
        if (directory / name).is_file():
            return directory / name
    raise SystemExit(f"Could not find {name} next to {scenario}; pass it explicitly")


def agent_run(args: argparse.Namespace) -> int:
    from ..pipeline import evaluate_streams
    from .episode import run_episode
    from .ledger_labels import label_publication

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    sources_path = args.sources or _sibling(args.scenario, "sources.json")
    catalog_path = args.catalog or _sibling(args.scenario, "catalog.json")
    sources = json.loads(sources_path.read_text(encoding="utf-8"))["sources"]
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    budget = None
    if args.backend == "live":
        if not args.model or not args.limits:
            raise SystemExit("Live runs need --model and --limits (see experiments/agent_pilot/limits.example.json)")
        try:
            limits = LiveLimits.load(args.limits)
        except LiveNotAuthorized as error:
            raise SystemExit(f"Live run blocked: {error}") from error
        if limits.model != args.model:
            raise SystemExit("--model must equal the model named in the limits file")
        budget = Budget(limits)
        estimate = budget.pessimistic_run_max_usd(1)
        print(f"Pessimistic maximum for this episode: ${estimate:.4f} (cap ${limits.max_spend_usd:.2f}; "
              f"pricing from {limits.pricing_source} at {limits.pricing_retrieved_utc})")
        if estimate > limits.max_spend_usd:
            raise SystemExit("Pessimistic maximum exceeds the cap; lower the limits or raise the cap explicitly")
        backend: Any = LiveBackend(limits, budget)
        agent_limits = limits.agent_limits()
    else:
        script = args.script or args.scenario.parent.parent / "scripted_plans" / args.scenario.name
        backend = ScriptedBackend(json.loads(script.read_text(encoding="utf-8")))
        from .backends import AgentLimits

        agent_limits = AgentLimits()
    manifest = run_episode(scenario, sources, backend, args.output, limits=agent_limits,
                           provenance={"command": "agent-run", "trace_backend": backend.kind})
    inspection: dict[str, Any] = {
        "kind": "development inspection (not pilot evidence)",
        "trace_backend": backend.kind,
        "status": manifest["status"],
        "incomplete_reasons": manifest["incomplete_reasons"],
        "agent_outcomes": manifest["agent_outcomes"],
        "binding_agreement": manifest["normalization"].get("binding_agreement"),
        "budget_ledger": budget.ledger if budget else None,
    }
    if manifest["status"] == "complete":
        ledger = json.loads((args.output / "resource_ledger.json").read_text(encoding="utf-8"))
        inspection["ledger_label"] = label_publication(ledger, catalog)
        streams = json.loads((args.output / "normalized_stream.json").read_text(encoding="utf-8"))
        publications = next(iter(evaluate_streams(streams, catalog).values()))
        inspection["views"] = {m: {k: v[k] for k in ("status", "evidence_ids", "unresolved_inputs")}
                               for m, v in publications[-1]["methods"].items()}
    (args.output / "inspection.json").write_text(json.dumps(inspection, indent=2) + "\n", encoding="utf-8")
    print(f"agent-run ({backend.kind}): {manifest['status']} {manifest['incomplete_reasons'] or ''}")
    print(f"agent outcomes: {manifest['agent_outcomes']}")
    if "views" in inspection:
        print(f"ledger label: {inspection['ledger_label']['verdict']}; full context: "
              f"{inspection['views']['full_context_reference']['status']}")
    print(f"Evidence: {args.output}")
    return 0 if manifest["status"] == "complete" else 3


def pilot_freeze(args: argparse.Namespace) -> int:
    from .pilot import freeze

    try:
        record = freeze(args.config, args.output, args.backend, args.limits)
    except LiveNotAuthorized as error:
        raise SystemExit(f"Live freeze blocked: {error}") from error
    print(f"Frozen {record['pilot_id']} ({args.backend}) at code {record['code']['git_commit']}")
    print(f"Freeze record: {args.output / 'freeze.json'}")
    return 0


def pilot_run(args: argparse.Namespace) -> int:
    from .pilot import run

    try:
        summary = run(args.freeze, args.output, args.limits)
    except LiveNotAuthorized as error:
        raise SystemExit(f"Live run blocked: {error}") from error
    print(f"pilot-run ({summary['trace_backend']}): {len(summary['complete'])} of {len(summary['planned'])} "
          "episodes complete")
    for episode in summary["episodes"]:
        print(f"  {episode['episode_id']}: {episode['status']} {episode['incomplete_reasons'] or ''}")
    print(f"Dataset for replay: {args.output / 'dataset'}; evaluator labels: {args.output / 'evaluator'}")
    return 0


def pilot_analyze(args: argparse.Namespace) -> int:
    from .pilot import analyze

    result = analyze(args.direct, args.scout, args.labels, args.execution, args.output)
    print(f"{result['evidence_status']}")
    print(f"completed {result['counts']['completed_episodes']}/{result['counts']['planned_episodes']}; "
          f"evaluable pairs {result['counts']['evaluable_pairs']}/{result['counts']['planned_pairs']}; "
          f"direct==scheduled: {result['direct_scheduled_agreement']['agree']}")
    for method, counts in result["pair_separation"].items():
        print(f"  {method}: separated {counts['separated']} of {counts['evaluable_pairs']} evaluable pairs")
    print(f"Report: {args.output / 'pilot_report.md'}")
    return 0


def register(commands: Any) -> None:
    run = commands.add_parser("agent-run", help="Execute one agent scenario (scripted by default)")
    run.add_argument("--backend", choices=("scripted", "live"), default="scripted")
    run.add_argument("--scenario", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True, help="New directory (must not exist)")
    run.add_argument("--script", type=Path, default=None, help="Scripted plan (default: ../scripted_plans/<id>.json)")
    run.add_argument("--sources", type=Path, default=None)
    run.add_argument("--catalog", type=Path, default=None)
    run.add_argument("--model", default=None, help="Live only: exact provider/model ID")
    run.add_argument("--limits", type=Path, default=None, help="Live only: limits file with live_enabled true")
    run.set_defaults(handler=agent_run)

    frz = commands.add_parser("pilot-freeze", help="Freeze the pilot before generation")
    frz.add_argument("--config", type=Path, required=True)
    frz.add_argument("--output", type=Path, required=True)
    frz.add_argument("--backend", choices=("scripted", "live"), default="scripted")
    frz.add_argument("--limits", type=Path, default=None)
    frz.set_defaults(handler=pilot_freeze)

    prun = commands.add_parser("pilot-run", help="Execute each frozen scenario once")
    prun.add_argument("--freeze", type=Path, required=True)
    prun.add_argument("--output", type=Path, required=True)
    prun.add_argument("--limits", type=Path, default=None)
    prun.set_defaults(handler=pilot_run)

    ana = commands.add_parser("pilot-analyze", help="Post-hoc analysis of the saved replays")
    ana.add_argument("--direct", type=Path, required=True)
    ana.add_argument("--scout", type=Path, required=True)
    ana.add_argument("--labels", type=Path, required=True)
    ana.add_argument("--execution", type=Path, required=True)
    ana.add_argument("--output", type=Path, required=True)
    ana.set_defaults(handler=pilot_analyze)
