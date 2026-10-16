"""Installed entry point: python -m fragmentguard.experiments compare --config ..."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import reporting
from ..schema import check_catalog_roots_immutable, input_bindings, load_policy, load_streams, parse_streams
from .common import counts, digest, read, resolved, write
from .evaluate import METHODS, evaluate


def compare(config, output):
    output.mkdir(parents=True, exist_ok=False)
    rows, metadata = [], []
    datasets = resolved(config)
    # Score first. Labels and pair files are intentionally unopened here.
    for spec in datasets:
        streams = parse_streams(load_streams(spec["streams"]))
        policy = load_policy(spec["policy"])
        preprocessing = {"events": 0, "input_references": 0}
        for sid, events in streams.items():
            check_catalog_roots_immutable(events, policy)
            bindings = input_bindings(events)
            preprocessing["events"] += len(events)
            preprocessing["input_references"] += sum(len(e.inputs) for e in events)
            for pub in evaluate(events, policy, bindings):
                rows.extend({"dataset": spec["name"], "source_kind": spec["kind"], "stream_id": sid,
                             "publication_id": pub["publication_id"], "method": method, **value}
                            for method, value in pub["methods"].items())
        metadata.append({"dataset": spec["name"], "kind": spec["kind"], "binding_preprocessing": preprocessing,
                         "streams_sha256": digest(spec["streams"]), "policy_sha256": digest(spec["policy"])})
    write(output / "outputs.json", rows)
    evaluated, summaries = [], {}
    for spec in datasets:
        labels = reporting.load_ground_truth(spec["labels"])
        selected = [r for r in rows if r["dataset"] == spec["name"]]
        full = {(r["stream_id"], r["publication_id"]): r["status"] for r in selected
                if r["method"] == "full_context_reference"}
        for r in selected:
            key = (r["stream_id"], r["publication_id"])
            reference = reporting.expectation(labels, *key, single=sum(k[0] == key[0] for k in full) == 1)
            if reference is None:
                raise ValueError(f"Missing evaluator label: {key}")
            evaluated.append({**r, "reference": reference,
                              "full_context": full[key]})
        joined = [r for r in evaluated if r["dataset"] == spec["name"]]
        summary = {"counts": counts(joined), "labels_sha256": digest(spec["labels"]),
                   "streaming_full_mismatches": [r for r in joined if r["method"] == "streaming"
                                                 and r["status"] != r["full_context"]],
                   "reference_label_mismatches": [r for r in joined if r["method"] == "full_context_reference"
                                                  and r["status"] != r["reference"]]}
        if "execution" in spec:
            execution = read(spec["execution"] / "run_summary.json")
            summary["execution_coverage"] = {"planned": len(execution["planned"]),
                                              "complete": len(execution["complete"]),
                                              "incomplete": [e for e in execution["episodes"]
                                                             if e["status"] != "complete"]}
            pairs = read(spec["pairs"])["pairs"]
            summary["pair_separation"] = {}
            by_key = {(r["stream_id"], r["method"]): r for r in joined}
            for method in METHODS:
                outcomes = []
                for pair in pairs:
                    a = by_key.get((execution["stream_ids"][pair["allowed"]], method))
                    b = by_key.get((execution["stream_ids"][pair["restricted"]], method))
                    evaluable = bool(a and b and a["reference"] == "clear" and b["reference"] == "alert")
                    outcomes.append({"pair": pair["pair"], "evaluable": evaluable,
                                     "separated": bool(evaluable and a["status"] == "clear"
                                                       and b["status"] == "alert")})
                summary["pair_separation"][method] = outcomes
        summaries[spec["name"]] = summary
    write(output / "evaluated.json", evaluated)
    write(output / "summary.json", summaries)
    write(output / "manifest.json", {"schema_version": 1, "source": reporting.source_fingerprint(),
                                     "packages": reporting.package_versions(), "config_sha256": digest(config),
                                     "datasets": metadata, "settings": {"budget": 3, "horizon": 100,
                                     "priority": "depth-first input order"},
                                     "outputs_sha256": digest(output / "outputs.json"),
                                     "note": "One shared complete-log binding pass per stream, before scoring. "
                                     "Streaming sees every arriving event and retains all version states; "
                                     "bounded checker views have different information/memory costs. "
                                     "No runtime speedup or equal total compute claim."})
    failures = any(s["streaming_full_mismatches"] or s["reference_label_mismatches"] for s in summaries.values())
    print(json.dumps({k: {m: c["correct"] for m, c in v["counts"].items()} for k, v in summaries.items()}, indent=2))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    comparison = sub.add_parser("compare", help="Complete-log five-method comparison; evaluator joins last")
    comparison.add_argument("--config", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    freeze = sub.add_parser("freeze-masks", help="Freeze exact pointers and exhaustive record masks before scoring")
    freeze.add_argument("--config", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    missing = sub.add_parser("missing", help="Score a frozen partial-observation specification")
    missing.add_argument("--spec", type=Path, required=True)
    missing.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compare":
        return compare(args.config.resolve(), args.output.resolve())
    from .missing import freeze_masks, run_missing

    if args.command == "freeze-masks":
        return freeze_masks(args.config.resolve(), args.output.resolve())
    return run_missing(args.spec.resolve(), args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
