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
- 3: EXECUTED ONCE after pricing/access verification; 8/12 complete, 76 requests, $0.0104266 accounted, no retries. Evidence: `examples/agent_pilot_02/live-20261016`. Authorization consumed; no additional paid run permitted.
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

Stage 3 has now received the required separate user authorization for one invocation
capped at $1. It remains unstarted; historical-price ceiling
$0.963648. Current prices/access must be verified and the recomputed ceiling must
fit any approved cap before freezing or generation. Credential value belongs in
secure environment settings, never chat. No live limits were enabled.

## Authorized integration

The user subsequently requested merging all changes and authorized the proposed
one-invocation $1 live run. Both remote `main` and the existing default branch
`claude/bold-noether-ekiwpm` are ancestors of the tested successor. Integrate by
ordinary fast-forward pushes, preserving all commits and leaving the default-branch
setting unchanged. This does not claim that GitHub's unavailable PR API recorded
a particular PR state.

The required secret and network additions were saved as an environment draft:
`ANTHROPIC_API_KEY` for `api.anthropic.com`; custom allowed domains
`api.github.com`, `platform.claude.com`, `api.anthropic.com` (existing presets
preserved). Review/save and publish those changes in environment settings; enter
the credential securely there. Draft saving does not execute or publish changes.
No duplicate spending approval is required within the approved cap/model/scope.


## Live stage completed

After the user supplied the environment key, pricing returned HTTP 200 and the
exact model's GET succeeded. The one authorized invocation was frozen from
`f876ee4ec23e2636c31cfa55a3bd940713501e0f` and executed once. Result: 8/12 complete,
4/6 pairs evaluable, no incorrect definite monitoring verdicts; streaming/full
match 8/8. sc04/sc05/sc09/sc11 still asked which handle matched the named target.
All failures and their costs are retained. No retries or substitute episodes.

76 requests / 67,586 input / 7,336 output tokens / $0.0104266 accounted. Full
canonical evidence is in `examples/agent_pilot_02/live-20261016`; new free-analysis
config is `experiments/agent_pilot_02/live-comparison.json`. This supersedes the
earlier blocked/not-started status. No further spending is authorized.
