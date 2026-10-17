"""Evidence support is distinct from a cached decision; exact versions matter."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fragmentguard.correlation import correlate_selection
from fragmentguard.experiments.common import digest, write
from fragmentguard.experiments.retrieval import minimum_support, run
from fragmentguard.monitor import check
from fragmentguard.observation import freeze_complete, hide, validate_observation
from fragmentguard.provenance import StreamingProvenance
from fragmentguard.schema import input_bindings, parse_streams
from test_bindings import POLICY, ev, overwrite_stream

ROOT = Path(__file__).resolve().parents[1]


def prepared(events, policy=POLICY, bindings=None):
    bindings = input_bindings(events) if bindings is None else bindings
    state = StreamingProvenance(policy)
    verdict = None
    for event in events:
        verdict = state.update(event, bindings[event.event_id])
    return state, verdict, {e.event_id: e for e in events}, bindings


class RetrievalTests(unittest.TestCase):
    def test_restricted_parent_state_recovers_short_proof_behind_long_public_branch(self):
        base = ROOT / "examples/agent_pilot/scripted-rehearsal-run"
        stream = json.loads((base / "episodes/sc04/normalized_stream.json").read_text())
        events = next(iter(parse_streams(stream).values()))
        policy = json.loads((base / "dataset/policy.json").read_text())
        state, cached, archive, bindings = prepared(events, policy)
        old = correlate_selection(events, 3, 100, bindings)
        with patch("fragmentguard.monitor.check", side_effect=AssertionError("No checker during retrieval")):
            witness = state.witness(events[-1], archive, 3, 100)
        self.assertEqual(cached["status"], "alert")
        self.assertEqual(check(old.events, policy, bindings)["status"], "insufficient_evidence")
        self.assertEqual(check(witness.events, policy, bindings)["status"], "alert")
        self.assertEqual([e.event_id for e in witness.events], ["e004", "e005", "e006"])
        self.assertEqual(minimum_support(events, policy, bindings, "alert", 100), 3)

    def test_cached_alert_does_not_supply_a_proof_that_exceeds_the_budget_or_horizon(self):
        events = [ev("e1", 1, "a", "read", ["restricted-record"], ["x"]),
                  ev("e2", 2, "b", "transform", ["x"], ["y"]),
                  ev("e3", 3, "b", "transform", ["y"], ["z"]),
                  ev("e4", 104, "c", "publish", ["z"], audience="public")]
        state, cached, archive, bindings = prepared(events)
        self.assertEqual(cached["status"], "alert")
        witness = state.witness(events[-1], archive, 3, 200)
        self.assertEqual(check(witness.events, POLICY, bindings)["status"], "insufficient_evidence")
        self.assertEqual(minimum_support(events, POLICY, bindings, "alert", 200), 4)
        limited = state.witness(events[-1], archive, 4, 100)
        self.assertEqual(check(limited.events, POLICY, bindings)["status"], "insufficient_evidence")
        self.assertIsNone(minimum_support(events, POLICY, bindings, "alert", 100))

    def test_missing_producer_never_falls_back_to_older_same_name(self):
        events = overwrite_stream("restricted-record")
        raw = freeze_complete({"stream_id": "stream01", "events": [e.to_dict() for e in events]}, POLICY)
        visible, bindings = validate_observation(hide(raw, {"e03"}), POLICY)
        state, cached, archive, _ = prepared(visible, bindings=bindings)
        self.assertEqual(cached["status"], "insufficient_evidence")
        for budget in (1, 3, 8):
            witness = state.witness(visible[-1], archive, budget, 100)
            result = check(witness.events, POLICY, bindings)
            self.assertEqual(result["status"], "insufficient_evidence")
            self.assertIn({"resource": "scratch", "bound_producer": "e03"}, result["unresolved_inputs"])

    def test_known_restriction_survives_missing_sibling_and_old_versions_remain_addressable(self):
        events = [ev("e1", 1, "a", "read", ["restricted-record"], ["x"]),
                  ev("e2", 2, "a", "read", ["public-guide"], ["x"]),
                  ev("e3", 3, "c", "publish", ["x", "unknown"], audience="public")]
        bindings = input_bindings(events)
        bindings["e3"]["x"] = "e1"
        state, cached, archive, _ = prepared(events, bindings=bindings)
        witness = state.witness(events[-1], archive, 2, 100)
        self.assertEqual(cached["status"], "alert")
        self.assertEqual(check(witness.events, POLICY, bindings)["status"], "alert")
        self.assertEqual([e.event_id for e in witness.events], ["e1", "e3"])
        self.assertEqual(state.retained_state()["version_state_slots"], 2)

    def test_runner_writes_method_outputs_before_opening_evaluator_and_reports_support_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = overwrite_stream("restricted-record")
            write(root / "streams.json", [{"stream_id": "stream01", "events": [e.to_dict() for e in events]}])
            write(root / "policy.json", POLICY)
            (root / "masked").mkdir()
            observation = {"observation_id": "obs0", "dataset": "test", "publication_id": "e04",
                           "hidden_ids": [], "observation": freeze_complete(
                               {"stream_id": "stream01", "events": [e.to_dict() for e in events]}, POLICY)}
            (root / "masked/observations.jsonl").write_text(json.dumps(observation) + "\n")
            write(root / "masked/plan.json", {"datasets": [{"name": "test", "policy": "/old-host/policy.json",
                  "policy_sha256": digest(root / "policy.json")}],
                  "observations_sha256": digest(root / "masked/observations.jsonl")})
            config = {"budgets": [3], "horizon": 100, "masked_specification": "masked",
                      "datasets": [{"name": "test", "streams": "streams.json", "policy": "policy.json",
                                    "labels": "labels.json"}]}
            write(root / "config.json", config)
            with self.assertRaises(FileNotFoundError):
                run(root / "config.json", root / "unlabeled")
            self.assertTrue((root / "unlabeled/outputs.jsonl").is_file())
            write(root / "labels.json", {"expected": {"stream01": "alert"}})
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run(root / "config.json", root / "results"), 0)
            summary = json.loads((root / "results/summary.json").read_text())
            self.assertEqual(summary["unique_observations"], 2)
            self.assertFalse(summary["violations"])
            self.assertTrue(summary["cached_streaming_matches_visible_full"])
