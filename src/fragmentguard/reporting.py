"""Structured run reports, a Markdown summary, and the run manifest.

Evaluator labels are loaded here, and only after scanner results exist. They are
joined into a separate ``evaluation`` section and never into scanner rows.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from .monitor import VERDICTS
from .pipeline import METHODS
from .schema import FIXTURE_DIR, read_json

REPORT_SCHEMA_VERSION = 1
PURPOSE = (
    "Integration smoke test on four hand-designed synthetic streams; not a paper "
    "replication, a benchmark, or evidence of real-world detection performance."
)
LABEL_BOUNDARY = (
    "Scanner input contained only neutral stream IDs and label-free event records. "
    "Evaluator expectations were read from ground_truth.json only after scanner "
    "results had been produced, and appear only in the 'evaluation' section."
)
EVALUATED_METHODS = ("correlated", "full_context_reference")
METHOD_TITLES = {
    "per_agent": "Per agent",
    "fixed_window": "Fixed window",
    "correlated": "Correlated",
    "full_context_reference": "Full context (reference)",
}
PACKAGES = ("fragmentguard", "inspect-ai", "inspect-scout", "pandas", "pyarrow", "duckdb", "pydantic")
PACKAGE_DIR = Path(__file__).resolve().parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | Any) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def load_ground_truth(path: Path | None = None) -> dict[str, str]:
    """Evaluator-only expectations. Call only after scanner outputs exist."""
    raw = read_json(path if path is not None else FIXTURE_DIR / "ground_truth.json")
    expected = raw.get("expected") if isinstance(raw, dict) else None
    if not isinstance(expected, dict) or any(value not in VERDICTS for value in expected.values()):
        raise ValueError("ground_truth.json must map stream IDs to verdicts under 'expected'")
    return expected


def stream_results_from_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Extract per-stream publications from raw scanner rows (direct or recorded)."""
    results: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = row["value"]
        if isinstance(value, str):
            value = json.loads(value)
        if row["transcript_id"] in results:
            raise ValueError(f"Duplicate scanner result for {row['transcript_id']}")
        results[row["transcript_id"]] = value["publications"]
    return dict(sorted(results.items()))


def outcome_rows(stream_results: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for stream_id, publications in stream_results.items():
        for publication in publications:
            for method in METHODS:
                result = publication["methods"][method]
                rows.append({
                    "stream_id": stream_id,
                    "publication_id": publication["publication_id"],
                    "audience": publication["audience"],
                    "method": method,
                    "status": result["status"],
                    "evidence_ids": result["evidence_ids"],
                    "selected_event_count": result["events_reviewed"],
                    "records_examined": result["records_examined"],
                    "unresolved_inputs": result["unresolved_inputs"],
                    "explanation": result["explanation"],
                })
    return rows


def status_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts = {method: {verdict: 0 for verdict in VERDICTS} for method in METHODS}
    for row in rows:
        counts[row["method"]][row["status"]] += 1
    return counts


def evaluate(stream_results: dict[str, list[dict[str, Any]]], truth: dict[str, str]) -> dict[str, Any]:
    """Compare correlated and full-context outcomes with evaluator expectations."""
    checks, problems = [], []
    if set(truth) != set(stream_results):
        problems.append("Evaluator streams and scanned streams differ")
    for stream_id, publications in stream_results.items():
        if len(publications) != 1:
            problems.append(f"{stream_id}: expected exactly one publication, found {len(publications)}")
            continue
        publication = publications[0]
        for method in EVALUATED_METHODS:
            observed = publication["methods"][method]["status"]
            checks.append({
                "stream_id": stream_id,
                "publication_id": publication["publication_id"],
                "method": method,
                "expected": truth.get(stream_id),
                "observed": observed,
                "match": observed == truth.get(stream_id),
            })
    return {
        "methods_checked": list(EVALUATED_METHODS),
        "checks": checks,
        "problems": problems,
        "all_match": not problems and bool(checks) and all(check["match"] for check in checks),
        "note": "Expectations were written alongside the checker; agreement verifies wiring, not generalisation.",
    }


def build_report(
    *, mode: str, complete: bool, path_completed: str | None, config: dict[str, Any],
    stream_results: dict[str, list[dict[str, Any]]] | None, evaluation: dict[str, Any] | None,
    blocker: str | None = None,
) -> dict[str, Any]:
    rows = outcome_rows(stream_results) if complete and stream_results is not None else []
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "purpose": PURPOSE,
        "run_status": "complete" if complete else "incomplete",
        "execution_mode": mode,
        "path_completed": path_completed,
        "blocker": blocker,
        "config": config,
        "label_boundary": LABEL_BOUNDARY,
        "rows": rows,
        "status_counts": status_counts(rows) if complete else None,
        "evaluation": evaluation if complete else None,
        "measurement_notes": {
            "selected_event_count": "Measured: events passed to the checker for that view.",
            "records_examined": (
                "Measured: distinct records the selector dereferenced (publication plus bound producers "
                "looked up). Deriving input bindings is one shared pass over the log and is not counted. "
                "Not time or tokens."
            ),
            "event_budget": "Design: the three bounded views share a maximum budget, not equal cost.",
            "tokens_and_latency": "Not measured; the checker is deterministic and uses no model.",
        },
    }


def format_unresolved(items: list[dict[str, Any]]) -> str:
    """``resource<-producer`` for an omitted producer, ``resource<-none`` if never produced."""
    return ", ".join(f"{item['resource']}<-{item['bound_producer'] or 'none'}" for item in items) or "-"


def _cell(row: dict[str, Any] | None) -> str:
    if row is None:
        return "not measured"
    return f"{row['status']} ({row['selected_event_count']})"


def render_markdown(report: dict[str, Any], expected: dict[str, str] | None = None) -> str:
    lines = [
        "# FragmentGuard run report",
        "",
        f"- Run status: **{report['run_status']}**",
        f"- Execution mode: `{report['execution_mode']}`",
        f"- Path completed: {report['path_completed'] or 'none'}",
        f"- Budget: {report['config']['budget']} events; horizon: {report['config']['horizon']} ticks",
        "",
        f"> {report['purpose']}",
        "",
    ]
    if report["run_status"] != "complete":
        lines += [
            "## No outcomes recorded",
            "",
            "This run did not complete, so no scanner outcomes are reported. Missing",
            "outcomes are not clear results.",
            "",
            f"Blocker: {report['blocker'] or 'unspecified'}",
            "",
        ]
        return "\n".join(lines)

    by_key = {(r["stream_id"], r["publication_id"], r["method"]): r for r in report["rows"]}
    publications = sorted({(r["stream_id"], r["publication_id"]) for r in report["rows"]})
    header = ["Stream", "Publication", "Evaluator expectation"] + [METHOD_TITLES[m] for m in METHODS]
    lines += [
        "## Outcomes",
        "",
        "Each cell is `status (selected events)`. `insufficient_evidence` is a separate",
        "outcome and is never counted as `clear`.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + " --- |" * len(header),
    ]
    for stream_id, publication_id in publications:
        cells = [stream_id, publication_id, (expected or {}).get(stream_id, "not loaded")]
        cells += [_cell(by_key.get((stream_id, publication_id, method))) for method in METHODS]
        lines.append("| " + " | ".join(cells) + " |")

    lines += ["", "## Status counts", "", "| Method | alert | clear | insufficient_evidence |",
              "| --- | --- | --- | --- |"]
    for method in METHODS:
        counts = report["status_counts"][method]
        lines.append(f"| {METHOD_TITLES[method]} | {counts['alert']} | {counts['clear']} | "
                     f"{counts['insufficient_evidence']} |")

    lines += [
        "", "## Evidence", "",
        "`Unresolved` lists inputs whose bound producer is not in the view (`resource<-producer`) or",
        "that no earlier event wrote and the catalog does not classify (`resource<-none`).", "",
        "| Stream | Publication | Method | Status | Selected | Examined | Evidence IDs | Unresolved |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['stream_id']} | {row['publication_id']} | {row['method']} | {row['status']} | "
            f"{row['selected_event_count']} | {row['records_examined']} | {', '.join(row['evidence_ids'])} | "
            f"{format_unresolved(row['unresolved_inputs'])} |"
        )

    evaluation = report["evaluation"]
    verdict = "all expectations matched" if evaluation["all_match"] else "MISMATCH — see report.json"
    lines += [
        "",
        "## Evaluator check",
        "",
        f"Methods checked against evaluator-only expectations: {', '.join(evaluation['methods_checked'])}: "
        f"**{verdict}**. {evaluation['note']}",
        "",
        "## Label boundary",
        "",
        report["label_boundary"],
        "",
    ]
    return "\n".join(lines)


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def source_fingerprint() -> dict[str, Any]:
    files = {
        path.relative_to(PACKAGE_DIR).as_posix(): sha256_file(path)
        for path in sorted(PACKAGE_DIR.rglob("*"))
        if path.is_file() and path.suffix in (".py", ".json")
    }
    combined = sha256_bytes(json.dumps(files, sort_keys=True).encode())
    return {"package_sha256": combined, "files": files, **source_revision()}


def source_revision() -> dict[str, Any]:
    """Git revision of the checkout providing this package, when it is one."""
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(PACKAGE_DIR), *args], capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()

    try:
        top = Path(git("rev-parse", "--show-toplevel")).resolve()
        if (top / "src" / "fragmentguard").resolve() != PACKAGE_DIR:
            return {"git_commit": None, "git_dirty": None}
        commit = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--", "src", "pyproject.toml", "requirements.lock.txt"))
        return {"git_commit": commit, "git_dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "git_dirty": None}


def environment() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": package_versions(),
    }


def artifact_hashes(output: Path, exclude: tuple[str, ...] = ("manifest.json",)) -> dict[str, str]:
    return {
        path.relative_to(output).as_posix(): sha256_file(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.relative_to(output).as_posix() not in exclude
    }
