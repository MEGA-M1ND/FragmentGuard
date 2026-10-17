"""Offline snapshots of the actual messages delivered to the publisher backend.

Run with ``python -m fragmentguard.experiments.handoff --config ... --output ...``.
Only the scripted backend is supported; snapshots establish input availability,
not live instruction following. No evaluator files are opened.
"""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path

from .. import reporting
from ..agentpilot.backends import AgentLimits, ScriptedBackend
from ..agentpilot.episode import HANDOFF_MARKER, episode_fingerprints, run_episode, verify_artifacts
from ..agentpilot.pilot import load_config
from .common import digest, read, write


class CaptureBackend(ScriptedBackend):
    def __init__(self, plan):
        super().__init__(plan)
        self.publisher_input = None

    async def generate(self, role, messages, tools):
        if role == "publisher" and self.publisher_input is None:
            self.publisher_input = {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)}
        return await super().generate(role, messages, tools)


def check(config_path: Path, output: Path) -> int:
    config = load_config(config_path)
    sources = read(config["sources"])["sources"]
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    with tempfile.TemporaryDirectory(prefix="fragmentguard-handoff-") as tmp:
        for sid in config["raw"]["run_order"]:
            scenario = read(config["scenarios"][sid])
            plan = read(config["plans"][sid])
            backend = CaptureBackend(plan)
            execution = Path(tmp) / sid
            manifest = run_episode(scenario, sources, backend, execution,
                                   limits=AgentLimits(**config["raw"]["agent_limits_scripted"]))
            ledger = read(execution / "resource_ledger.json")
            publisher = next(t for t in read(execution / "agent_transcripts.json")["agents"]
                             if t["role"] == "publisher")
            actual = backend.publisher_input
            user = actual["messages"][1]["content"]
            metadata = json.loads(user.split(HANDOFF_MARKER, 1)[1])
            target = next(step["arguments"]["handle"] for step in plan["publisher"]
                          if step.get("tool") == "publish_resource")
            handed = [entry for entry in ledger["versions"].values() if entry["produced_by_agent"] == "processor"]
            handed.sort(key=lambda entry: entry["produced_by_seq"])
            expected = {entry["display_name"]: entry["version_id"] for entry in handed
                        if entry["display_name"] is not None}
            expected_artifacts = [{"handle": entry["version_id"], "name": entry["display_name"]} for entry in handed]
            checks = {
                "execution_complete": manifest["status"] == "complete",
                "captured_message_is_recorded_received_message": user == publisher["received"]["user_message"],
                "received_metadata_matches_actual_message": metadata == publisher["received"]["handoff_metadata"],
                "all_processor_versions_retained": metadata["artifacts"] == expected_artifacts,
                "name_mapping_matches_ledger": metadata["latest_by_name"] == expected,
                "intended_target_explicit": target in metadata["latest_by_name"],
                "published_target_matches_mapping": len(ledger["publications"]) == 1 and
                ledger["publications"][0]["version_id"] == metadata["latest_by_name"].get(target),
                "actual_files_and_ledger_verified": verify_artifacts(execution)["ok"],
                "normalization_binding_agreement": manifest["normalization"].get("binding_agreement", {}).get("agree"),
                "no_model_calls": manifest["generation"]["model_requests"] == 0,
            }
            rows.append({"scenario_id": sid, "intended_target_name_from_scripted_plan": target,
                         "actual_publisher_backend_input": actual, "ledger_derived_handoff": metadata,
                         "checks": checks, "all_checks_passed": all(checks.values()),
                         "scenario_sha256": digest(config["scenarios"][sid]),
                         "plan_sha256": digest(config["plans"][sid])})
    write(output / "publisher-inputs.json", rows)
    write(output / "check-summary.json", {
        "source": reporting.source_fingerprint(), "handoff_fingerprints": episode_fingerprints(),
        "config_sha256": digest(config_path), "source_contents_sha256": digest(config["sources"]),
        "checked": len(rows), "passed": sum(row["all_checks_passed"] for row in rows),
        "model_requests": 0, "accounted_usd": 0,
        "publisher_inputs_sha256": digest(output / "publisher-inputs.json"),
        "note": "Snapshots capture actual backend inputs and compare them with the committed execution ledger. "
        "Scripted generation only; no live compliance claim. Catalog/evaluator files were not opened.",
    })
    passed = sum(row["all_checks_passed"] for row in rows)
    print(f"{passed}/{len(rows)} actual publisher inputs verified; no model calls")
    return 0 if all(row["all_checks_passed"] for row in rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(check(args.config.resolve(), args.output.resolve()))
