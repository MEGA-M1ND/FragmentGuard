"""Exercise the new commands' freeze, scoring and evaluator boundaries."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fragmentguard.experiments.__main__ import compare
from fragmentguard.experiments.common import read, write
from fragmentguard.experiments.missing import freeze_masks, run_missing
from fragmentguard.observation import freeze_complete, hide
from fragmentguard.schema import SchemaError
from test_bindings import POLICY, overwrite_stream


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write(self.root / "streams.json", [{"stream_id": "stream01", "events":
                                          [e.to_dict() for e in overwrite_stream("restricted-record")]}])
        write(self.root / "policy.json", POLICY)
        write(self.root / "labels.json", {"expected": {"stream01": "alert"}})
        write(self.root / "comparison.json", {"datasets": [{"name": "replacement", "kind": "test",
              "streams": "streams.json", "policy": "policy.json", "labels": "labels.json"}]})

    def test_frozen_masks_deduplicate_categories_and_score_conservatively(self):
        spec, results = self.root / "spec", self.root / "results"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(freeze_masks(self.root / "comparison.json", spec), 0)
            self.assertEqual(run_missing(spec, results), 0)
        plan = read(spec / "plan.json")
        self.assertEqual(plan["unique_observations"], 8)
        observations = [json.loads(line) for line in (spec / "observations.jsonl").read_text().splitlines()]
        self.assertEqual(len({tuple(r["hidden_ids"]) for r in observations}), 8)
        self.assertTrue(any("direct_producer" in r["categories"] for r in observations))
        summary = read(results / "summary.json")
        self.assertEqual(summary["method_outputs"], 40)
        self.assertFalse(summary["violations"])
        manifest = read(results / "experiment-manifest.json")
        for name, digest in manifest["artifacts"].items():
            self.assertEqual(hashlib.sha256((results / name).read_bytes()).hexdigest(), digest)
        with (spec / "observations.jsonl").open("a") as handle:
            handle.write("{}\n")
        with self.assertRaisesRegex(ValueError, "Frozen observations changed"):
            run_missing(spec, self.root / "tampered-results")

    def test_evaluator_is_opened_only_after_outputs_and_disagreements_fail(self):
        # Absence of evaluator metadata must not prevent writing genuine method outputs.
        (self.root / "labels.json").unlink()
        with self.assertRaises(FileNotFoundError):
            compare(self.root / "comparison.json", self.root / "unlabeled")
        self.assertTrue((self.root / "unlabeled/outputs.json").is_file())
        write(self.root / "labels.json", {"expected": {"stream01": "clear"}})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(compare(self.root / "comparison.json", self.root / "mislabeled"), 1)
        self.assertTrue(read(self.root / "mislabeled/summary.json")["replacement"]["reference_label_mismatches"])

    def test_partial_api_does_not_accept_hidden_consumer_edges(self):
        raw = freeze_complete({"stream_id": "stream01", "events":
                               [e.to_dict() for e in overwrite_stream("restricted-record")]}, POLICY)
        partial = hide(raw, {"e03"})
        partial["bindings"]["e03"] = raw["bindings"]["e03"]
        from fragmentguard.observation import validate_observation

        with self.assertRaisesRegex(SchemaError, "hidden input edges"):
            validate_observation(partial, POLICY)


class NewArtifactPreservation(unittest.TestCase):
    def test_all_preexisting_example_and_input_bytes_remain_identical(self):
        root = Path(__file__).resolve().parents[1]
        inventory = read(root / "experiments/streaming_baseline/historical-sha256.json")
        self.assertEqual(len(inventory), 425)
        for name, digest in inventory.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)

    def test_new_experiment_manifests_match_their_raw_outputs(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob("examples/**/experiment-manifest.json"):
            manifest = read(path)
            outputs = path.parent / ("outputs.jsonl" if (path.parent / "outputs.jsonl").exists() else "outputs.json")
            self.assertEqual(hashlib.sha256(outputs.read_bytes()).hexdigest(), manifest["outputs_sha256"])
