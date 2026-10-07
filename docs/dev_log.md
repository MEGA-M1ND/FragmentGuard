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
- ~~The per-agent and fixed-window baselines can replay writes that later writes
  replaced.~~ Addressed by input bindings (see the entry below).
- ~~Correlation re-scans history for each lookup.~~ Correlation now follows
  precomputed bindings: one O(n) pass per stream, then direct lookups.

## 2026-10-07: stale-write bug in correlated selection (fixed)

- **Bug.** The checker resolved a read by resource name to the latest *selected*
  write. When the view omitted a read's actual producer but contained an older
  write of the same name, the read silently used the older write. Reproduction
  (budget 3, horizon 100):
  - e01 read public-guide→scratch
  - e02 transform scratch→snapshot
  - e03 read restricted-record→scratch
  - e04 publish [snapshot, scratch] public

  Correlation selected e01/e02/e04 and returned `clear`; full context returned
  `alert`. The same mechanism produced a per-agent false `alert` when a stale
  restricted write was in view and the public overwrite was not.
- **Why the fixtures missed it.** None of the four fixtures overwrites a resource
  after it has been read. The old "never contradicts full context" test ran only
  on those fixtures.
- **Process.** The regression tests and controls were committed first and failed
  (4 of 7) before the fix (commit `bc8598f`).
- **Fix.** `schema.input_bindings` binds each read to its actual producer: the
  latest earlier write in the workspace. Correlation follows bindings, and the
  checker resolves every read through its binding. An omitted producer leaves
  the input unresolved.
  - Bindings are causal and label-free.
  - They are given identically to all four views; only event selection differs.
  - Results now include `unresolved_inputs`.
  - Outcomes on the bundled fixtures are unchanged.
- **Behaviour changes beyond the regression.**
  - The per-agent stale-write characterisation test (previously a wrong `clear`)
    now expects `insufficient_evidence`.
  - `records_examined` for the correlated view now counts records the selector
    dereferenced, not records scanned while searching for producers. The shared
    binding pass is not counted. For stream04 this is 3, previously 7.
- **Evidence the class of bug is closed.** A property test checks that every
  sub-view of 400 generated streams returns either the full-context verdict or
  `insufficient_evidence`. The pre-fix checker breaks this on 71 of 7,366
  sub-views; the fixed checker on none.
- **Remaining.** Bindings are derived from the log, so a log missing a write
  still yields a stale binding (see `docs/assumptions.md` §6).

## 2026-10-07: next-experiment plan corrected

- The previous plan proposed cases with dropped producer events. Bindings are
  derived from the log, so deleting a write would silently bind the read to an
  older write and recreate the stale-write problem during binding construction.
  (Pointed out in review after PR #1.)
- The plan now requires complete, ordered logs. Missing evidence is created
  only by the views (budget, horizon, branch priority).
- Missing-log robustness moves to a later experiment that needs version IDs
  recorded at the source.
- The dataset is now 12 cases written as 6 matched benign/restricted pairs, by
  an author who has not inspected the selector. The pairs vary branching,
  overwrites, interleaving, and timing.
- The commit, budget, horizon, branch priority, gate, and input and label
  hashes are frozen before labels are opened. Each mode is run once, and every
  disagreement is inspected, including cases where a baseline wins.
