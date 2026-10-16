"""Forward-state controls, including replacements and explicit old handles."""

import random
import unittest

from fragmentguard.experiments.evaluate import evaluate
from fragmentguard.schema import input_bindings
from fragmentguard.streaming import StreamingSensitivity
from test_bindings import POLICY, ev, overwrite_stream
from test_properties import random_stream


class StreamingTests(unittest.TestCase):
    def run_events(self, events, bindings=None):
        state = StreamingSensitivity(POLICY)
        bindings = bindings if bindings is not None else input_bindings(events)
        results = [state.update(e, bindings[e.event_id]) for e in events]
        return results[-1]

    def test_public_restricted_unknown_and_internal(self):
        for root, expected in (("public-guide", "clear"), ("restricted-record", "alert"),
                               ("unknown", "insufficient_evidence")):
            for audience in ("public", "internal"):
                with self.subTest(root=root, audience=audience):
                    events = [ev("e1", 1, "a", "read", [root], ["x"]),
                              ev("e2", 2, "b", "transform", ["x"], ["y"]),
                              ev("e3", 3, "c", "publish", ["y"], audience=audience)]
                    result = self.run_events(events)
                    self.assertEqual(result["status"], expected if audience == "public" else "clear")
                    self.assertEqual(result["retained_versions"], 2)

    def test_restricted_survives_unknown_sibling(self):
        result = self.run_events([ev("e1", 1, "a", "read", ["restricted-record"], ["x"]),
                                  ev("e2", 2, "c", "publish", ["x", "unknown"], audience="public")])
        self.assertEqual(result["status"], "alert")
        self.assertTrue(result["unresolved_inputs"])

    def test_replacement_stale_write_and_omission(self):
        for root in ("restricted-record", "public-guide"):
            events = overwrite_stream(root)
            bindings = input_bindings(events)
            self.assertEqual(self.run_events(events)["status"], "alert" if root == "restricted-record" else "clear")
            omitted = self.run_events([events[0], events[1], events[3]], bindings)
            self.assertEqual(omitted["status"], "insufficient_evidence")
            self.assertIn({"resource": "scratch", "bound_producer": "e03"}, omitted["unresolved_inputs"])

    def test_explicit_old_version_handle_survives_display_name_replacement(self):
        events = [ev("e1", 1, "a", "read", ["restricted-record"], ["scratch"]),
                  ev("e2", 2, "a", "read", ["public-guide"], ["scratch"]),
                  ev("e3", 3, "c", "publish", ["scratch"], audience="public")]
        bindings = input_bindings(events)
        bindings["e3"]["scratch"] = "e1"  # A recorder-supplied old handle, not the compatibility binder.
        self.assertEqual(self.run_events(events, bindings)["status"], "alert")

    def test_forward_baseline_matches_reference_on_generated_valid_streams(self):
        for seed in range(120):
            events = random_stream(random.Random(seed), 7)
            for pub in evaluate(events, POLICY, input_bindings(events)):
                self.assertEqual(pub["methods"]["streaming"]["status"],
                                 pub["methods"]["full_context_reference"]["status"], f"seed={seed}")
