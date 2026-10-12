"""Agent-executed pilot: environment, recorder, normalization, limits, and analysis.

No test makes a paid call. Scripted plans and an injected Inspect mock model
exercise the real tool executor and recorder; their outputs are never live evidence.
"""

import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from inspect_ai.model import ModelOutput, ModelUsage, get_model

from fragmentguard import cli
from fragmentguard.agentpilot import pilot
from fragmentguard.agentpilot.backends import (
    Budget, LimitReached, LiveBackend, LiveLimits, LiveNotAuthorized, ScriptedBackend,
)
from fragmentguard.agentpilot.episode import ScenarioError, run_episode, validate_scenario, verify_artifacts
from fragmentguard.agentpilot.ledger_labels import label_publication
from fragmentguard.agentpilot.normalize import check_bindings
from fragmentguard.agentpilot.workspace import EpisodeAborted, Recorder, Workspace

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT = ROOT / "experiments" / "agent_pilot"
SOURCES = json.loads((EXPERIMENT / "sources.json").read_text())["sources"]
CATALOG = json.loads((EXPERIMENT / "catalog.json").read_text())


def load(kind, sid):
    return json.loads((EXPERIMENT / kind / f"{sid}.json").read_text())


def live_limits(**overrides):
    values = {
        "live_enabled": True, "model": "anthropic/test-model", "max_spend_usd": 1.0,
        "input_usd_per_million_tokens": 1.0, "output_usd_per_million_tokens": 1.0,
        "pricing_source": "test", "pricing_retrieved_utc": "2026-10-12T00:00:00Z", "max_output_tokens": 100,
        "max_requests_per_agent": 4, "max_tool_calls_per_agent": 4, "max_total_requests": 50,
        "max_context_bytes": 20000, "request_overhead_tokens": 500,
    }
    values.update(overrides)
    return LiveLimits(**values)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.tmp = Path(self._dir.name)

    def episode(self, sid, plan=None, **kwargs):
        backend = ScriptedBackend(plan if plan is not None else load("scripted_plans", sid))
        return run_episode(load("scenarios", sid), SOURCES, backend, self.tmp / sid, **kwargs)


class RecorderAndWorkspaceTests(TempDirTest):
    def workspace(self, permitted=("src-3184", "src-5520")):
        recorder = Recorder(self.tmp / "ops.jsonl")
        return Workspace(self.tmp / "ws", "sc99", {r: SOURCES[r] for r in permitted}, list(permitted), recorder)

    def test_tool_effects_match_recorded_operations_and_hashes(self):
        manifest = self.episode("sc03")
        self.assertEqual(manifest["status"], "complete")
        out = self.tmp / "sc03"
        ledger = json.loads((out / "resource_ledger.json").read_text())
        records = [json.loads(line) for line in (out / "raw_operations.jsonl").read_text().splitlines()]
        for record in records:
            self.assertEqual(record["status"], "ok")
            if record["operation"] == "publish":
                artifact = out / "workspace" / record["artifact_path"]
                copy = out / "output_artifacts" / record["artifact_path"]
                for path in (artifact, copy):
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["artifact_sha256"])
            else:
                entry = ledger["versions"][record["output_version"]]
                self.assertEqual(entry["sha256"], record["output_sha256"])
                self.assertEqual(entry["produced_by_seq"], record["seq"])
                self.assertEqual(entry["inputs"], [i["version_id"] for i in record["inputs"]])
        self.assertEqual({r["actor_kind"] for r in records}, {"scripted_backend", "scripted_background"})

    def test_agent_run_inspection_verifies_artifacts_and_reports_usage(self):
        out = self.tmp / "cli-dev01"
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            code = cli.main(["agent-run", "--backend", "scripted", "--output", str(out),
                             "--scenario", str(EXPERIMENT / "scenarios" / "dev01.json")])
        self.assertEqual(code, 0)
        inspection = json.loads((out / "inspection.json").read_text())
        self.assertEqual(inspection["artifact_check"], {"ok": True, "successful_operations_checked": 3,
                                                        "problems": []})
        self.assertEqual(inspection["usage"]["model_requests"], 0)
        self.assertIn("artifact check: ok", printed.getvalue())
        published = next((out / "workspace" / "public_outputs").iterdir())
        published.write_text("tampered")
        (out / "workspace" / "internal_outputs" / "stray.json").write_text("{}")
        problems = verify_artifacts(out)["problems"]
        self.assertTrue(any("does not match the recorded hash" in p for p in problems))
        self.assertTrue(any("unrecorded destination file" in p for p in problems))

    def test_normalized_bindings_agree_with_ledger_and_tampering_is_detected(self):
        self.episode("sc08")
        out = self.tmp / "sc08"
        stream = json.loads((out / "normalized_stream.json").read_text())[0]
        mapping = json.loads((out / "normalization_map.json").read_text())
        ledger = json.loads((out / "resource_ledger.json").read_text())
        records = [json.loads(line) for line in (out / "raw_operations.jsonl").read_text().splitlines()]
        self.assertTrue(check_bindings(stream, mapping, ledger, records)["agree"])
        # The processor read 'draft' by name; it must bind to the second (replacing) version.
        processor = next(e for e in stream["events"] if e["agent_id"] == "processor")
        self.assertEqual(processor["inputs"], ["v002"])
        tampered = json.loads(json.dumps(ledger))
        tampered["versions"]["v002"]["produced_by_seq"] = 1
        self.assertFalse(check_bindings(stream, mapping, tampered, records)["agree"])

    def test_old_handle_keeps_its_version_after_name_replacement(self):
        ws = self.workspace()
        first = ws.execute("collector", "scripted_backend", "read_resource",
                           {"resource_id": "src-3184", "name": "draft"})
        second = ws.execute("collector", "scripted_backend", "read_resource",
                            {"resource_id": "src-5520", "name": "draft"})
        self.assertNotEqual(first["handle"], second["handle"])
        by_handle = ws.execute("processor", "scripted_backend", "transform_resource",
                               {"input_handles": [first["handle"]], "operation": "copy"})
        by_name = ws.execute("processor", "scripted_backend", "transform_resource",
                             {"input_handles": ["draft"], "operation": "copy"})
        self.assertEqual(by_handle["content"], SOURCES["src-3184"])
        self.assertEqual(by_name["content"], SOURCES["src-5520"])
        self.assertEqual(ws.ledger()["display_names"]["draft"], [first["handle"], second["handle"]])
        self.assertEqual(ws.versions[by_name["handle"]].inputs, [second["handle"]])

    def test_rejected_operations_have_no_successful_effects(self):
        ws = self.workspace()
        ws.execute("collector", "scripted_backend", "read_resource", {"resource_id": "src-3184", "name": "ok"})
        before = dict(ws.versions)
        bad_calls = [
            ("collector", "read_resource", {"resource_id": "../../etc/passwd"}),
            ("collector", "read_resource", {"resource_id": "/tmp/x"}),
            ("collector", "read_resource", {"resource_id": "src-9045"}),  # not permitted
            ("collector", "read_resource", {"resource_id": "src-3184", "name": "src-3184"}),  # root-like name
            ("collector", "read_resource", {"resource_id": "src-3184", "path": "/etc"}),  # unknown argument
            ("collector", "transform_resource", {"input_handles": ["ok"], "operation": "copy"}),  # wrong role
            ("processor", "transform_resource", {"input_handles": ["v999"], "operation": "copy"}),
            ("processor", "transform_resource", {"input_handles": ["ok"], "operation": "write_arbitrary"}),
            ("processor", "transform_resource", {"input_handles": ["ok"], "operation": "select_fields",
                                                 "fields": ["secret"]}),
            ("publisher", "publish_resource", {"handle": "src-3184", "audience": "public"}),  # a root
            ("publisher", "publish_resource", {"handle": "ok", "audience": "everyone"}),
        ]
        for agent, tool, args in bad_calls:
            self.assertIn("error", ws.execute(agent, "scripted_backend", tool, args), (tool, args))
        self.assertEqual(ws.versions, before)
        self.assertEqual(ws.publications, [])
        self.assertEqual([p for d in ws.destinations.values() for p in d.iterdir()], [])
        records = [json.loads(line) for line in (self.tmp / "ops.jsonl").read_text().splitlines()]
        self.assertEqual([r["status"] for r in records], ["ok"] + ["error"] * len(bad_calls))
        # A second publication is refused by the environment.
        self.assertIn("published", ws.execute("publisher", "scripted_backend", "publish_resource",
                                              {"handle": "ok", "audience": "internal"}))
        self.assertIn("error", ws.execute("publisher", "scripted_backend", "publish_resource",
                                          {"handle": "ok", "audience": "public"}))
        self.assertEqual(len(ws.publications), 1)

    def test_recording_failure_makes_the_episode_incomplete(self):
        manifest = self.episode("sc07", recorder_fail_when=lambda record: record["seq"] == 2)
        out = self.tmp / "sc07"
        self.assertEqual(manifest["status"], "incomplete")
        self.assertTrue(any("recording failed" in r for r in manifest["incomplete_reasons"]))
        self.assertFalse((out / "normalized_stream.json").exists())
        self.assertEqual(manifest["publications"], [])
        ledger = json.loads((out / "resource_ledger.json").read_text())
        self.assertEqual(sorted(ledger["versions"]), ["src-5520", "v001"])  # seq 2 left no effect
        ws = self.workspace()
        ws.incomplete_reasons.append("simulated")
        with self.assertRaises(EpisodeAborted):
            ws.execute("collector", "scripted_backend", "read_resource", {"resource_id": "src-3184"})

    def test_agent_contexts_and_workspaces_are_isolated(self):
        self.episode("sc03")
        self.episode("sc07")
        transcripts = json.loads((self.tmp / "sc03" / "agent_transcripts.json").read_text())["agents"]
        collector, processor, publisher = transcripts
        self.assertEqual(processor["received"]["handoff_handles"], ["v001"])
        self.assertEqual(publisher["received"]["handoff_handles"], ["v004"])  # background v002/v003 excluded
        processor_text = json.dumps(processor["messages"])
        self.assertNotIn(collector["final_text"], processor_text)
        self.assertEqual([m["role"] for m in processor["messages"]][:2], ["system", "user"])
        self.assertNotEqual((self.tmp / "sc03" / "workspace").resolve(), (self.tmp / "sc07" / "workspace").resolve())
        self.assertEqual(sorted(p.name for p in (self.tmp / "sc07" / "workspace" / "public_outputs").iterdir()),
                         ["pub01.json"])

    def test_refused_or_missing_publication_is_an_execution_outcome_not_a_verdict(self):
        plan = load("scripted_plans", "sc02")
        plan["publisher"] = [{"final": "I won't publish this.", "stop_reason": "content_filter"}]
        manifest = self.episode("sc02", plan=plan)
        self.assertEqual(manifest["status"], "incomplete")
        self.assertEqual(manifest["agent_outcomes"]["publisher"], "refused")
        self.assertIn("0 successful publications", manifest["incomplete_reasons"][0])
        with self.assertRaises(ValueError):
            label_publication(json.loads((self.tmp / "sc02" / "resource_ledger.json").read_text()), CATALOG)
        plan = load("scripted_plans", "sc07")
        plan["processor"] = [{"final": "", "stop_reason": "max_tokens"}]
        truncated = self.episode("sc07", plan=plan)
        self.assertEqual(truncated["agent_outcomes"]["processor"], "output_limit")
        self.assertEqual(truncated["status"], "incomplete")

    def test_scenarios_cannot_carry_labels_and_outputs_are_never_overwritten(self):
        scenario = load("scenarios", "sc01")
        for key in ("expected", "pair", "intended_condition", "label"):
            with self.assertRaises(ScenarioError):
                validate_scenario({**scenario, key: "alert"})
        self.episode("sc01")
        with self.assertRaises(SystemExit):
            self.episode("sc01")


class LiveLimitTests(TempDirTest):
    def test_live_requires_explicit_complete_authorization(self):
        for overrides in ({"live_enabled": False}, {"model": "mockllm/model"}, {"model": "no-provider"},
                          {"max_spend_usd": 0}, {"input_usd_per_million_tokens": 0}, {"max_output_tokens": 0}):
            with self.assertRaises(LiveNotAuthorized, msg=overrides):
                live_limits(**overrides).validate()
        template = EXPERIMENT / "limits.example.json"
        with self.assertRaises(LiveNotAuthorized):
            LiveLimits.load(template)  # The committed template never authorizes anything.
        missing = self.tmp / "limits.json"
        missing.write_text(json.dumps({"live_enabled": True, "model": "anthropic/x"}))
        with self.assertRaises(LiveNotAuthorized):
            LiveLimits.load(missing)
        with self.assertRaises(SystemExit):
            cli.main(["agent-run", "--backend", "live", "--scenario", str(EXPERIMENT / "scenarios" / "dev01.json"),
                      "--output", str(self.tmp / "blocked")])
        self.assertFalse((self.tmp / "blocked").exists())
        with self.assertRaises(LiveNotAuthorized):
            LiveBackend(live_limits(), Budget(live_limits()), model=object())  # injection needs the test flag

    def test_budget_reserves_before_requests_and_charges_unknown_usage_in_full(self):
        budget = Budget(live_limits(max_spend_usd=0.005))
        reserved = budget.reserve(1000)
        self.assertAlmostEqual(reserved, ((1000 + 500) * 2 + 100) / 1e6)  # input priced at the 2x ceiling
        entry = budget.settle(reserved, None)
        self.assertEqual(entry["accounted_usd"], reserved)
        with self.assertRaises(LimitReached):
            budget.reserve(1000)  # 0.0031 spent + 0.0031 reserved would exceed 0.005
        self.assertEqual(budget.requests, 1)
        with self.assertRaises(LimitReached):
            Budget(live_limits()).reserve(30000)  # over max_context_bytes

    def test_live_backend_stops_before_exceeding_limits(self):
        def usage():
            return ModelUsage(input_tokens=300, output_tokens=20, total_tokens=320)
        outputs = [ModelOutput.for_tool_call("mockllm/model", "read_resource",
                                             {"resource_id": "src-5520", "name": "draft"}, tool_call_id="c1"),
                   ModelOutput.from_content("mockllm/model", "Saved.")]
        for output in outputs:
            output.usage = usage()
        model = get_model("mockllm/model", custom_outputs=outputs, memoize=False)
        limits = live_limits(max_total_requests=2)
        budget = Budget(limits)
        backend = LiveBackend(limits, budget, model=model, _allow_test_model=True)
        self.assertEqual(backend._config().max_retries, 0)
        manifest = run_episode(load("scenarios", "dev01"), SOURCES, backend, self.tmp / "live",
                               limits=limits.agent_limits())
        self.assertEqual(budget.requests, 2)
        self.assertEqual(manifest["generation"]["model_requests"], 2)
        self.assertEqual(manifest["agent_outcomes"]["collector"], "finished")
        self.assertTrue(manifest["agent_outcomes"]["processor"].startswith("stopped_before_request"))
        self.assertEqual(manifest["status"], "incomplete")
        self.assertAlmostEqual(manifest["generation"]["accounted_usd"], 2 * 320 / 1e6)
        records = [json.loads(line) for line in (self.tmp / "live" / "raw_operations.jsonl").read_text().splitlines()]
        self.assertEqual([r["actor_kind"] for r in records], ["model"])


    def test_live_freeze_records_estimates_and_refuses_an_insufficient_cap(self):
        limits = self.tmp / "limits.json"
        limits.write_text(json.dumps(live_limits(max_spend_usd=50.0, max_total_requests=1000).to_dict()))
        record = pilot.freeze(EXPERIMENT / "pilot_config.json", self.tmp / "frz", "live", limits, require_clean=False)
        generation = record["generation"]
        self.assertGreater(generation["pessimistic_max_usd_including_development_episodes"],
                           generation["pessimistic_max_usd"])
        self.assertLessEqual(generation["pessimistic_max_usd"], 50.0)
        limits.write_text(json.dumps(live_limits(max_spend_usd=0.01).to_dict()))
        with self.assertRaises(SystemExit):
            pilot.freeze(EXPERIMENT / "pilot_config.json", self.tmp / "frz2", "live", limits, require_clean=False)
        self.assertFalse((self.tmp / "frz2").exists())

    def test_committed_pilot_limits_authorize_nothing_and_fit_their_proposed_cap(self):
        committed = EXPERIMENT / "live" / "pilot.limits.json"
        with self.assertRaises(LiveNotAuthorized):
            LiveLimits.load(committed)  # Proposed only: live_enabled stays false until authorized.
        enabled = self.tmp / "limits.json"
        enabled.write_text(json.dumps({**json.loads(committed.read_text()), "live_enabled": True}))
        record = pilot.freeze(EXPERIMENT / "pilot_config.json", self.tmp / "frz", "live", enabled, require_clean=False)
        limits = record["generation"]["limits"]
        self.assertEqual(limits["max_total_requests"], 12 * 3 * limits["max_requests_per_agent"])
        self.assertAlmostEqual(record["generation"]["pessimistic_max_usd"], 0.963648)
        self.assertLessEqual(record["generation"]["pessimistic_max_usd"], limits["max_spend_usd"])


class CostAccountingTests(TempDirTest):
    """Inspect's ModelUsage: output_tokens is the total (reasoning included); input_tokens
    excludes cache reads/writes. Reservation and settlement must use those same meanings."""

    RATES = {"input_usd_per_million_tokens": 4.0, "output_usd_per_million_tokens": 20.0}

    def test_reasoning_tokens_are_a_breakdown_not_an_extra_charge(self):
        budget = Budget(live_limits(max_output_tokens=4096, **self.RATES))
        reserved = budget.reserve(1000)
        entry = budget.settle(reserved, {"input_tokens": 100, "output_tokens": 1000, "reasoning_tokens": 600})
        self.assertAlmostEqual(entry["accounted_usd"], 0.0204, places=10)  # not 0.0324
        self.assertEqual(entry["tokens"], {"input_total": 100, "cache_read": 0, "cache_write": 0,
                                           "output_total": 1000, "reasoning_included_in_output": 600})
        self.assertAlmostEqual(budget.spent_usd, 0.0204, places=10)

    def test_cache_tokens_add_to_input_and_settlement_stays_within_reservation(self):
        limits = live_limits(max_output_tokens=4096, request_overhead_tokens=500, **self.RATES)
        budget = Budget(limits)
        reserved = budget.reserve(1000)
        self.assertAlmostEqual(reserved, ((1000 + 500) * 4 * 2 + 4096 * 20) / 1e6)
        mixed = {"input_tokens": 1000, "input_tokens_cache_read": 300, "input_tokens_cache_write": 200,
                 "output_tokens": 4096, "reasoning_tokens": 4000}
        entry = budget.settle(reserved, mixed)
        self.assertEqual(entry["tokens"]["input_total"], 1500)
        self.assertAlmostEqual(entry["accounted_usd"], ((1000 + 300) * 4 + 200 * 4 * 2 + 4096 * 20) / 1e6)
        self.assertFalse(entry["exceeded_reservation"])
        # Worst case on the same semantics: every input token billed as a cache write at the
        # ceiling, and a full-length output whose reasoning is part of output_tokens.
        budget2 = Budget(limits)
        reserved2 = budget2.reserve(1000)
        worst = {"input_tokens": 0, "input_tokens_cache_write": 1500, "output_tokens": 4096,
                 "reasoning_tokens": 4096}
        entry2 = budget2.settle(reserved2, worst)
        self.assertAlmostEqual(entry2["accounted_usd"], reserved2)
        self.assertFalse(entry2["exceeded_reservation"])

    def test_live_requests_disable_caching_and_replay_thinking_verbatim(self):
        from inspect_ai.model import ChatMessageAssistant, ContentReasoning, ContentText
        from inspect_ai.tool import ToolCall

        backend = LiveBackend(live_limits(), Budget(live_limits()), model=object(), _allow_test_model=True)
        config = backend._config()
        self.assertIs(config.cache_prompt, False)
        self.assertEqual(config.max_retries, 0)
        original = ChatMessageAssistant(
            content=[ContentReasoning(reasoning="", signature="sig-abc", redacted=False), ContentText(text="ok")],
            tool_calls=[ToolCall(id="c1", function="read_resource", arguments={"resource_id": "src-5520"})])
        replayed = LiveBackend._messages([{"role": "assistant", "content": "ok", "tool_calls": [],
                                           "raw": original.model_dump(mode="json")}])[0]
        self.assertEqual(replayed.model_dump(), original.model_dump())

    def test_usage_beyond_the_reservation_halts_further_requests(self):
        budget = Budget(live_limits(max_output_tokens=100, **self.RATES))
        reserved = budget.reserve(1000)
        entry = budget.settle(reserved, {"input_tokens": 5000, "output_tokens": 100})
        self.assertTrue(entry["exceeded_reservation"])
        with self.assertRaises(LimitReached):
            budget.reserve(10)

    def _live(self, outputs, **limit_overrides):
        model = get_model("mockllm/model", custom_outputs=outputs, memoize=False)
        limits = live_limits(**{**self.RATES, **limit_overrides})
        budget = Budget(limits)
        return LiveBackend(limits, budget, model=model, _allow_test_model=True), budget, limits

    @staticmethod
    def _call(tool, arguments, call_id):
        output = ModelOutput.for_tool_call("mockllm/model", tool, arguments, tool_call_id=call_id)
        output.usage = ModelUsage(input_tokens=200, output_tokens=50, total_tokens=250, reasoning_tokens=30)
        return output

    def test_model_error_after_work_keeps_incurred_costs(self):
        first = self._call("read_resource", {"resource_id": "src-5520", "name": "draft"}, "c1")
        backend, budget, limits = self._live([first])  # the second request raises: outputs run out
        manifest = run_episode(load("scenarios", "dev01"), SOURCES, backend, self.tmp / "err",
                               limits=limits.agent_limits())
        first_cost = (200 * 4 + 50 * 20) / 1e6
        self.assertEqual(manifest["agent_outcomes"]["collector"], "model_error")
        # Later agents still run (the collector's read was done); each failed request is charged.
        self.assertEqual(manifest["generation"]["model_requests"], 4)
        self.assertAlmostEqual(budget.ledger[0]["accounted_usd"], first_cost)
        self.assertEqual(budget.ledger[1]["basis"], "usage unavailable: charged the full reservation")
        self.assertAlmostEqual(manifest["generation"]["accounted_usd"], budget.spent_usd)
        self.assertGreater(manifest["generation"]["accounted_usd"], first_cost)
        self.assertEqual(manifest["status"], "incomplete")

    def test_recording_abort_mid_agent_keeps_that_agents_costs(self):
        first = self._call("read_resource", {"resource_id": "src-5520", "name": "draft"}, "c1")
        backend, budget, limits = self._live([first])
        manifest = run_episode(load("scenarios", "dev01"), SOURCES, backend, self.tmp / "abort",
                               limits=limits.agent_limits(), recorder_fail_when=lambda r: r["seq"] == 1)
        self.assertEqual(manifest["status"], "incomplete")
        self.assertTrue(manifest["aborted"])
        self.assertEqual(manifest["agent_outcomes"], {"collector": "aborted"})
        self.assertEqual(manifest["generation"]["model_requests"], 1)
        self.assertAlmostEqual(manifest["generation"]["accounted_usd"], (200 * 4 + 50 * 20) / 1e6)
        transcripts = json.loads((self.tmp / "abort" / "agent_transcripts.json").read_text())["agents"]
        self.assertIn("recording failed", transcripts[0]["aborted"])

    def test_preflight_only_checks_without_calling_a_model(self):
        limits_path = self.tmp / "limits.json"
        limits_path.write_text(json.dumps(live_limits(max_spend_usd=10.0, **self.RATES).to_dict()))
        scenario = str(EXPERIMENT / "scenarios" / "dev01.json")
        with mock.patch.object(LiveBackend, "generate", side_effect=AssertionError("no model call")), \
                mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "not-a-real-key"}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.main(["agent-run", "--backend", "live", "--model", "anthropic/test-model",
                             "--limits", str(limits_path), "--scenario", scenario, "--preflight-only"])
        report = json.loads(out.getvalue().split("\nPreflight only")[0])
        self.assertTrue(report["credential_variable_set"])
        self.assertNotIn("not-a-real-key", out.getvalue())
        self.assertEqual(report["credential_variable"], "ANTHROPIC_API_KEY")
        self.assertAlmostEqual(report["pessimistic_max_usd"], 3 * 4 * report["max_request_reservation_usd"])
        self.assertEqual(code, 0 if report["provider_package_version"] else 3)
        self.assertEqual(list(self.tmp.iterdir()), [limits_path])  # nothing else written

    def test_pilot_run_reports_costs_of_an_episode_that_raised(self):
        limits_path = self.tmp / "limits.json"
        limits_path.write_text(json.dumps(live_limits(max_spend_usd=60.0, max_total_requests=1000,
                                                      max_output_tokens=4096, **self.RATES).to_dict()))
        pilot.freeze(EXPERIMENT / "pilot_config.json", self.tmp / "frz", "live", limits_path, require_clean=False)

        class ChargingBackend:
            kind, model = "live", "anthropic/test-model"

            def __init__(self, limits, budget):
                self.budget = budget

        async def charge_then_fail(scenario, sources, backend, output, **kwargs):
            reserved = backend.budget.reserve(1000)
            backend.budget.settle(reserved, {"input_tokens": 100, "output_tokens": 1000, "reasoning_tokens": 600})
            raise RuntimeError("provider connection dropped mid-episode")

        with mock.patch.object(pilot, "LiveBackend", ChargingBackend), \
                mock.patch.object(pilot, "run_episode_async", charge_then_fail):
            summary = pilot.run(self.tmp / "frz" / "freeze.json", self.tmp / "run", limits_path,
                                require_fingerprint=False)
        failed = summary["episodes"]
        self.assertEqual({e["status"] for e in failed}, {"execution_failed"})
        for episode in failed:
            self.assertAlmostEqual(episode["generation"]["accounted_usd"], 0.0204)
            self.assertEqual(episode["generation"]["model_requests"], 1)
        totals = summary["generation_totals"]
        self.assertAlmostEqual(totals["accounted_usd"], 12 * 0.0204)
        self.assertAlmostEqual(totals["accounted_usd"], totals["sum_of_episode_accounted_usd"])
        self.assertEqual({entry["episode"] for entry in totals["budget_ledger"]}, set(summary["planned"]))


class PilotPipelineTests(unittest.TestCase):
    """Freeze -> run -> label-free replays in both modes -> post-hoc analysis, on a scripted copy."""

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._dir.name)
        cls.experiment = cls.tmp / "agent_pilot"
        shutil.copytree(EXPERIMENT, cls.experiment)
        plan_path = cls.experiment / "scripted_plans" / "sc05.json"
        plan = json.loads(plan_path.read_text())
        plan["publisher"] = [{"final": "Not publishing.", "stop_reason": "content_filter"}]
        plan_path.write_text(json.dumps(plan))
        config = cls.experiment / "pilot_config.json"
        pilot.freeze(config, cls.tmp / "freeze", "scripted", require_clean=False)
        cls.summary = pilot.run(cls.tmp / "freeze" / "freeze.json", cls.tmp / "exec")
        dataset = cls.tmp / "exec" / "dataset"
        common = ["--streams", str(dataset / "streams.json"), "--policy", str(dataset / "policy.json"),
                  "--provenance", str(dataset / "provenance.json"), "--budget", "3", "--horizon", "100",
                  "--gate", "none"]
        blocked = mock.patch.object(LiveBackend, "generate", side_effect=AssertionError("generation during replay"))
        scripted = mock.patch.object(ScriptedBackend, "generate", side_effect=AssertionError("generation"))
        with blocked, scripted, contextlib.redirect_stdout(io.StringIO()):
            cls.codes = [cli.main(["demo", "--mode", mode, "--output", str(cls.tmp / mode), *common])
                         for mode in ("direct", "scout")]
        labels = cls.tmp / "exec" / "evaluator" / "labels.json"
        cls.report = pilot.analyze(cls.tmp / "direct", cls.tmp / "scout", labels, cls.tmp / "exec",
                                   cls.tmp / "analysis")

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def test_replays_complete_without_generation_and_agree(self):
        self.assertEqual(self.codes, [cli.EXIT_OK, cli.EXIT_OK])
        self.assertTrue(self.report["direct_scheduled_agreement"]["agree"])
        attempt = json.loads((self.tmp / "scout" / "scheduled-attempt.json").read_text())
        self.assertTrue(attempt["checks"]["zero_model_tokens"])
        manifest = json.loads((self.tmp / "scout" / "manifest.json").read_text())
        self.assertEqual(manifest["source_kind"], "agent_executed_trace")
        self.assertEqual(manifest["trace_generation"]["trace_backend"], "scripted")
        direct = json.loads((self.tmp / "direct" / "report.json").read_text())
        self.assertIsNone(direct["evaluation"])  # labels never entered the replay
        self.assertIn("SCRIPTED", direct["purpose"])

    def test_incomplete_twin_is_reported_not_removed(self):
        counts = self.report["counts"]
        self.assertEqual((counts["planned_episodes"], counts["completed_episodes"]), (12, 11))
        self.assertEqual((counts["planned_pairs"], counts["evaluable_pairs"]), (6, 5))
        sc05 = next(e for e in self.report["episodes"] if e["episode_id"] == "sc05")
        self.assertEqual(sc05["execution_status"], "incomplete")
        self.assertNotIn("ledger_label", sc05)
        pair_b = next(p for p in self.report["pairs"] if p["pair"] == "pair-b")
        self.assertFalse(pair_b["evaluable"])
        for counts in self.report["pair_separation"].values():
            self.assertEqual((counts["evaluable_pairs"], counts["planned_pairs"]), (5, 6))
        labels = json.loads((self.tmp / "exec" / "evaluator" / "labels.json").read_text())
        self.assertNotIn("stream05", labels["expected"])

    def test_labels_agree_with_full_context_and_baseline_wins_are_kept(self):
        self.assertEqual(self.report["label_agreement"]["halted"], [])
        self.assertIn(["sc04", "fixed_window"], [list(x) for x in self.report["baseline_more_informative"]])
        self.assertGreater(self.report["status_counts_completed"]["correlated"]["insufficient_evidence"], 0)
        markdown = (self.tmp / "analysis" / "pilot_report.md").read_text()
        self.assertIn("SCRIPTED rehearsal", markdown)
        self.assertIn("sc04: fixed_window", markdown)

    def test_no_label_or_pair_data_reaches_agents_or_scanners(self):
        pairs = json.loads((self.experiment / "evaluator" / "pairs.json").read_text())
        markers = [p["pair"] for p in pairs["pairs"]] + ["intended", "restricted", "allowed"]
        for episode in (self.tmp / "exec" / "episodes").iterdir():
            text = (episode / "agent_transcripts.json").read_text()
            for marker in markers:
                self.assertNotIn(marker, text, episode.name)
        dataset = self.tmp / "exec" / "dataset"
        self.assertEqual(sorted(p.name for p in dataset.iterdir()), ["policy.json", "provenance.json", "streams.json"])
        for stream in json.loads((dataset / "streams.json").read_text()):
            self.assertEqual(set(stream), {"stream_id", "events"})

    def test_frozen_inputs_and_code_are_enforced(self):
        record = json.loads((self.tmp / "freeze" / "freeze.json").read_text())
        record["code"]["package_sha256"] = "0" * 64
        tampered = self.tmp / "tampered.json"
        tampered.write_text(json.dumps(record))
        with self.assertRaises(SystemExit):
            pilot.run(tampered, self.tmp / "never")
        scenario = self.experiment / "scenarios" / "sc01.json"
        original = scenario.read_text()
        try:
            scenario.write_text(original.replace("format_summary", "copy"))
            with self.assertRaises(SystemExit):
                pilot.run(self.tmp / "freeze" / "freeze.json", self.tmp / "never2")
        finally:
            scenario.write_text(original)
        self.assertFalse((self.tmp / "never").exists() or (self.tmp / "never2").exists())
        with mock.patch("fragmentguard.reporting.source_fingerprint", return_value={"git_dirty": True}):
            with self.assertRaises(SystemExit):
                pilot.freeze(self.experiment / "pilot_config.json", self.tmp / "dirty", "scripted")


if __name__ == "__main__":
    unittest.main()
