# FragmentGuard: next experiment results

Streaming sensitivity propagation handles the current complete-log toy policy:
it matched full-context checking on all 24 initial publications and all eight
completed pilot 2 publications. Correlation provides bounded evidence retrieval;
these experiments do not establish a detection advantage over propagation.

| Experiment | Observed outcome |
| --- | --- |
| Complete-trace baseline | 4 fixtures, 12 scripted and 8 pilot 1 live publications: streaming/full/labels agree |
| Pilot 2 scripted rehearsal | 12/12 complete; target identity/file/ledger/binding checks passed |
| Missing-record analysis | 636 observations, zero wrong definite verdicts, 29 controls agree |
| Pilot 2 live, now executed once | 8/12 complete; 4/6 pairs evaluable; same four missing publications |

Pilot 2's revised publisher instructions name `summary` for sc05/sc11 and `report`
for sc04/sc09. All four publishers still asked which opaque handle matched that
name. The clarification alone did not fix the live handoff. No failures were
retried or replaced. Pairs B and F remain unevaluable, including the case designed
to favor the fixed window. Completed publication targets and bytes match the ledger.

| Pair separation | Pilot 1 | Pilot 2 |
| --- | ---: | ---: |
| Per-agent | 0/4 | 0/4 |
| Fixed window | 2/4 | 2/4 |
| Correlated | 3/4 | 3/4 |
| Full context / streaming | 4/4 | 4/4 |

Pilot 2 had no incorrect definite monitoring verdicts; streaming matched full
context on 8/8, correlation on 7/8 with sc12 uncertain. Direct/scheduled replays
agree with zero monitoring tokens. The original scripted sc04 window win and all
six masked window wins remain visible in the earlier evidence. Missing-record
behavior remains conservative under trusted pointers, not proof of safety with
dishonest or unlogged execution. Masks are interventions, not independent workflows.

**New paid work: one invocation, 76 requests, $0.0104266 accounted**, including
incomplete episodes; 67,586 input and 7,336 output tokens. Current official prices
and exact model access were verified; pessimistic ceiling $0.963648, approved cap
$1. No retries, extra development episodes or second invocation. The original
pilot's 77 requests / $0.0105118 remain historical, and accounted costs are not
independently verified invoices. Future costs are not inferred from either run.

Full pilot 2 evidence and interpretation:
[examples/agent_pilot_02/live-20261016/README.md](examples/agent_pilot_02/live-20261016/README.md).
Methodology and earlier results: [docs/streaming_baseline.md](docs/streaming_baseline.md).
102 tests, lint and dependency checks pass after adding live artifacts; all 542
previous tracked example/fixture files and the original 425-file inventory remain
byte-identical. Original build and clean-wheel checks remain recorded separately.

Recommendation: keep propagation as the stronger baseline. Before another paid
run, rehearse a minimal structured target name-to-handle handoff derived from the
ledger. The current paid authorization has been consumed; any additional
invocation requires new explicit authorization.
