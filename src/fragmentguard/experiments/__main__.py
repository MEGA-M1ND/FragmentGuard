"""Installed entry point: python -m fragmentguard.experiments compare --config ..."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .. import reporting
from ..schema import check_catalog_roots_immutable, input_bindings, load_policy, load_streams, parse_streams
from .evaluate import METHODS, evaluate


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolved(spec_path):
    spec = read(spec_path)
    return [{**d, **{key: spec_path.parent / d[key] for key in
                    ("streams", "policy", "labels", "execution", "pairs") if key in d}}
            for d in spec["datasets"]]


def counts(rows):
    result = {}
    for method in METHODS:
        selected = [r for r in rows if r["method"] == method]
        c = Counter(r["status"] for r in selected)
        result[method] = {"publications": len(selected), "verdicts": dict(c),
                          "correct": sum(r["status"] == r["reference"] for r in selected),
                          "insufficient_evidence": c["insufficient_evidence"],
                          "wrong_clear": sum(r["status"] == "clear" and r["reference"] == "alert" for r in selected),
                          "wrong_alert": sum(r["status"] == "alert" and r["reference"] == "clear" for r in selected),
                          "definitive": c["clear"] + c["alert"]}
    return result


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
    args = parser.parse_args()
    return compare(args.config.resolve(), args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
