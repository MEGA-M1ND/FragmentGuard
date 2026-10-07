# Historical prototype (imported, not re-run)

This directory is the first FragmentGuard prototype, imported unchanged from
`fragmentguard_first_run.zip` (the `.venv/` directory and caches were excluded).
It was produced in a separate hosted runtime on 7 October 2026, before this
repository had any commits. It is kept for provenance only. **Its outputs are
not results of this repository's code and do not replace a fresh run.** Fresh
results are in [`../first_run/`](../first_run/).

## What is here

- `ARTIFACT_MANIFEST.json`: the prototype's own SHA-256 list for 28 files. Every
  listed file was checked on import and matched, using the paths in this
  directory. A hash shows the files are unchanged since the manifest was
  written. It does not prove the original run happened as described.
- `README.md`, `FIRST_RUN.md`, `NEXT_EXPERIMENT.md`: the prototype's notes, verbatim.
- `fragmentguard/`, `tests/`, `fixtures/`, `requirements*.txt`: the prototype's
  source, the nine original tests, and its fixtures. The current package in
  `src/fragmentguard/` was refactored from this code. Its bundled fixtures are
  byte-identical to `fixtures/` here: the SHA-256 hashes match.
- `runs/direct-first-run/`: the prototype's successful direct-mode run.
- `runs/first-run/` and `runs/scout-two-workers/`: two **interrupted** scheduled
  scans. Their `_summary.json` reports `"complete": false`, and their error lists
  are empty even though the jobs did not finish. These are not completed
  evaluations.

## Recorded blockers (historical observations)

In that hosted runtime the Scout scheduler failed before any scanning happened:

- With one process: `psutil.NoSuchProcess` (pid=2). The PID that Python reported
  did not match the mounted `/proc` namespace.
- With two processes: the worker manager's local socket was refused with
  `PermissionError: [Errno 1] Operation not permitted`, then `EOFError`.

These are observations about that environment, not an established Scout defect.
The same pinned versions completed scheduled scans in this repository's
environment (see `docs/first_run.md`).

The Scout recorder files here contain absolute paths from the original runtime
(`/workspace/scratch/...`). They were left as recorded.
