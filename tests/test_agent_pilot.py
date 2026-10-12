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
from fragmentguard.agentpilot.episode import ScenarioError, run_episode, validate_scenario
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
        budget = Budget(live_limits(max_spend_usd=0.002))
        reserved = budget.reserve(1000)
        self.assertAlmostEqual(reserved, (1000 + 500 + 100) / 1e6)
        entry = budget.settle(reserved, None)
        self.assertEqual(entry["accounted_usd"], reserved)
        with self.assertRaises(LimitReached):
            budget.reserve(1000)  # 0.0016 spent + 0.0016 reserved would exceed 0.002
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
