"""Regression and controls for stale-write resolution.

A read must resolve to the write that actually produced it. If the view omits
that producer, the input is unresolved; it must not fall back to an older
selected write of the same resource name.
"""

import unittest

from fragmentguard.pipeline import METHODS, evaluate_stream
from fragmentguard.schema import Event

POLICY = {"restricted-record": "restricted", "public-guide": "public"}


def ev(event_id, tick, agent, operation, inputs=(), outputs=(), audience=None):
    return Event(event_id, tick, agent, operation, tuple(inputs), tuple(outputs), audience)


def overwrite_stream(overwrite_root, ticks=(1, 2, 3, 4)):
    """e03 rewrites `scratch` after e02 consumed the older `scratch` written by e01."""
    t1, t2, t3, t4 = ticks
    return [
        ev("e01", t1, "a", "read", ["public-guide"], ["scratch"]),
        ev("e02", t2, "a", "transform", ["scratch"], ["snapshot"]),
        ev("e03", t3, "b", "read", [overwrite_root], ["scratch"]),
        ev("e04", t4, "c", "publish", ["snapshot", "scratch"], audience="public"),
    ]


def outcome(events, method="correlated", **kwargs):
    result = evaluate_stream(events, POLICY, **kwargs)[0]["methods"][method]
    return result["status"], result["evidence_ids"]


class StaleWriteRegressionTests(unittest.TestCase):
    def test_omitted_producer_is_unresolved_not_an_older_write(self):
        events = overwrite_stream("restricted-record")
        self.assertEqual(outcome(events, budget=3), ("insufficient_evidence", ["e01", "e02", "e04"]))
        self.assertEqual(outcome(events, budget=4), ("alert", ["e01", "e02", "e03", "e04"]))
        self.assertEqual(outcome(events, "full_context_reference")[0], "alert")

    def test_benign_overwrite_control(self):
        # Same shape, public overwrite. A budget-3 clear would rest on the stale
        # e01 write, so it is unsupported; the complete lineage is clear.
        events = overwrite_stream("public-guide")
        self.assertEqual(outcome(events, budget=3)[0], "insufficient_evidence")
        self.assertEqual(outcome(events, budget=4)[0], "clear")
        self.assertEqual(outcome(events, "full_context_reference")[0], "clear")

    def test_stale_restricted_write_in_view_does_not_cause_false_alert(self):
        events = [
            ev("e01", 1, "a", "read", ["restricted-record"], ["scratch"]),
            ev("e02", 2, "b", "read", ["public-guide"], ["scratch"]),
            ev("e03", 3, "a", "publish", ["scratch"], audience="public"),
        ]
        self.assertEqual(outcome(events, "per_agent"), ("insufficient_evidence", ["e01", "e03"]))
        self.assertEqual(outcome(events)[0], "clear")
        self.assertEqual(outcome(events, "full_context_reference")[0], "clear")

    def test_branching_lineage_needs_every_branch_for_clear(self):
        events = [
            ev("e01", 1, "a", "read", ["public-guide"], ["left"]),
            ev("e02", 2, "b", "read", ["public-guide"], ["right"]),
            ev("e03", 3, "b", "transform", ["right"], ["right2"]),
            ev("e04", 4, "c", "publish", ["right2", "left"], audience="public"),
        ]
        self.assertEqual(outcome(events, budget=3), ("insufficient_evidence", ["e02", "e03", "e04"]))
        self.assertEqual(outcome(events, budget=4)[0], "clear")

    def test_horizon_truncation_keeps_omitted_producers_unresolved(self):
        events = overwrite_stream("restricted-record", ticks=(1, 2, 3, 104))
        self.assertEqual(outcome(events, budget=4, horizon=100), ("insufficient_evidence", ["e04"]))
        self.assertEqual(outcome(events, budget=4, horizon=101), ("alert", ["e03", "e04"]))
        self.assertEqual(outcome(events, budget=4, horizon=103)[0], "alert")
        benign = overwrite_stream("public-guide", ticks=(1, 2, 3, 104))
        # e03 is in range but snapshot's producer e02 is not: still unresolved.
        self.assertEqual(outcome(benign, budget=4, horizon=101), ("insufficient_evidence", ["e03", "e04"]))
        self.assertEqual(outcome(benign, budget=4, horizon=103)[0], "clear")

    def test_future_events_do_not_change_earlier_publication(self):
        events = overwrite_stream("restricted-record")
        later = [
            ev("e05", 5, "a", "read", ["public-guide"], ["scratch"]),
            ev("e06", 6, "c", "publish", ["scratch"], audience="public"),
        ]
        for budget in (1, 2, 3, 4):
            before = evaluate_stream(events, POLICY, budget=budget)
            after = evaluate_stream(events + later, POLICY, budget=budget)
            self.assertEqual(after[0], before[0], f"budget={budget}")
        second = evaluate_stream(events + later, POLICY)[1]["methods"]
        self.assertEqual(second["correlated"]["status"], "clear")
        self.assertEqual(second["correlated"]["evidence_ids"], ["e05", "e06"])
        self.assertEqual(second["full_context_reference"]["status"], "clear")

    def test_every_view_is_full_context_verdict_or_insufficient(self):
        for root in ("restricted-record", "public-guide"):
            events = overwrite_stream(root)
            for budget in (1, 2, 3, 4):
                methods = evaluate_stream(events, POLICY, budget=budget)[0]["methods"]
                full = methods["full_context_reference"]["status"]
                for name in METHODS:
                    self.assertIn(methods[name]["status"], {full, "insufficient_evidence"},
                                  f"{root} budget={budget} {name}")


if __name__ == "__main__":
    unittest.main()
