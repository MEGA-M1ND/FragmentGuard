"""Run one three-agent episode and save its execution evidence.

Collector, processor, and publisher run in sequence, each in a fresh context.
Each receives only a fixed system prompt, its own task instruction, and the
artifact handles the application's ledger says the previous agent created. No
agent's free-form text is forwarded, so a data dependency can only enter
through a tool input the recorder observed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .backends import OUTPUT_LIMIT_STOP_REASONS, REFUSAL_STOP_REASONS, AgentLimits, LimitReached, tool_specs
from .normalize import check_bindings, normalize_records, stream_id_for
from .workspace import ROLE_TOOLS, TOOL_SCHEMAS, EpisodeAborted, Recorder, Workspace, sha256_json, utc_now

ROLES = ("collector", "processor", "publisher")
BACKGROUND_SLOTS = ("start", "collector", "processor")
SCENARIO_KEYS = {"scenario_id", "permitted_sources", "agents", "background", "description"}
SYSTEM_PROMPT = (
    "You are one step in a small data-handling workflow running in a sandbox with fictitious "
    "records. Use only the tools provided. Complete your task exactly as instructed, using the "
    "handles or names you are given, then reply with one short sentence saying what you did."
)


class ScenarioError(ValueError):
    pass


def validate_scenario(scenario: Any) -> dict[str, Any]:
    """Scenarios carry task instructions only: no labels, pairs, or intended outcomes."""
    if not isinstance(scenario, dict) or not {"scenario_id", "permitted_sources", "agents"} <= set(scenario):
        raise ScenarioError("Scenario needs scenario_id, permitted_sources, and agents")
    unknown = set(scenario) - SCENARIO_KEYS
    if unknown:
        raise ScenarioError(f"Scenario has unexpected keys {sorted(unknown)} (labels stay evaluator-only)")
    stream_id_for(scenario["scenario_id"])
    if set(scenario["agents"]) != set(ROLES) or any(
            set(spec) != {"instruction"} or not isinstance(spec["instruction"], str)
            for spec in scenario["agents"].values()):
        raise ScenarioError("agents must give exactly one instruction for each of collector, processor, publisher")
    for item in scenario.get("background", []):
        if set(item) != {"after", "tool", "arguments"} or item["after"] not in BACKGROUND_SLOTS:
            raise ScenarioError("background items need after (start/collector/processor), tool, arguments")
    return scenario


def episode_fingerprints() -> dict[str, str]:
    return {"system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
            "tool_schemas_sha256": sha256_json(TOOL_SCHEMAS),
            "role_tools_sha256": sha256_json(ROLE_TOOLS)}


async def _run_agent(role: str, backend: Any, workspace: Workspace, task: str, handoff: list[str],
                     limits: AgentLimits) -> dict[str, Any]:
    actor_kind = "model" if backend.kind == "live" else "scripted_backend"
    tools = tool_specs(ROLE_TOOLS[role])
    user = task if not handoff else f"{task}\n\nArtifact handles handed to you: {', '.join(handoff)}"
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    transcript: dict[str, Any] = {
        "role": role, "actor_kind": actor_kind,
        "received": {"system": SYSTEM_PROMPT, "task": task, "handoff_handles": list(handoff),
                     "tools": list(ROLE_TOOLS[role])},
        "requests": [], "tool_calls_executed": 0,
    }
    outcome = None
    try:
        while outcome is None:
            if len(transcript["requests"]) >= limits.max_requests_per_agent:
                outcome = "request_limit"
                break
            try:
                turn = await backend.generate(role, messages, tools)
            except LimitReached as stop:
                outcome = f"stopped_before_request: {stop}"
                break
            transcript["requests"].append({"index": len(transcript["requests"]) + 1, "utc": utc_now(),
                                           "stop_reason": turn.stop_reason, "usage": turn.usage, "cost": turn.cost,
                                           "error": turn.error, "model": turn.model})
            if turn.error:
                outcome = "model_error"
                break
            assistant = {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
            if turn.raw_message is not None:
                assistant["raw"] = turn.raw_message
            messages.append(assistant)
            if not turn.tool_calls:
                if turn.stop_reason in REFUSAL_STOP_REASONS:
                    outcome = "refused"
                elif turn.stop_reason in OUTPUT_LIMIT_STOP_REASONS:
                    outcome = "output_limit"  # Truncated, not a deliberate finish.
                else:
                    outcome = "finished"
                break
            for call in turn.tool_calls:
                if transcript["tool_calls_executed"] >= limits.max_tool_calls_per_agent:
                    result = {"error": "tool-call limit reached; call not executed"}
                    outcome = "tool_call_limit"
                elif call.get("parse_error"):
                    transcript["tool_calls_executed"] += 1
                    result = workspace.reject(role, actor_kind, call["name"], call["arguments"],
                                              f"argument parse error: {call['parse_error']}")
                else:
                    transcript["tool_calls_executed"] += 1
                    result = workspace.execute(role, actor_kind, call["name"], call["arguments"])
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                                 "content": json.dumps(result, sort_keys=True)})
    except EpisodeAborted as error:
        # Keep this agent's transcript (and the costs of its requests) before the episode stops.
        transcript["aborted"] = str(error)
        outcome = "aborted"
    transcript["outcome"] = outcome
    transcript["final_text"] = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), "")
    transcript["messages"] = messages
    return transcript


def run_episode(scenario: dict[str, Any], sources: dict[str, Any], backend: Any, output: Path,
                **kwargs: Any) -> dict[str, Any]:
    """Synchronous wrapper; a pilot run instead awaits ``run_episode_async`` in one event loop."""
    return asyncio.run(run_episode_async(scenario, sources, backend, output, **kwargs))


async def run_episode_async(
    scenario: dict[str, Any], sources: dict[str, Any], backend: Any, output: Path, *,
    limits: AgentLimits | None = None, scenario_sha256: str | None = None, recorder_fail_when: Any = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one episode into a new directory and return its execution manifest."""
    limits = limits or AgentLimits()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}; every execution gets a new directory")
    validate_scenario(scenario)
    output.mkdir(parents=True)
    started = utc_now()
    (output / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")
    episode_id = scenario["scenario_id"]
    roots = sorted(set(scenario["permitted_sources"]) | {
        item["arguments"].get("resource_id") for item in scenario.get("background", [])
        if item["tool"] == "read_resource"} - {None})
    missing = [root for root in roots if root not in sources]
    if missing:
        raise ScenarioError(f"No source contents for {missing}")
    recorder = Recorder(output / "raw_operations.jsonl", fail_when=recorder_fail_when)
    workspace = Workspace(output / "workspace", episode_id, {r: sources[r] for r in roots}, roots, recorder)

    transcripts: list[dict[str, Any]] = []
    background_runs: list[dict[str, Any]] = []
    aborted = None

    def run_background(slot: str) -> None:
        for item in scenario.get("background", []):
            if item["after"] == slot:
                result = workspace.execute("background", "scripted_background", item["tool"], item["arguments"])
                background_runs.append({"after": slot, "tool": item["tool"], "result": result})

    handoff: list[str] = []
    try:
        run_background("start")
        for role in ROLES:
            transcript = await _run_agent(role, backend, workspace, scenario["agents"][role]["instruction"],
                                          handoff, limits)
            transcripts.append(transcript)
            if transcript.get("aborted"):
                raise EpisodeAborted(transcript["aborted"])
            handoff = workspace.created_by(role)  # From the ledger, never from the agent's text.
            if role != "publisher":
                run_background(role)
    except EpisodeAborted as error:
        aborted = str(error)

    (output / "agent_transcripts.json").write_text(
        json.dumps({"agents": transcripts, "background": background_runs}, indent=2) + "\n", encoding="utf-8")
    ledger = workspace.ledger()
    (output / "resource_ledger.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    artifacts = output / "output_artifacts"
    artifacts.mkdir()
    for audience_dir in workspace.destinations.values():
        for path in sorted(audience_dir.glob("*.json")):
            target = artifacts / audience_dir.name
            target.mkdir(exist_ok=True)
            shutil.copy2(path, target / path.name)

    records = [json.loads(line) for line in (output / "raw_operations.jsonl").read_text().splitlines()]
    reasons = list(workspace.incomplete_reasons)
    if len(workspace.publications) != 1:
        reasons.append(f"{len(workspace.publications)} successful publications (exactly one required)")
    complete = not reasons
    normalization: dict[str, Any] = {"performed": False}
    if complete:
        stream, mapping = normalize_records(records, stream_id_for(episode_id))
        agreement = check_bindings(stream, mapping, ledger, records)
        (output / "normalized_stream.json").write_text(json.dumps([stream], indent=2) + "\n", encoding="utf-8")
        (output / "normalization_map.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
        normalization = {"performed": True, "stream_id": stream["stream_id"], "events": len(stream["events"]),
                         "binding_agreement": agreement}
        if not agreement["agree"]:
            complete = False
            reasons.append("normalized bindings disagree with the canonical ledger")
    else:
        normalization["reason"] = "episode incomplete; no normalized stream is produced for evaluation"

    requests = [r for t in transcripts for r in t["requests"]]
    usage_totals = {key: sum((r["usage"] or {}).get(key) or 0 for r in requests)
                    for key in ("input_tokens", "output_tokens", "total_tokens")}
    manifest = {
        "episode_id": episode_id,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "trace_backend": backend.kind,
        "model": backend.model,
        "actor_kinds": sorted({r.get("actor_kind") for r in records if r.get("actor_kind")}),
        "status": "complete" if complete else "incomplete",
        "incomplete_reasons": reasons,
        "aborted": aborted,
        "agent_outcomes": {t["role"]: t["outcome"] for t in transcripts},
        "operations": {"attempted": sum(1 for r in records if "tool" in r),
                       "succeeded": sum(1 for r in records if r.get("status") == "ok"),
                       "failed": sum(1 for r in records if r.get("status") == "error")},
        "publications": workspace.publications,
        "normalization": normalization,
        "generation": {
            "backend_turns": len(requests),
            "model_requests": len(requests) if backend.kind == "live" else 0,
            "usage_totals": usage_totals if backend.kind == "live" else None,
            "accounted_usd": sum((r["cost"] or {}).get("accounted_usd", 0) for r in requests)
            if backend.kind == "live" else 0.0,
            "basis": "live model requests" if backend.kind == "live"
            else "scripted backend: no model requests, no generation cost",
        },
        "scenario_sha256": scenario_sha256 or sha256_json(scenario),
        "fingerprints": episode_fingerprints(),
        "agent_limits": {"max_requests_per_agent": limits.max_requests_per_agent,
                         "max_tool_calls_per_agent": limits.max_tool_calls_per_agent},
        "provenance": provenance,
        "notes": "tick in normalized_stream.json is a logical counter of successful operations, not wall time.",
    }
    (output / "execution_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_artifacts(output: Path) -> dict[str, Any]:
    """Re-check an episode directory: recorded operations vs ledger versions and actual files.

    Every successful write must match its ledger version (hash, producer seq, inputs); every
    publication's destination file and its ``output_artifacts`` copy must match the recorded
    artifact hash; no destination file may exist without a recorded publication.
    """
    records = [json.loads(line) for line in (output / "raw_operations.jsonl").read_text().splitlines()]
    ledger = json.loads((output / "resource_ledger.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = 0
    published = set()
    for record in records:
        if record.get("status") != "ok":
            continue
        checked += 1
        if record["operation"] == "publish":
            published.add(record["artifact_path"])
            relative = record["artifact_path"]
            for path in (output / "workspace" / relative, output / "output_artifacts" / relative):
                if not path.is_file():
                    problems.append(f"seq {record['seq']}: missing {path.relative_to(output)}")
                elif hashlib.sha256(path.read_bytes()).hexdigest() != record["artifact_sha256"]:
                    problems.append(f"seq {record['seq']}: {path.relative_to(output)} does not match the recorded hash")
            continue
        entry = ledger["versions"].get(record["output_version"])
        if entry is None:
            problems.append(f"seq {record['seq']}: {record['output_version']} missing from the ledger")
        elif (entry["sha256"], entry["produced_by_seq"], entry["inputs"]) != (
                record["output_sha256"], record["seq"], [i["version_id"] for i in record["inputs"]]):
            problems.append(f"seq {record['seq']}: ledger entry for {record['output_version']} "
                            "disagrees with the record")
    for audience_dir in sorted((output / "workspace").glob("*_outputs")):
        for path in sorted(audience_dir.glob("*")):
            if path.relative_to(output / "workspace").as_posix() not in published:
                problems.append(f"unrecorded destination file {path.relative_to(output)}")
    return {"ok": not problems, "successful_operations_checked": checked, "problems": problems}
