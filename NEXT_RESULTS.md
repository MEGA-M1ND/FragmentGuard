# FragmentGuard: next experiment results

The simple streaming sensitivity baseline matches full-context checking under
our complete-log toy policy. Correlation provides bounded evidence retrieval;
these results do not establish a detection advantage over sensitivity propagation.

| New offline check | Observed outcome |
| --- | --- |
| Original fixtures | Streaming/full-context/labels agree on 4/4 publications |
| Original scripted rehearsal | Agree on 12/12; streaming separates 6/6 pairs, correlation 3/6, window 2/6 |
| Eight completed pilot 1 live traces | Agree on 8/8; streaming separates 4/4 evaluable pairs, correlation 3/4, window 2/4 |
| Clarified pilot 2 scripted rehearsal | 12/12 complete; target names, file hashes, ledger and bindings verified; direct/Scout agree |
| Missing-record robustness | 636 unique observations; zero wrong clear/wrong alert; 29 controls agree; streaming equals all-visible checking |

Missing-record results are conservative behavior under trusted producer/version
pointers, not safety under dishonest or unlogged execution. Streaming/all-visible
checking retain 184 definite verdicts and become uncertain in 452 observations.
Masks are interventions on 29 publications, not independent workflows.

Baseline wins are retained: the fixed window alerts on scripted sc04 while
correlation is uncertain. Across the missing-record observations there are six
window wins (four scripted, two stale-write regression masks) and twelve streaming
wins over correlation; IDs and missing references are in
`examples/missing_evidence/first_analysis/results/baseline_wins.json`.

Historical pilot 1 remains 8/12 complete, with sc04/sc05/sc09/sc11 lacking a
publication. Its 77 requests and $0.0105118 accounted spend are historical evidence,
not new work, current pricing, or a verified invoice. No failures were replaced.
All 425 pre-existing example/fixture/pilot-input files retain their original bytes.

**Pilot 2 live is authorized for one invocation capped at $1, but has not started.** Only sc04/sc09 publisher instructions now name `report`,
and sc05/sc11 name `summary`; all other inputs/selection settings are preserved.
A scripted success does not demonstrate live instruction compliance.
The disabled proposal is one 12-episode invocation on
`anthropic/claude-haiku-5-5`, capped at $1. The $0.963648 pessimistic ceiling uses
historical prices; current prices could not be verified (proxy 403), and the
credential is unset. The provider package is installed. Review
`experiments/agent_pilot_02/review-packet.json` and its exact command sequence for the authorized invocation. See `authorization-status.json` beside it for the
remaining credential/pricing prerequisites. No live limits have been enabled.

Validation: 102 tests, Ruff, byte compilation, dependency consistency, sdist/wheel
builds, bundled/custom direct and scheduled Scout smoke checks, scripted dev01/dev02,
and clean-wheel direct/Scout/new experiment commands passed. Final source reproduces
the saved comparison and omission outputs byte-for-byte. Remote CI has not been
claimed; these are local cloud-machine results.

**This task: zero live requests; $0 accounted spend.**

Methodology, source commits, hashes, limitations and runnable commands:
[docs/streaming_baseline.md](docs/streaming_baseline.md).
Recommendation: keep sensitivity propagation as the stronger baseline; decide
to complete pricing/access preflight and execute the already authorized clarified live pilot.
