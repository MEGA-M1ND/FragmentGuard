# Development log

Short factual entries. These are engineering notes, not research results.

## 2026-10-07: prototype (hosted runtime, imported)

- The direct scanner path worked and nine offline tests passed.
- The full Scout scheduler did not complete in that runtime. The one-process
  attempt failed with `psutil.NoSuchProcess`, because the PID differed from the
  `/proc` namespace. The two-process attempt hit a local socket `PermissionError`,
  then `EOFError`.
- Scout returned an empty error list for the interrupted job. So "no errors" was
  not used as evidence of completion. See `examples/historical_prototype/`.

## 2026-10-07: milestone 1 in this repository

- The repository had no commits. The prototype's ZIP was inspected and its
  manifest hashes verified (28/28 matched). The code was refactored from a flat
  `fragmentguard/` package into `src/fragmentguard/`: `schema`, `correlation`,
  `monitor`, `pipeline`, `scout`, `reporting`, `cli`. Fixtures are bundled as
  package data, so the CLI works from any directory.
- Fixtures were kept **byte-identical** (same SHA-256 as the prototype). Fixture
  4 differs from fixture 3 in its resource names, its agent roles, and where the
  relevant events sit among benign ones. Its ticks are still consecutive
  integers. Varying tick gaps is left to the next dataset, not done by editing
  the imported fixtures.
- The nine original tests were kept. Only their imports and fixture path
  changed. Thirty tests were added: schema, selection, and checker edge cases;
  JSON/Markdown agreement; incomplete runs; the label boundary; and Scout round
  trip and mode agreement.
- The dependency pins were unchanged (Python 3.12.3 here, 3.12.14 in the
  prototype). `pip freeze` in this environment reproduced the prototype's lock
  file exactly.
- **Scout's scheduler completed here** with `max_processes=1` and the mock model:
  4 scans, 4 results, 0 errors, 0 tokens, empty `model_usage`. Nothing was
  patched. So the prototype's blocker looks specific to that environment.
- Inspect Scout's documentation site and arXiv were blocked by this environment's
  network egress proxy. Scout interfaces were therefore checked against the
  installed 0.5.4 package (`inspect.signature`). The paper's title, authors, and
  FakeLab availability were confirmed through a web search result that quoted
  the arXiv abstract page.
- Scout 0.5.4 prints a `DeprecationWarning` (`fetch_arrow_table()` in its parquet
  index) during tests. It is harmless and comes from upstream. It is left alone.
- Scout's `display="none"` still printed the scan panel during CLI runs. This is
  cosmetic.
- A missing transcript database does not raise in `scan()`. It returns
  `complete=False` with an empty error list. The runner's completion checks
  (`status.complete`, scan and result counts equal to the number of transcripts,
  zero tokens) catch this, and a test covers it.
- Scout's `_scan.json` stores the transcripts location exactly as passed. Passing
  the relative `--output` path keeps it relative to the working directory where
  the run started.

## Improvement opportunities (not done)

- Branch priority is depth-first in input order. A breadth-first or
  restricted-first policy would change which evidence gets truncated, but it
  must be frozen before any labelled evaluation.
- The per-agent and fixed-window baselines can replay writes that later writes
  replaced (see `docs/assumptions.md` §10). A future baseline could flag
  resources whose producer it did not see.
- Correlation re-scans history for each lookup. That costs O(n) per input, which
  is fine at this scale. An index of the latest writer would help larger streams.
  Measure before optimising.
