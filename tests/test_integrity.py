"""Additional offline integrity checks for the schema, selector, checker, and pipeline."""

import copy
import unittest

from fragmentguard.correlation import correlate, correlate_selection
from fragmentguard.monitor import check
from fragmentguard.pipeline import METHODS, evaluate_stream, evaluate_streams
from fragmentguard.schema import (
    Event, SchemaError, input_bindings, load_policy, load_streams, parse_events, parse_stream,
    validate_policy,
)

POLICY = {"restricted-record": "restricted", "public-guide": "public"}


def ev(event_id, tick, agent, operation, inputs=(), outputs=(), audience=None):
    return Event(event_id, tick, agent, operation, tuple(inputs), tuple(outputs), audience)


def record(**overrides):
    base = {"event_id": "e01", "tick": 1, "agent_id": "a", "operation": "read",
            "inputs": ["public-guide"], "outputs": ["draft"], "audience": None}
    base.update(overrides)
    return base


def statuses(events, **kwargs):
    methods = evaluate_stream(events, POLICY, **kwargs)[-1]["methods"]
    return {name: methods[name]["status"] for name in METHODS}


class SchemaTests(unittest.TestCase):
    def test_hidden_labels_cannot_enter_streams_or_events(self):
        with self.assertRaises(SchemaError):
            Event.from_dict(record(expected="alert"))
        with self.assertRaises(SchemaError):
            parse_stream({"stream_id": "stream01", "events": [record()], "label": "attack"})
        for stream_id in ("attack01", "stream01-exfil", "campaign7", ""):
            with self.assertRaises(SchemaError, msg=stream_id):
                parse_stream({"stream_id": stream_id, "events": [record()]})

    def test_invalid_records_fail_validation(self):
        invalid = [
            record(operation="execute"),
            record(event_id="bad id"),
            record(agent_id=""),
            record(inputs=["draft", "draft"]),
            record(inputs=["ok", 5]),
            record(tick=True),
            record(tick=-1),
            record(audience="public"),
            record(operation="publish", outputs=[], audience="everyone"),
            record(operation="publish", outputs=["copy"], audience="public"),
            record(operation="note"),
            record(operation="transform", outputs=[]),
            "not an object",
        ]
        for item in invalid:
            with self.assertRaises(SchemaError, msg=repr(item)):
                Event.from_dict(item)

    def test_ordering_and_duplicate_ids_are_rejected_not_repaired(self):
        with self.assertRaises(SchemaError):
            parse_events([record(), record(event_id="e02", tick=1)])  # equal ticks
        with self.assertRaises(SchemaError):
            parse_events([record(), record(tick=2)])  # duplicate ID
        with self.assertRaises(SchemaError):
            parse_events([record(event_id="e02", tick=2), record()])  # not sorted for the caller

    def test_policy_validation(self):
        for policy in ({}, {"x": "secret"}, {"bad id": "public"}, []):
            with self.assertRaises(SchemaError, msg=repr(policy)):
                validate_policy(policy)
        self.assertEqual(load_policy(), POLICY)


class SelectionAndCheckerTests(unittest.TestCase):
    def setUp(self):
        self.streams = {s["stream_id"]: parse_events(s["events"]) for s in load_streams()}

    def test_future_events_cannot_change_an_earlier_publication(self):
        events = self.streams["stream03"]
        later = [
            ev("e07", 7, "a", "read", ["public-guide"], ["summary"]),
            ev("e08", 8, "b", "read", ["restricted-record"], ["draft"]),
            ev("e09", 9, "c", "publish", ["summary"], audience="public"),
        ]
        before = evaluate_stream(events, POLICY)
        after = evaluate_stream(events + later, POLICY)
        self.assertEqual(after[0], before[0])
        self.assertEqual(len(after), 2)
        self.assertEqual(after[1]["methods"]["correlated"]["status"], "clear")

    def test_unknown_ancestry_is_never_clear(self):
        events = [ev("e01", 1, "a", "publish", ["mystery"], audience="public")]
        self.assertEqual(set(statuses(events).values()), {"insufficient_evidence"})
        mixed_public = [
            ev("e01", 1, "a", "read", ["public-guide"], ["part"]),
            ev("e02", 2, "b", "publish", ["part", "mystery"], audience="public"),
        ]
        self.assertEqual(statuses(mixed_public)["full_context_reference"], "insufficient_evidence")

    def test_known_restricted_branch_alerts_despite_unknown_branch(self):
        events = [
            ev("e01", 1, "a", "read", ["restricted-record"], ["part"]),
            ev("e02", 2, "b", "publish", ["mystery", "part"], audience="public"),
        ]
        result = evaluate_stream(events, POLICY)[0]["methods"]["full_context_reference"]
        self.assertEqual(result["status"], "alert")
        self.assertIn("mystery", result["explanation"])

    def test_latest_restricted_write_shadows_older_public_write(self):
        events = [
            ev("e01", 1, "a", "read", ["public-guide"], ["summary"]),
            ev("e02", 2, "b", "read", ["restricted-record"], ["summary"]),
            ev("e03", 3, "c", "publish", ["summary"], audience="public"),
        ]
        result = evaluate_stream(events, POLICY)[0]["methods"]["correlated"]
        self.assertEqual((result["status"], result["evidence_ids"]), ("alert", ["e02", "e03"]))

    def test_identical_resource_names_do_not_cross_workspaces(self):
        streams = [
            {"stream_id": "stream01", "events": [
                record(event_id="e01", inputs=["restricted-record"], outputs=["summary"])]},
            {"stream_id": "stream02", "events": [
                record(event_id="e02", tick=2, operation="publish", inputs=["summary"],
                       outputs=[], audience="public")]},
        ]
        results = evaluate_streams(streams, POLICY)
        self.assertEqual(results["stream01"], [])
        for name in METHODS:
            self.assertEqual(results["stream02"][0]["methods"][name]["status"], "insufficient_evidence")

    def test_benign_restricted_handoff_to_internal_audience_is_clear(self):
        methods = evaluate_stream(self.streams["stream02"], POLICY)[0]["methods"]
        self.assertEqual({methods[name]["status"] for name in METHODS}, {"clear"})

    def test_horizon_truncation_preserves_missingness(self):
        events = [
            ev("e01", 1, "a", "read", ["restricted-record"], ["draft"]),
            ev("e02", 150, "b", "publish", ["draft"], audience="public"),
        ]
        self.assertEqual(statuses(events)["correlated"], "insufficient_evidence")
        self.assertEqual(statuses(events, horizon=149)["correlated"], "alert")

    def test_budget_truncated_branch_is_missing_not_clear(self):
        # Depth-first, first-listed input first: the public branch fills the budget.
        events = [
            ev("e01", 1, "a", "read", ["public-guide"], ["left"]),
            ev("e02", 2, "a", "transform", ["left"], ["left2"]),
            ev("e03", 3, "b", "read", ["restricted-record"], ["right"]),
            ev("e04", 4, "c", "publish", ["left2", "right"], audience="public"),
        ]
        selected = correlate(events, budget=3)
        self.assertEqual([e.event_id for e in selected], ["e01", "e02", "e04"])
        self.assertEqual(statuses(events, budget=3)["correlated"], "insufficient_evidence")
        self.assertEqual(statuses(events, budget=4)["correlated"], "alert")

    def test_bounded_correlation_never_contradicts_full_context_on_fixtures(self):
        # Fixture-specific check. The general property, for arbitrary views of
        # arbitrary streams, is exercised in test_properties.py.
        for stream_id, events in self.streams.items():
            for budget in range(1, len(events) + 1):
                for horizon in range(0, 8):
                    for publication in evaluate_stream(events, POLICY, budget, horizon):
                        methods = publication["methods"]
                        self.assertIn(
                            methods["correlated"]["status"],
                            {methods["full_context_reference"]["status"], "insufficient_evidence"},
                            msg=f"{stream_id} budget={budget} horizon={horizon}",
                        )
                        self.assertLessEqual(methods["correlated"]["events_reviewed"], budget)

    def test_selection_reports_examined_records_separately(self):
        selection = correlate_selection(self.streams["stream04"])
        self.assertEqual([e.event_id for e in selection.events], ["e02", "e04", "e07"])
        # The publication plus the two bound producers it dereferenced (e04, e02).
        self.assertEqual(selection.records_examined, 3)

    def test_per_agent_view_does_not_replay_unseen_overwrite(self):
        # Before input bindings this view replayed the stale e01 write and returned
        # clear. The publication's input is bound to e02, which the view omits.
        events = [
            ev("e01", 1, "a", "read", ["public-guide"], ["summary"]),
            ev("e02", 2, "b", "read", ["restricted-record"], ["summary"]),
            ev("e03", 3, "a", "publish", ["summary"], audience="public"),
        ]
        result = statuses(events)
        self.assertEqual(result["per_agent"], "insufficient_evidence")
        self.assertEqual(result["correlated"], "alert")
        self.assertEqual(result["full_context_reference"], "alert")

    def test_checker_rejects_invalid_evidence_instead_of_scoring_it(self):
        note = ev("e01", 1, "a", "note")
        publication = ev("e02", 2, "a", "publish", ["x"], audience="public")
        bindings = input_bindings([note, publication])
        with self.assertRaises(SchemaError):
            check([], POLICY, bindings)
        with self.assertRaises(SchemaError):
            check([note], POLICY, bindings)
        with self.assertRaises(SchemaError):
            check([publication, note, publication], POLICY, bindings)
        with self.assertRaises(SchemaError):
            check([publication], POLICY, {})  # missing bindings
        with self.assertRaises(SchemaError):
            check([publication], POLICY, {"e02": {}})  # bindings must cover inputs
        writer = ev("e01", 1, "a", "read", ["public-guide"], ["y"])
        with self.assertRaises(SchemaError):  # bound to an event that did not write x
            check([writer, publication], POLICY, {"e01": {"public-guide": None}, "e02": {"x": "e01"}})

    def test_results_explain_with_selected_records(self):
        result = evaluate_stream(self.streams["stream03"], POLICY)[0]["methods"]["correlated"]
        self.assertEqual(result["evidence_ids"], ["e01", "e03", "e06"])
        self.assertIn("restricted-record", result["explanation"])
        self.assertIn("e01, e03", result["explanation"])

    def test_fixtures_do_not_put_full_provenance_in_last_three_events(self):
        for stream_id in ("stream01", "stream03", "stream04"):
            window = evaluate_stream(self.streams[stream_id], POLICY)[0]["methods"]["fixed_window"]
            self.assertEqual(window["status"], "insufficient_evidence", stream_id)

    def test_pipeline_does_not_mutate_input(self):
        streams = load_streams()
        snapshot = copy.deepcopy(streams)
        evaluate_streams(streams, POLICY)
        self.assertEqual(streams, snapshot)


if __name__ == "__main__":
    unittest.main()
