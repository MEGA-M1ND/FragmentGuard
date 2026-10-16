"""Two-phase, deterministic frozen-pointer record-omission experiment."""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from pathlib import Path

from .. import reporting
from ..monitor import check
from ..observation import evaluate_observation, freeze_complete, hide
from ..pipeline import evaluate_stream
from ..schema import input_bindings, load_policy, load_streams, parse_streams
from .common import counts, digest, read, resolved, write


def masks(events, bindings):
    """Unique masks with overlapping category memberships; never hide the target."""
    if len(events) > 11:
        raise ValueError("Exhaustive specification is limited to ten earlier records; "
                         "preregister a new plan for larger logs")
    earlier = events[:-1]
    categories = defaultdict(set)
    categories[frozenset()].add("control")
    for event in earlier:
        if event.operation != "publish":
            categories[frozenset({event.event_id})].add("single_nonpublication")
    for producer in bindings[events[-1].event_id].values():
        if producer is not None:
            categories[frozenset({producer})].add("direct_producer")
    for size in range(len(earlier) + 1):
        for subset in itertools.combinations(earlier, size):
            categories[frozenset(e.event_id for e in subset)].add("exhaustive")
    return [(sorted(hidden), sorted(categories[hidden])) for hidden in
            sorted(categories, key=lambda x: (len(x), sorted(x)))]


def freeze_masks(config: Path, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    datasets = resolved(config)
    metadata, n = [], 0
    preprocessing = {}
    with (output / "observations.jsonl").open("x") as handle:
        for spec in datasets:
            preprocessing[spec["name"]] = {"prefix_events": 0, "input_references": 0}
            policy = load_policy(spec["policy"])
            streams = parse_streams(load_streams(spec["streams"]))
            metadata.append({**{k: str(v.resolve()) if isinstance(v, Path) else v for k, v in spec.items()},
                             "streams_sha256": digest(spec["streams"]), "policy_sha256": digest(spec["policy"])})
            for sid, events in streams.items():
                for index, event in enumerate(events):
                    if event.operation != "publish":
                        continue
                    prefix = events[:index + 1]
                    frozen = freeze_complete({"stream_id": sid, "events": [e.to_dict() for e in prefix]}, policy)
                    # Capture the compatibility bindings BEFORE producing any masked payload.
                    bindings = {eid: {r: ref["event_id"] if ref is not None else None for r, ref in refs.items()}
                                for eid, refs in frozen["bindings"].items()}
                    preprocessing[spec["name"]]["prefix_events"] += len(prefix)
                    preprocessing[spec["name"]]["input_references"] += sum(len(e.inputs) for e in prefix)
                    for hidden, categories in masks(prefix, bindings):
                        observed = hide(frozen, set(hidden))
                        row = {"observation_id": f"obs{n:05d}", "dataset": spec["name"], "stream_id": sid,
                               "publication_id": event.event_id, "categories": categories,
                               "visible_ids": [e["event_id"] for e in observed["events"]],
                               "hidden_ids": hidden, "observation": observed}
                        handle.write(json.dumps(row, sort_keys=True) + "\n")
                        n += 1
    write(output / "plan.json", {
        "schema_version": 1, "source": reporting.source_fingerprint(), "packages": reporting.package_versions(),
        "config_sha256": digest(config), "datasets": metadata, "unique_observations": n,
        "observations_sha256": digest(output / "observations.jsonl"),
        "binding_preprocessing": preprocessing,
        "intervention": "Exhaustive subsets of earlier payloads; retain target publication. Deduplicate masks. "
        "Control, singleton nonpublication, direct-producer and exhaustive categories overlap.",
        "observation_contract": "Trusted workspace-scoped IDs, ticks, produced version identities and visible "
        "input producer pointers. No hidden inputs, agent IDs, operations, sensitivity or ancestry. "
        "Forward state starts empty for every observation. This does not test dishonest pointers/unlogged execution.",
        "settings": {"budget": 3, "horizon": 100, "priority": "depth-first input order"},
    })
    print(f"Frozen {n} unique observations before scoring: {output}")
    return 0


def run_missing(spec: Path, output: Path) -> int:
    plan = read(spec / "plan.json")
    if digest(spec / "observations.jsonl") != plan["observations_sha256"]:
        raise ValueError("Frozen observations changed")
    for dataset in plan["datasets"]:
        for key in ("streams", "policy"):
            if digest(dataset[key]) != dataset[f"{key}_sha256"]:
                raise ValueError(f"Frozen {key} changed")
    output.mkdir(parents=True, exist_ok=False)
    policies = {d["name"]: load_policy(Path(d["policy"])) for d in plan["datasets"]}
    # No unmasked payloads, labels, pair definitions or retained full-state labels enter scoring.
    with (spec / "observations.jsonl").open() as source, (output / "outputs.jsonl").open("x") as handle:
        for line in source:
            row = json.loads(line)
            results = evaluate_observation(row["observation"], policies[row["dataset"]])
            publication = next(p for p in results if p["publication_id"] == row["publication_id"])
            metadata = {k: v for k, v in row.items() if k != "observation"}
            for method, value in publication["methods"].items():
                handle.write(json.dumps({**metadata, "method": method, **value}, sort_keys=True) + "\n")
    # Only after all raw method outputs are on disk: read unmasked histories and evaluator metadata.
    references, evaluator, controls = {}, {}, {}
    source_groups, coverage, label_hashes, pairs_hashes = {}, {}, {}, {}
    for dataset in plan["datasets"]:
        name = dataset["name"]
        labels = reporting.load_ground_truth(Path(dataset["labels"]))
        label_hashes[name] = digest(dataset["labels"])
        for sid, events in parse_streams(load_streams(Path(dataset["streams"]))).items():
            bindings = input_bindings(events)
            for pub in evaluate_stream(events, policies[name]):
                controls[(name, sid, pub["publication_id"])] = pub["methods"]
            pubs = [e for e in events if e.operation == "publish"]
            for index, event in enumerate(events):
                if event.operation != "publish":
                    continue
                key = (name, sid, event.event_id)
                references[key] = check(events[:index + 1], policies[name], bindings)["status"]
                evaluator[key] = reporting.expectation(labels, sid, event.event_id, len(pubs) == 1)
                if evaluator[key] is None:
                    raise ValueError(f"Missing evaluator label: {key}")
        if "execution" in dataset:
            execution = read(Path(dataset["execution"]) / "run_summary.json")
            coverage[name] = {"planned": len(execution["planned"]), "complete": len(execution["complete"]),
                              "incomplete": [e for e in execution["episodes"] if e["status"] != "complete"]}
            for pair in read(dataset["pairs"])["pairs"]:
                for sid in (pair["allowed"], pair["restricted"]):
                    source_groups[(name, execution["stream_ids"][sid])] = pair["pair"]
            pairs_hashes[name] = digest(dataset["pairs"])
    rows, violations, label_mismatches = [], [], []
    for key, verdict in references.items():
        if verdict != evaluator[key]:
            label_mismatches.append({"key": list(key), "reference": verdict, "label": evaluator[key]})
    with (output / "outputs.jsonl").open() as source, (output / "evaluated.jsonl").open("x") as handle:
        for line in source:
            r = json.loads(line)
            key = (r["dataset"], r["stream_id"], r["publication_id"])
            r.update(reference=references[key], evaluator_label=evaluator[key],
                     pair=source_groups.get((r["dataset"], r["stream_id"])))
            wrong = r["status"] not in (r["reference"], "insufficient_evidence")
            expected = controls[key].get(r["method"], controls[key]["full_context_reference"])
            control_mismatch = "control" in r["categories"] and (r["status"] != expected["status"] or (
                r["method"] != "streaming" and r["evidence_ids"] != expected["evidence_ids"]))
            r.update(wrong_definite=wrong, control_mismatch=control_mismatch)
            if wrong or control_mismatch:
                violations.append(r)
            rows.append(r)
            handle.write(json.dumps(r, sort_keys=True) + "\n")
    by_dataset, by_workflow, by_pair, by_category = {}, {}, {}, {}
    for d in plan["datasets"]:
        name = d["name"]
        selected = [r for r in rows if r["dataset"] == name]
        by_dataset[name] = counts(selected)
        by_workflow[name], by_pair[name], by_category[name] = {}, {}, {}
        for sid in sorted({r["stream_id"] for r in selected}):
            by_workflow[name][sid] = counts([r for r in selected if r["stream_id"] == sid])
        for pair in sorted({r["pair"] for r in selected if r["pair"]}):
            by_pair[name][pair] = counts([r for r in selected if r["pair"] == pair])
        for category in sorted({c for r in selected for c in r["categories"]}):
            by_category[name][category] = counts([r for r in selected if category in r["categories"]])
    keyed = defaultdict(dict)
    for row in rows:
        keyed[row["observation_id"]][row["method"]] = row
    wins = []
    for observation, methods in keyed.items():
        correlated = methods["correlated"]
        for baseline in ("fixed_window", "streaming"):
            better = methods[baseline]
            if (better["status"] == better["reference"] and better["status"] in ("alert", "clear")
                    and correlated["status"] == "insufficient_evidence"):
                wins.append({"observation_id": observation, "baseline": baseline,
                             **{k: better[k] for k in ("dataset", "stream_id", "publication_id", "hidden_ids",
                                                      "categories", "reference", "evidence_ids")},
                             "correlated_unresolved": correlated["unresolved_inputs"]})
    write(output / "baseline_wins.json", wins)
    write(output / "summary.json", {
        "unique_observations": plan["unique_observations"], "method_outputs": len(rows),
        "by_dataset": by_dataset, "by_workflow": by_workflow, "by_pair": by_pair, "by_category": by_category,
        "violations": violations, "reference_label_mismatches": label_mismatches, "execution_coverage": coverage,
        "became_uncertain": [{k: r[k] for k in ("dataset", "stream_id", "publication_id", "observation_id",
                                               "method", "hidden_ids", "reference", "unresolved_inputs")}
                             for r in rows if r["method"] in ("streaming", "full_context_reference")
                             and r["status"] == "insufficient_evidence" and r["reference"] in ("alert", "clear")],
        "note": "Post-hoc interventions on the same workflows, not independent or held-out samples. "
        "full_context_reference means ALL VISIBLE records in these rows; reference is the unmasked verdict. "
        "All methods share the same visible payloads/pointers. Category memberships overlap.",
    })
    write(output / "experiment-manifest.json", {
        "schema_version": 1, "source": reporting.source_fingerprint(), "packages": reporting.package_versions(),
        "plan_sha256": digest(spec / "plan.json"), "observations_sha256": plan["observations_sha256"],
        "outputs_sha256": digest(output / "outputs.jsonl"), "labels_sha256": label_hashes,
        "pairs_sha256": pairs_hashes, "paid_requests": 0, "accounted_usd": 0,
        "artifacts": reporting.artifact_hashes(output, ("experiment-manifest.json",)),
    })
    print(f"{plan['unique_observations']} observations, {len(violations)} soundness/control violations, "
          f"{len(label_mismatches)} reference/label mismatches")
    return 1 if violations or label_mismatches else 0
