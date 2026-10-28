"""Extract final publication facts from preserved results; never calls a model."""

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(), parse_float=Decimal)


def facts():
    rows = [
        json.loads(line)
        for line in (ROOT / "examples/evidence_retrieval/first-comparison/evaluated.jsonl").read_text().splitlines()
    ]
    curve = {}
    for budget in (1, 2, 3, 4, 8):
        curve[str(budget)] = {}
        for group in ("complete", "masked_control", "masked"):
            curve[str(budget)][group] = {}
            for method in ("correlated", "streaming_provenance"):
                selected = [r for r in rows if r["budget"] == budget and r["group"] == group and r["method"] == method]
                for row in selected:
                    assert row["sufficient_support"] == (
                        row["evidence"]["status"] == row["visible_full_reference"]
                        and row["evidence"]["status"] != "insufficient_evidence"
                    )
                curve[str(budget)][group][method] = {
                    "observations": len(selected),
                    "sufficient_support": sum(r["sufficient_support"] for r in selected),
                    "wrong_definite": sum(
                        r["evidence"]["status"] not in (r["visible_full_reference"], "insufficient_evidence")
                        for r in selected
                    ),
                }
    complete = [
        r for r in rows if r["budget"] == 3 and r["group"] == "complete" and r["method"] == "streaming_provenance"
    ]
    assert len(complete) == 37
    assert all(r["cached_streaming_verdict"] == r["visible_full_reference"] == r["evaluator_label"] for r in complete)
    pilots = []
    for name, path in [
        ("pilot_1", "examples/agent_pilot/live-pilot-run"),
        ("pilot_2", "examples/agent_pilot_02/live-20261016/run"),
    ]:
        summary = read(path + "/run_summary.json")
        pilots.append(
            {
                "id": name,
                "attempted": len(summary["planned"]),
                "completed": len(summary["complete"]),
                "incomplete": [r["episode_id"] for r in summary["episodes"] if r["status"] != "complete"],
                "model_requests": summary["generation_totals"]["model_requests"],
                "accounted_usd": str(summary["generation_totals"]["accounted_usd"]),
            }
        )
    dev_cost = sum(
        read(f"examples/agent_pilot/live-dev0{i}/execution_manifest.json")["generation"]["accounted_usd"]
        for i in (1, 2)
    )
    return {
        "report_date": "2026-10-28",
        "experimental_evidence_base_commit": "aed2a1c969267e1f70dfeac8255daa9f4443ed13",
        "complete_publications": len(complete),
        "complete_cached_verdict_matches": len(complete),
        "complete_publications_by_source": dict(Counter(r["dataset"] for r in complete)),
        "raw_evidence_support_by_budget": curve,
        "pilots": pilots,
        "two_pilot_accounted_usd": str(sum(Decimal(p["accounted_usd"]) for p in pilots)),
        "development_episode_accounted_usd": str(dev_cost),
        "total_accounted_usd_including_development": str(dev_cost + sum(Decimal(p["accounted_usd"]) for p in pilots)),
        "completed_experiment_status": "Final; four-case live successor not run and excluded from results",
        "new_model_calls_for_publication": 0,
        "source_files": [
            "examples/evidence_retrieval/first-comparison/evaluated.jsonl",
            "examples/evidence_retrieval/first-comparison/summary.json",
            "examples/missing_evidence/first_analysis/results/summary.json",
            "examples/agent_pilot/live-pilot-analysis/pilot_report.json",
            "examples/agent_pilot_02/live-20261016/analysis/pilot_report.json",
        ],
        "interpretation": "Descriptive counts on self-authored cases, not independent trials or attack accuracy.",
    }


if __name__ == "__main__":
    output = ROOT / "publication/results.json"
    output.write_text(json.dumps(facts(), indent=2, sort_keys=True) + "\n")
    print(output)
