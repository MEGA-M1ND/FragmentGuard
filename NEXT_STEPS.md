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
- 2: complete; four symmetric publisher clarifications, 12/12 scripted rehearsal, target/file/binding verification and direct/Scout agreement. Evidence: `examples/agent_pilot_02/`.
- 3: PENDING, not authorized. Proposed limits disabled; exact command packet prepared. Official pricing access blocked (proxy 403); credential unset, optional provider package absent.
- 4: complete; 636 unique observations, no wrong definite verdict/control mismatch; streaming equals all-visible checking. Artifacts: `examples/missing_evidence/first_analysis`.
- 5: complete locally and pushed for review; automatic PR creation blocked by GitHub API Forbidden. Summary: `NEXT_RESULTS.md`; method: `docs/streaming_baseline.md`; paid-run packet: `experiments/agent_pilot_02/review-packet.json`.

Methodology and commands will live in `docs/streaming_baseline.md`.
No paid model calls are authorized by the implementation brief.

Final validation: 102 tests passed after optional anthropic 1.13.0 installation, all locked versions unchanged. Direct/Scout, wheel, packaged experiment commands and exact output reproduction passed. All 425 historical file hashes preserved. This task: zero live calls, $0 accounted spend.

## Delivery

Pushed branch: `experiment/streaming-and-missing-evidence`.
PR creation was attempted with base `claude/bold-noether-ekiwpm` and failed:
`Post https://api.github.com/graphql: Forbidden`. This is an API/proxy restriction,
not an automatic approval-review rejection. Git push succeeded; no PR or merge is
claimed. PR #3 was not changed. Draft description:
`experiments/streaming_baseline/successor-pr.md`.

When GitHub API access is available, from this checkout run:

```bash
gh pr create --repo MEGA-M1ND/FragmentGuard --base claude/bold-noether-ekiwpm --head experiment/streaming-and-missing-evidence --title 'Compare streaming sensitivity and missing evidence; prepare pilot 2' --body-file experiments/streaming_baseline/successor-pr.md
```

Manual stacked comparison:
https://github.com/MEGA-M1ND/FragmentGuard/compare/claude/bold-noether-ekiwpm...experiment/streaming-and-missing-evidence?expand=1

Stage 3 remains pending, not silently dropped: the brief requires a new explicit
spending authorization. Proposed one-invocation cap $1; historical-price ceiling
$0.963648. Current prices/access must be verified and the recomputed ceiling must
fit any approved cap before freezing or generation. Credential value belongs in
secure environment settings, never chat. No live limits were enabled.
