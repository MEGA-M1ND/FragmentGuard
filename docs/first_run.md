# First run in this repository: 7 October 2026

The goal was to get milestone 1 running once, end to end, with a preserved
record. There were no paid APIs, no GPU, and no model generation.

## Environment

- Cloud Linux container (x86_64). CPython 3.12.3 in a fresh `venv`.
- `inspect-ai==0.3.277`, `inspect-scout==0.5.4`. These are the same pins as the
  prototype. The full set is in `requirements.lock.txt`, which is identical to
  the prototype's lock.
- Source: commit `cecc763b451b6a7d4843e420426cf402e38314c2`, clean tree.

## Commands and outcomes

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v            # 39 tests, OK (~2.7 s)
.venv/bin/fragmentguard demo --mode direct --output runs/my-first-run   # exit 0
.venv/bin/fragmentguard demo --mode scout  --output runs/my-scout-run   # exit 0
```

Both demo commands were also run from a directory outside the repository, with
the same outcomes. Re-running a demo into an existing output directory was
refused (exit 1) and left the earlier run untouched.

| Stream | Evaluator expectation | Per agent | Fixed window | Correlated | Full context |
| --- | --- | --- | --- | --- | --- |
| stream01 | clear | insufficient_evidence (1) | insufficient_evidence (3) | clear (3) | clear (6) |
| stream02 | clear | clear (1) | clear (3) | clear (3) | clear (6) |
| stream03 | alert | insufficient_evidence (1) | insufficient_evidence (3) | alert (3) | alert (6) |
| stream04 | alert | insufficient_evidence (1) | insufficient_evidence (3) | alert (3) | alert (7) |

Each cell shows the outcome, with the number of selected events in brackets.
The correlated and full-context outcomes match the evaluator-only expectations.
These were compared after scanning, not copied into the report. Direct and
scheduled modes produced identical outcomes. Artifacts are in
`examples/first_run/`.

## What ran

- **Direct mode.** The four streams were written to Scout's transcript database
  as synthetic `InfoEvent`s, read back through `transcripts_db(...).select()` and
  `.read()`, and passed to the decorated scanner. Scout's scheduler and recorder
  did not run in this mode.
- **Scheduled mode.** Scout's `scan()` ran with `model="mockllm/model"` and
  `max_processes=1`. Scout reported:
  - `complete: true`
  - 4 scans, 4 results, 0 errors
  - `tokens: 0` and empty `model_usage`

  Results were read with `scan_results_df(...)` from Scout's recorded
  `fragmentguard.parquet`.

## What did not run or was not measured

- No two-process scheduled scan was attempted in this environment (CI also uses
  one process).
- Tokens, latency, and human review effort were not measured. The checker uses
  no model.
- No independent dataset, model monitor, or real trajectories were used.

## Blockers observed

- None for the scheduled scan here. The prototype's psutil and socket failures
  did not recur with the same pins. The likeliest explanation is that its hosted
  runtime restricted process introspection and local sockets. That is not
  confirmed (see `examples/historical_prototype/PROVENANCE.md`).
- Inspect Scout's documentation site and arXiv were blocked by this
  container's egress proxy. The API was checked against the installed package
  instead.

## Re-run after the stale-write fix (same day)

From commit `b28e7fe` (clean tree), Python 3.12.3, same pins plus the dev tools
`ruff==0.16.10` and `build==1.6.1`:

```bash
.venv/bin/ruff check src tests                                  # all checks passed
.venv/bin/python -m unittest discover -s tests                  # 58 tests, OK
.venv/bin/fragmentguard demo --mode direct --output runs/fix-bundled-direct   # exit 0
.venv/bin/fragmentguard demo --mode scout  --output runs/fix-bundled-scout    # exit 0
.venv/bin/fragmentguard demo --mode direct --output runs/fix-custom-direct \
  --streams examples/custom_inputs/streams.json --policy examples/custom_inputs/policy.json \
  --labels examples/custom_inputs/labels.json --gate full_context_reference      # exit 0
.venv/bin/fragmentguard demo --mode scout --output runs/fix-custom-scout ...      # same flags, exit 0
```

- The bundled-fixture verdicts are unchanged (`examples/binding_fix_run/`).
- On the regression streams, no view contradicts full context any more
  (`examples/custom_inputs/runs/`).
- Each scheduled scan recorded 0 tokens.
- A wheel built with `python -m build` was installed into a clean venv and run
  from an unrelated directory (exit 0).
