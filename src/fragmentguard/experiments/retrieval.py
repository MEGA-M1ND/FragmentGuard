"""Offline evidence retrieval: original correlation versus streaming + provenance.

Both selectors use the same visible payload archive, policy and frozen producer
metadata. Reference checks and subset oracles run only AFTER raw outputs exist.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path

from .. import reporting
from ..correlation import correlate_selection
from ..monitor import check
from ..observation import freeze_complete, validate_observation
from ..provenance import StreamingProvenance
from ..schema import load_policy, load_streams, parse_streams
from .common import digest, read, resolved, write


def encoded_bytes(value):
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def observations(config):
    spec = read(config)
    for dataset in resolved(config):
        policy = load_policy(dataset["policy"])
        for sid, events in parse_streams(load_streams(dataset["streams"])).items():
            for index, event in enumerate(events):
                if event.operation == "publish":
                    raw = freeze_complete({"stream_id": sid, "events": [e.to_dict() for e in events[:index + 1]]},
                                          policy)
                    yield {"id": f"complete/{dataset['name']}/{sid}/{event.event_id}", "group": "complete",
                           "dataset": dataset["name"], "target": event.event_id, "policy": policy, "raw": raw,
                           "shared_binding_preprocessing_events": index + 1}
    masked = config.parent / spec["masked_specification"]
    plan = read(masked / "plan.json")
    if digest(masked / "observations.jsonl") != plan["observations_sha256"]:
        raise ValueError("Frozen masked observations changed")
    policy_by_name = {d["name"]: load_policy(Path(d["policy"])) for d in plan["datasets"]}
    with (masked / "observations.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            yield {"id": f"masked/{row['observation_id']}",
                   "group": "masked_control" if not row["hidden_ids"] else "masked",
                   "dataset": row["dataset"], "target": row["publication_id"],
                   "policy": policy_by_name[row["dataset"]], "raw": row["observation"],
                   "shared_binding_preprocessing_events": 0}


def minimum_support(events, policy, bindings, reference, horizon):
    """Post-hoc tiny exhaustive oracle; never consulted by either selector."""
    if reference == "insufficient_evidence":
        return None
    earlier = [e for e in events[:-1] if events[-1].tick - e.tick <= horizon]
    if len(earlier) > 10:
        raise ValueError("Subset oracle supports at most ten earlier records")
    for size in range(len(earlier) + 1):
        for subset in itertools.combinations(earlier, size):
            if check([*subset, events[-1]], policy, bindings)["status"] == reference:
                return size + 1
    return None


def run(config: Path, output: Path):
    protocol = read(config)
    budgets, horizon = protocol["budgets"], protocol["horizon"]
    if (not budgets or any(type(b) is not int or b < 1 for b in budgets)
            or budgets != sorted(set(budgets)) or type(horizon) is not int or horizon < 0):
        raise ValueError("Ordered unique positive budgets and nonnegative horizon required")
    output.mkdir(parents=True, exist_ok=False)
    datasets = resolved(config)
    input_hashes = {str(dataset[key]): digest(dataset[key]) for dataset in datasets for key in ("streams", "policy")}
    masked = config.parent / protocol["masked_specification"]
    input_hashes[str(masked / "observations.jsonl")] = digest(masked / "observations.jsonl")
    write(output / "protocol.json", {"source": reporting.source_fingerprint(), "config_sha256": digest(config),
                                    "protocol": protocol, "input_hashes": input_hashes,
                                    "method": "Known-restricted-parent-first stable DFS versus input-order DFS. "
                                    "Checker budgets do not equate memory, tokens or total compute."})
    examples = list(observations(config))
    cached = {}
    with (output / "outputs.jsonl").open("x") as handle:
        for obs in examples:
            events, bindings = validate_observation(obs["raw"], obs["policy"])
            state = StreamingProvenance(obs["policy"])
            archive = {}
            decision = None
            for event in events:
                decision = state.update(event, bindings[event.event_id])
                archive[event.event_id] = event
            if events[-1].event_id != obs["target"] or decision is None:
                raise ValueError("Observation must end at its target publication")
            cached[obs["id"]] = decision["status"]
            shared = {"archive_events": len(events), "archive_payload_canonical_bytes":
                      encoded_bytes([e.to_dict() for e in events]),
                      "binding_edges": sum(len(refs) for refs in bindings.values()),
                      "binding_preprocessing_events": obs["shared_binding_preprocessing_events"]}
            for budget in budgets:
                original = correlate_selection(events, budget, horizon, bindings)
                propagated = state.witness(events[-1], archive, budget, horizon)
                selections = {
                    "correlated": (original.events, {"payload_records_examined": original.records_examined,
                                   "query_history_index_entries": len(events), "additional_state": None}),
                    "streaming_provenance": (propagated.events, {
                        "payload_records_examined": propagated.payload_records_examined,
                        "parent_edges_examined": propagated.parent_edges_examined,
                        "cached_state_reads": propagated.cached_state_reads, "query_history_index_entries": 0,
                        "online_event_updates": len(events),
                        "online_input_updates": state.input_references_ingested,
                        "additional_state": state.retained_state()}),
                }
                for method, (view, work) in selections.items():
                    selected_bindings = {e.event_id: bindings[e.event_id] for e in view}
                    row = {"observation_id": obs["id"], "group": obs["group"], "dataset": obs["dataset"],
                           "stream_id": obs["raw"]["stream_id"], "publication_id": obs["target"],
                           "budget": budget, "horizon": horizon, "method": method,
                           "evidence": check(view, obs["policy"], selected_bindings),
                           "checker_context_canonical_bytes": encoded_bytes({"events": [e.to_dict() for e in view],
                                   "bindings": selected_bindings, "policy": obs["policy"]}),
                           "shared_storage_and_preprocessing": shared, "work": work,
                           "cached_streaming_verdict": decision["status"] if method == "streaming_provenance" else None}
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
    # Raw evidence rows are sealed before reference/oracle/evaluator joins.
    references, minima, labels = {}, {}, {}
    for obs in examples:
        events, bindings = validate_observation(obs["raw"], obs["policy"])
        references[obs["id"]] = check(events, obs["policy"], bindings)["status"]
        minima[obs["id"]] = minimum_support(events, obs["policy"], bindings, references[obs["id"]], horizon)
    for dataset in datasets:
        truth = reporting.load_ground_truth(dataset["labels"])
        for sid, events in parse_streams(load_streams(dataset["streams"])).items():
            pubs = [e for e in events if e.operation == "publish"]
            for pub in pubs:
                key = f"complete/{dataset['name']}/{sid}/{pub.event_id}"
                labels[key] = reporting.expectation(truth, sid, pub.event_id, len(pubs) == 1)
                if labels[key] is None:
                    raise ValueError(f"Missing label: {key}")
    counts = {}
    violations, opportunities, rows = [], [], []
    with (output / "outputs.jsonl").open() as raw, (output / "evaluated.jsonl").open("x") as joined:
        for line in raw:
            row = json.loads(line)
            key, status = row["observation_id"], row["evidence"]["status"]
            row.update(visible_full_reference=references[key], minimum_support_events=minima[key],
                       evaluator_label=labels.get(key))
            row["sufficient_support"] = status == references[key] and status != "insufficient_evidence"
            wrong = status not in (references[key], "insufficient_evidence")
            if (wrong or cached[key] != references[key]
                    or (key in labels and labels[key] != references[key])):
                violations.append(row)
            if minima[key] is not None and minima[key] <= row["budget"] and not row["sufficient_support"]:
                opportunities.append(row)
            group = counts.setdefault(f"{row['group']}/{row['dataset']}", {}).setdefault(
                str(row["budget"]), {}).setdefault(row["method"], defaultdict(int))
            group["observations"] += 1
            group["sufficient_support"] += row["sufficient_support"]
            group["insufficient_evidence"] += status == "insufficient_evidence"
            group["wrong_definite"] += wrong
            group["payload_records_examined"] += row["work"]["payload_records_examined"]
            group["checker_context_canonical_bytes"] += row["checker_context_canonical_bytes"]
            joined.write(json.dumps(row, sort_keys=True) + "\n")
            rows.append(row)
    write(output / "summary.json", {"counts": counts, "violations": violations,
                                   "available_support_missed": opportunities,
                                   "unique_observations": len(examples), "method_rows": len(rows),
                                   "cached_streaming_matches_visible_full":
                                   all(cached[k] == reference for k, reference in references.items()),
                                   "note": "Masked/control and complete sets overlap; not independent samples. "
                                   "Oracle is post-hoc only. No timings, human review or token measurements."})
    write(output / "experiment-manifest.json", {"source": reporting.source_fingerprint(),
          "packages": reporting.package_versions(), "artifacts": reporting.artifact_hashes(
              output, ("experiment-manifest.json",)), "model_requests": 0, "accounted_usd": 0})
    print(f"{len(examples)} observations, {len(rows)} evidence rows, {len(violations)} correctness violations")
    return 1 if violations else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.config.resolve(), args.output.resolve()))
