"""Properties of the binding-based checker on generated streams, not just fixtures.

Why the soundness property should hold for *any* view: every resolved binding is
a true dependency edge, so restricted or public roots found in a view are a
subset of the true ones. A view can therefore only return ``alert`` if the
complete log also has restricted ancestry, and can only return ``clear`` for a
public publication if its whole lineage resolved inside the view, which then
equals the true lineage. Everything else is ``insufficient_evidence``. These
tests check that argument exhaustively over every sub-view of seeded random
streams; they are evidence for the property, not a formal proof.
"""

import itertools
import random
import unittest

from fragmentguard.correlation import correlate_selection
from fragmentguard.monitor import check
from fragmentguard.pipeline import METHODS, evaluate_stream
from fragmentguard.schema import Event, input_bindings

POLICY = {"restricted-record": "restricted", "public-guide": "public"}
ROOTS = list(POLICY)
INTERMEDIATES = ["r1", "r2", "r3"]
SEEDS = range(400)


def random_stream(rng: random.Random, length: int) -> list[Event]:
    events, tick = [], 0
    for index in range(length):
        last = index == length - 1
        operation = "publish" if last else rng.choice(["read", "transform", "transform", "note", "publish"])
        event_id, tick = f"e{index + 1:02d}", tick + rng.randint(1, 4)
        if operation == "note":
            events.append(Event(event_id, tick, "a", "note", (), (), None))
            continue
        inputs = tuple(rng.sample(ROOTS + INTERMEDIATES, rng.randint(1, 2)))
        agent = rng.choice("abc")
        if operation == "publish":
            events.append(Event(event_id, tick, agent, "publish", inputs, (), rng.choice(["public", "internal"])))
        else:
            outputs = tuple(rng.sample(INTERMEDIATES, rng.randint(1, 2)))
            events.append(Event(event_id, tick, agent, operation, inputs, outputs, None))
    return events


class GeneratedStreamProperties(unittest.TestCase):
    def test_every_subview_is_full_verdict_or_insufficient(self):
        checked = 0
        for seed in SEEDS:
            rng = random.Random(seed)
            events = random_stream(rng, rng.randint(2, 7))
            bindings = input_bindings(events)
            full = check(events, POLICY, bindings)["status"]
            prior = events[:-1]
            for size in range(len(prior) + 1):
                for subset in itertools.combinations(prior, size):
                    status = check(list(subset) + [events[-1]], POLICY, bindings)["status"]
                    self.assertIn(status, {full, "insufficient_evidence"},
                                  f"seed={seed} view={[e.event_id for e in subset]}")
                    checked += 1
        self.assertGreater(checked, 5000)

    def test_unbounded_correlation_matches_full_context(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            events = random_stream(rng, rng.randint(2, 7))
            bindings = input_bindings(events)
            selection = correlate_selection(events, budget=len(events), horizon=10**6, bindings=bindings)
            self.assertEqual(check(selection.events, POLICY, bindings)["status"],
                             check(events, POLICY, bindings)["status"], f"seed={seed}")

    def test_bindings_and_results_are_causal(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            events = random_stream(rng, rng.randint(4, 9))
            cut = rng.randint(1, len(events) - 1)
            prefix = events[:cut]
            self.assertEqual(input_bindings(prefix), {k: v for k, v in input_bindings(events).items()
                                                      if k in {e.event_id for e in prefix}})
            for budget in (1, 2, 3):
                before = evaluate_stream(prefix, POLICY, budget=budget, horizon=5)
                after = evaluate_stream(events, POLICY, budget=budget, horizon=5)
                self.assertEqual(after[: len(before)], before, f"seed={seed} budget={budget}")

    def test_all_views_respect_the_property_through_the_pipeline(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            events = random_stream(rng, rng.randint(2, 8))
            for budget in (1, 2, 3):
                for publication in evaluate_stream(events, POLICY, budget=budget, horizon=6):
                    methods = publication["methods"]
                    full = methods["full_context_reference"]["status"]
                    for name in METHODS:
                        self.assertIn(methods[name]["status"], {full, "insufficient_evidence"},
                                      f"seed={seed} budget={budget} {name}")


if __name__ == "__main__":
    unittest.main()
