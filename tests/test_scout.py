"""Inspect Scout integration checks. These run offline with the mock model setting."""

import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from inspect_ai.event import InfoEvent

from fragmentguard import cli, reporting, scout
from fragmentguard.pipeline import PipelineConfig, evaluate_streams
from fragmentguard.schema import SchemaError, load_policy, load_streams


class ScoutIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.streams, self.policy = load_streams(), load_policy()
        self.database = self.root / "transcripts"
        asyncio.run(scout.write_database(self.database, self.streams))

    def test_database_round_trip_preserves_payloads_and_ids(self):
        transcripts = asyncio.run(scout.read_database(self.database))
        self.assertEqual([t.transcript_id for t in transcripts], [s["stream_id"] for s in self.streams])
        for transcript, stream in zip(transcripts, self.streams, strict=True):
            self.assertEqual(transcript.source_type, scout.SOURCE_TYPE)
            self.assertFalse(transcript.metadata)
            self.assertTrue(all(isinstance(e, InfoEvent) for e in transcript.events))
            self.assertEqual([e.data for e in transcript.events], stream["events"])
            self.assertEqual(
                [e.uuid for e in transcript.events],
                [f"{stream['stream_id']}.{record['event_id']}" for record in stream["events"]],
            )

    def test_scanner_rejects_non_synthetic_or_labelled_transcripts(self):
        scan_fn = scout.fragmentguard(self.policy)
        transcript = asyncio.run(scout.read_database(self.database))[0]
        labelled = transcript.model_copy(update={"metadata": {"expected": "clear"}})
        foreign = transcript.model_copy(update={"events": [
            transcript.events[0].model_copy(update={"source": "real.tool"})]})
        moved = transcript.model_copy(update={"transcript_id": "stream09"})
        for bad in (labelled, foreign, moved):
            with self.assertRaises(SchemaError):
                asyncio.run(scan_fn(bad))

    def test_direct_and_scheduled_modes_agree_when_both_complete(self):
        config = PipelineConfig()
        direct = asyncio.run(scout.run_direct(self.database, self.policy, config))
        with contextlib.redirect_stdout(io.StringIO()):
            scheduled = scout.run_scheduled(
                self.database, self.root / "scans", self.policy, config, len(self.streams))
        self.assertTrue(scheduled["complete"], f"Scheduled scan incomplete: {scheduled.get('blocker')} "
                                               f"{scheduled.get('errors')}")
        self.assertTrue(all(scheduled["checks"].values()))
        direct_results = reporting.stream_results_from_rows(direct)
        scheduled_results = reporting.stream_results_from_rows(scheduled["rows"])
        self.assertEqual(direct_results, scheduled_results)
        self.assertEqual(direct_results, evaluate_streams(self.streams, self.policy, config))

    def test_incomplete_scheduled_scan_stays_incomplete(self):
        with contextlib.redirect_stdout(io.StringIO()):
            attempt = scout.run_scheduled(
                self.root / "missing", self.root / "scans", self.policy, PipelineConfig(), len(self.streams))
        self.assertFalse(attempt["complete"])
        self.assertNotIn("rows", attempt)
        self.assertTrue(attempt["blocker"])

    def test_cli_direct_demo_writes_complete_hashed_artifacts(self):
        output = self.root / "runs" / "direct"
        cwd = os.getcwd()
        os.chdir(self.root)  # The installed command must not depend on the repository cwd.
        self.addCleanup(os.chdir, cwd)
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["demo", "--mode", "direct", "--output", str(output)])
        self.assertEqual(code, cli.EXIT_OK)
        manifest = json.loads((output / "manifest.json").read_text())
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(manifest["completion"]["status"], "complete")
        self.assertIs(manifest["model_generation"]["invoked"], False)
        self.assertEqual(report["run_status"], "complete")
        self.assertTrue(report["evaluation"]["all_match"])
        for relative, digest in manifest["artifacts"].items():
            self.assertEqual(reporting.sha256_file(output / relative), digest, relative)
        self.assertIn("report.md", manifest["artifacts"])
        self.assertIn("scanner-results.json", manifest["artifacts"])

    def test_cli_custom_inputs_run_through_both_modes(self):
        example = Path(__file__).resolve().parent.parent / "examples" / "custom_inputs"
        common = ["--streams", str(example / "streams.json"), "--policy", str(example / "policy.json"),
                  "--budget", "3", "--horizon", "100"]
        outcomes = {}
        for mode in ("direct", "scout"):
            output = self.root / f"custom-{mode}"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["demo", "--mode", mode, "--output", str(output), *common,
                                 "--labels", str(example / "labels.json"), "--gate", "full_context_reference"])
            self.assertEqual(code, cli.EXIT_OK, mode)
            report = json.loads((output / "report.json").read_text())
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(report["run_status"], "complete")
            self.assertEqual(manifest["inputs"]["streams"]["sha256"],
                             reporting.sha256_file(example / "streams.json"))
            outcomes[mode] = [(r["stream_id"], r["publication_id"], r["method"], r["status"])
                              for r in report["rows"]]
        self.assertEqual(outcomes["direct"], outcomes["scout"])

        gated = self.root / "custom-gated"
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["demo", "--mode", "direct", "--output", str(gated), *common,
                             "--labels", str(example / "labels.json"), "--gate", "correlated"])
        self.assertEqual(code, cli.EXIT_MISMATCH)  # insufficient_evidence is not a match

        unlabelled = self.root / "custom-unlabelled"
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["demo", "--mode", "direct", "--output", str(unlabelled), *common])
        self.assertEqual(code, cli.EXIT_OK)
        report = json.loads((unlabelled / "report.json").read_text())
        self.assertIsNone(report["evaluation"])
        manifest = json.loads((unlabelled / "manifest.json").read_text())
        self.assertIsNone(manifest["inputs"]["labels (evaluator-only, read after scanning)"])

    def test_cli_rejects_missing_labels_before_scanning(self):
        output = self.root / "never-created"
        with self.assertRaises(SystemExit):
            cli.main(["demo", "--mode", "direct", "--output", str(output),
                      "--labels", str(self.root / "missing.json")])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
