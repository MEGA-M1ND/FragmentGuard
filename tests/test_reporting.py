"""Report integrity: JSON/Markdown agreement, incomplete runs, and the label boundary."""

import tempfile
import unittest
from pathlib import Path

import fragmentguard
from fragmentguard import cli, reporting
from fragmentguard.pipeline import METHODS, PipelineConfig, evaluate_streams
from fragmentguard.schema import load_policy, load_streams


def markdown_table(text: str, heading: str) -> list[list[str]]:
    lines = text.split(f"## {heading}\n", 1)[1].splitlines()
    end = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    rows = [line for line in lines[:end] if line.startswith("|")]
    return [[cell.strip() for cell in row.strip("|").split("|")] for row in rows[2:]]


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.results = evaluate_streams(load_streams(), load_policy())
        self.expected = reporting.load_ground_truth()
        self.report = reporting.build_report(
            mode="direct", complete=True, path_completed="test", config=PipelineConfig().to_dict(),
            stream_results=self.results, evaluation=reporting.evaluate(self.results, self.expected),
        )
        self.markdown = reporting.render_markdown(self.report, self.expected)

    def test_json_and_markdown_reports_agree(self):
        rows = self.report["rows"]
        self.assertEqual(len(rows), 4 * len(METHODS))
        evidence = markdown_table(self.markdown, "Evidence")
        self.assertEqual(
            evidence,
            [[r["stream_id"], r["publication_id"], r["method"], r["status"], str(r["selected_event_count"]),
              str(r["records_examined"]), ", ".join(r["evidence_ids"]),
              reporting.format_unresolved(r["unresolved_inputs"])] for r in rows],
        )
        outcomes = markdown_table(self.markdown, "Outcomes")
        by_key = {(r["stream_id"], r["method"]): r for r in rows}
        for cells in outcomes:
            stream_id = cells[0]
            self.assertEqual(cells[2], self.expected[stream_id])
            for method, cell in zip(METHODS, cells[3:]):
                row = by_key[(stream_id, method)]
                self.assertEqual(cell, f"{row['status']} ({row['selected_event_count']})")
        counts = markdown_table(self.markdown, "Status counts")
        for method, cells in zip(METHODS, counts):
            self.assertEqual([int(c) for c in cells[1:]],
                             list(self.report["status_counts"][method].values()))

    def test_fixture_outcomes_match_evaluator_expectations(self):
        evaluation = self.report["evaluation"]
        self.assertTrue(evaluation["all_match"])
        self.assertEqual(
            [c["observed"] for c in evaluation["checks"] if c["method"] == "correlated"],
            ["clear", "clear", "alert", "alert"],
        )

    def test_evaluator_reports_mismatch(self):
        wrong = dict(self.expected, stream01="alert")
        self.assertFalse(reporting.evaluate(self.results, wrong)["all_match"])
        self.assertFalse(reporting.evaluate(self.results, {"stream01": "clear"})["all_match"])

    def test_incomplete_run_reports_no_outcomes(self):
        report = reporting.build_report(
            mode="scout", complete=False, path_completed=None, config=PipelineConfig().to_dict(),
            stream_results=self.results, evaluation={"all_match": True}, blocker="scheduler blocked",
        )
        self.assertEqual(report["run_status"], "incomplete")
        self.assertEqual(report["rows"], [])
        self.assertIsNone(report["status_counts"])
        self.assertIsNone(report["evaluation"])
        markdown = reporting.render_markdown(report)
        self.assertIn("No outcomes recorded", markdown)
        self.assertIn("scheduler blocked", markdown)
        self.assertNotIn("| clear", markdown)
        self.assertNotIn("## Outcomes", markdown)

    def test_label_file_is_not_read_by_selection_or_scanner_code(self):
        package = Path(fragmentguard.__file__).parent
        for module in ("schema.py", "correlation.py", "monitor.py", "pipeline.py", "scout.py"):
            source = (package / module).read_text()
            self.assertNotIn("ground_truth", source, module)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "run"
            existing.mkdir()
            (existing / "keep.txt").write_text("first attempt")
            with self.assertRaises(SystemExit):
                cli.run_demo("direct", existing)
            self.assertEqual([p.name for p in existing.iterdir()], ["keep.txt"])


if __name__ == "__main__":
    unittest.main()
