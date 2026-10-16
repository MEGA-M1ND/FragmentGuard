"""Trusted pointers survive missing payloads without turning uncertainty into safety."""

import copy
import itertools
import random
import unittest
from unittest.mock import patch

from fragmentguard.observation import evaluate_observation, freeze_complete, hide, validate_observation
from fragmentguard.schema import SchemaError
from fragmentguard.streaming import StreamingSensitivity
from test_bindings import POLICY, ev, overwrite_stream
from test_properties import random_stream


def frozen(events):
    return freeze_complete({"stream_id": "stream01", "events": [e.to_dict() for e in events]}, POLICY)


class ObservationTests(unittest.TestCase):
    def test_missing_replacement_does_not_resolve_to_stale_write(self):
        raw = hide(frozen(overwrite_stream("restricted-record")), {"e03"})
        with patch("fragmentguard.observation.input_bindings", side_effect=AssertionError("rebinding forbidden")):
            methods = evaluate_observation(raw, POLICY)[0]["methods"]
        for method, result in methods.items():
            self.assertEqual(result["status"], "insufficient_evidence", method)
            self.assertIn({"resource": "scratch", "bound_producer": "e03"}, result["unresolved_inputs"])

    def test_restricted_sibling_survives_missing_branch(self):
        events = [ev("e1", 1, "a", "read", ["public-guide"], ["left"]),
                  ev("e2", 2, "b", "read", ["restricted-record"], ["right"]),
                  ev("e3", 3, "c", "publish", ["left", "right"], audience="public")]
        methods = evaluate_observation(hide(frozen(events), {"e1"}), POLICY)[0]["methods"]
        for method in ("streaming", "correlated", "full_context_reference", "fixed_window"):
            self.assertEqual(methods[method]["status"], "alert")
            self.assertTrue(methods[method]["unresolved_inputs"])

    def test_missing_reference_cannot_be_reclassified_as_catalog_root(self):
        result = StreamingSensitivity(POLICY).update(
            ev("e2", 2, "a", "publish", ["public-guide"], audience="public"), {"public-guide": "e1"})
        self.assertEqual(result["status"], "insufficient_evidence")
        raw = frozen([ev("e1", 1, "a", "read", ["public-guide"], ["x"]),
                      ev("e2", 2, "c", "publish", ["x"], audience="public")])
        raw["identities"]["e1"]["outputs"] = ["public-guide"]
        with self.assertRaises(SchemaError):
            validate_observation(raw, POLICY)  # A produced catalog root is an integrity failure.

    def test_old_handle_is_valid_and_input_metadata_is_removed_with_payload(self):
        events = [ev("e1", 1, "a", "read", ["restricted-record"], ["x"]),
                  ev("e2", 2, "b", "read", ["public-guide"], ["x"]),
                  ev("e3", 3, "c", "publish", ["x"], audience="public")]
        raw = frozen(events)
        raw["bindings"]["e3"]["x"]["event_id"] = "e1"
        self.assertEqual(evaluate_observation(raw, POLICY)[0]["methods"]["streaming"]["status"], "alert")
        missing = hide(raw, {"e1"})
        self.assertNotIn("e1", missing["bindings"])
        self.assertEqual(set(missing["identities"]["e1"]), {"tick", "outputs"})
        self.assertEqual(evaluate_observation(missing, POLICY)[0]["methods"]["streaming"]["status"],
                         "insufficient_evidence")

    def test_bad_metadata_is_rejected_even_when_producer_payload_is_absent(self):
        raw = hide(frozen(overwrite_stream("restricted-record")), {"e03"})
        alterations = [
            lambda r: r["bindings"]["e04"]["scratch"].update(stream_id="stream02"),
            lambda r: r["bindings"]["e04"]["scratch"].update(event_id="ghost"),
            lambda r: r["bindings"]["e04"]["scratch"].update(event_id="e02"),
            lambda r: r["bindings"]["e04"].update(scratch=None),
            lambda r: r["identities"]["e03"].update(tick=20),
            lambda r: r["identities"]["e03"].update(inputs=["secret-hidden-input"]),
            lambda r: r["bindings"].update(e03={"restricted-record": None}),
        ]
        for change in alterations:
            with self.subTest(change=alterations.index(change)):
                bad = copy.deepcopy(raw)
                change(bad)
                with self.assertRaises(SchemaError):
                    evaluate_observation(bad, POLICY)

    def test_all_small_subsets_are_sound_and_controls_agree(self):
        streams = [overwrite_stream(root, ticks=(1, 2, 3, 104))
                   for root in ("restricted-record", "public-guide")]
        # Reuse the existing seeded stream generator: branches, unknowns,
        # old writes, multiple publications, internal/public and multiple agents.
        streams.extend(random_stream(random.Random(seed), 6) for seed in range(40))
        for events in streams:
            raw = frozen(events)
            control = evaluate_observation(raw, POLICY)[-1]["methods"]
            reference = control["full_context_reference"]["status"]
            self.assertEqual(control["streaming"]["status"], reference)
            for size in range(len(events)):
                for subset in itertools.combinations(events[:-1], size):
                    methods = evaluate_observation(hide(raw, {e.event_id for e in subset}), POLICY)[-1]["methods"]
                    for name, result in methods.items():
                        self.assertIn(result["status"], {reference, "insufficient_evidence"}, name)
