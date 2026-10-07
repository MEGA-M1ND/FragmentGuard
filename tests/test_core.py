"""Offline checks for evidence integrity; no model evaluations.

These nine tests are carried over from the first prototype; only imports and the
fixture location changed when the code moved to ``src/fragmentguard``.
"""

import json
import unittest

from fragmentguard.correlation import correlate
from fragmentguard.pipeline import evaluate_stream
from fragmentguard.schema import FIXTURE_DIR, Event, parse_events


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.streams = json.loads((FIXTURE_DIR / "streams.json").read_text())
        self.policy = json.loads((FIXTURE_DIR / "policy.json").read_text())
        self.events = parse_events(self.streams[2]["events"])

    def test_future_writes_cannot_change_previous_publication(self) -> None:
        future = Event("later", 99, "a", "read", ("public-guide",), ("summary",), None)
        before = evaluate_stream(self.events, self.policy)
        after = evaluate_stream(self.events + [future], self.policy)
        self.assertEqual(before, after)

    def test_unknown_provenance_is_not_a_clean_result(self) -> None:
        result = evaluate_stream(self.events, self.policy)[0]["methods"]
        self.assertEqual(result["per_agent"]["status"], "insufficient_evidence")
        self.assertEqual(result["correlated"]["status"], "alert")

    def test_latest_write_shadows_restricted_old_write(self) -> None:
        replacement = Event("replacement", 5, "a", "read", ("public-guide",), ("summary",), None)
        events = self.events[:4] + [replacement, self.events[-1]]
        result = evaluate_stream(events, self.policy)[0]["methods"]["correlated"]
        self.assertEqual(result["status"], "clear")
        self.assertEqual(result["evidence_ids"], ["replacement", "e06"])

    def test_ground_truth_cannot_enter_event_schema(self) -> None:
        record = dict(self.streams[0]["events"][0], campaign_id="hidden-label")
        with self.assertRaises(ValueError):
            Event.from_dict(record)

    def test_budget_and_horizon_preserve_missingness(self) -> None:
        result = evaluate_stream(self.events, self.policy, budget=2)[0]["methods"]["correlated"]
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertLessEqual(result["events_reviewed"], 2)
        self.assertEqual(correlate(self.events, lookback=0), [self.events[-1]])

    def test_benign_handoffs_do_not_trigger_alerts(self) -> None:
        for stream in self.streams[:2]:
            methods = evaluate_stream(parse_events(stream["events"]), self.policy)[0]["methods"]
            self.assertEqual(methods["correlated"]["status"], "clear")

    def test_streams_do_not_share_resource_state(self) -> None:
        unknown = Event("e01", 1, "a", "publish", ("draft",), (), "public")
        evaluate_stream(self.events, self.policy)
        result = evaluate_stream([unknown], self.policy)[0]["methods"]["correlated"]
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_out_of_order_evidence_is_rejected(self) -> None:
        records = list(reversed(self.streams[0]["events"]))
        with self.assertRaises(ValueError):
            parse_events(records)

    def test_trusted_catalog_cannot_be_overwritten(self) -> None:
        overwrite = Event("overwrite", 0, "a", "read", ("restricted-record",), ("public-guide",), None)
        with self.assertRaises(ValueError):
            evaluate_stream([overwrite] + self.events, self.policy)


if __name__ == "__main__":
    unittest.main()
