# Next experiments progress

Starting commit: `4da34d538c60c8ed083b45b536d9acd48be7a339`.
Successor branch: `experiment/streaming-and-missing-evidence`, based on the live milestone.
`main` (`67f0453`) does not contain this head. PR #3 API lookup returned Forbidden;
Git read access works. Do not modify or merge #3.

Baseline: Python 3.12.14; locked dependencies installed, editable dev package;
85 tests passed, Ruff passed, sdist/wheel built. Direct/Scout smoke results are
recorded in the final validation record. Writable XDG directories are needed.
Historical preservation inventory: `experiments/streaming_baseline/historical-sha256.json`.

Stages:
- 0: starting state and baseline recorded.
- 1: complete; 24/24 streaming/full-context/label agreement. Artifacts: `examples/streaming_baseline/first_comparison/results`.
- 2: versioned publication clarification and offline rehearsal pending.
- 3: paid generation unauthorized; prepare review packet only.
- 4: frozen-pointer missing-evidence experiment pending.
- 5: final checks, results, and reviewable delivery pending.

Methodology and commands will live in `docs/streaming_baseline.md`.
No paid model calls are authorized by the implementation brief.
