# Evidence retrieval with streaming provenance

This new offline experiment follows PR #4. It does not regenerate pilot 1, pilot 2
or the original masked observations, change the historical selector or claim an
independent replication. The existing cases are known and were used during design.

Question: under a bounded checker context, does original resource correlation
supply supporting records more effectively than sensitivity propagation with
stored provenance? A correct cached flag alone is not counted as raw supporting
evidence. Both outputs are reported separately.

## Protocol fixed before this comparison run

Use all 37 existing complete publications: original fixtures, original scripted
rehearsal, both completed live-pilot datasets, and stale-write regression inputs.
Also reuse all 636 frozen partial observations, separating the 29 no-deletion
controls from the 607 actual masked observations. Groups overlap; do not treat
these as independent samples or combine denominators into general accuracy.

The configuration is `experiments/evidence_retrieval/protocol.json`. Checker event
budgets are 1, 2, 3, 4 and 8, with a fixed tick horizon of 100. This is a new budget
comparison, not a change to pilot 1/2's fixed three-event protocol. Both selectors
receive the same visible archive, policy and exact producer references. Every
partial observation starts with empty streaming state; no unmasked sensitivity
state or hidden input edges are supplied.

Original correlation remains depth-first in declared input order. The stronger
baseline updates the existing independent sensitivity state as records arrive,
stores ordered producer pointers, and retrieves depth-first with known-restricted
parents first, retaining input order within a priority. No evaluator labels,
precomputed root ancestry, subset oracle or full-context checker supplies its
verdict or retrieval choices. Exact producer/resource keys retain old versions.
Missing producer payloads stay unresolved, including replacement-name cases.

Both returned views go through the same checker with only their selected records,
selected bindings and trusted catalog. The record budget includes the publication.
Raw method outputs are written before full-visible reference checks, complete-case
evaluator labels and a tiny exhaustive minimum-support oracle. That post-hoc oracle
finds the smallest admissible raw view supporting a definite visible-reference
verdict. It identifies support missed by a selector versus support impossible
under its budget/horizon; it never guides retrieval. No oracle is calculated for
an uncertain reference verdict. The oracle is capped at ten earlier records.

## Costs and limits

Both methods rely on the same full visible payload archive and frozen bindings;
these are not free. Raw rows report archive event count, canonical payload bytes,
binding edges and complete-prefix compatibility-binding preprocessing. Partial
bindings were frozen earlier in the original specification; a zero new binding
pass does not mean their original construction was free.

Correlation reports query-time history-index entries built and payload records
examined. Streaming reports online event/input updates, retained version states,
parent edges, identity headers, unresolved entries and canonical state bytes, plus
query payload dereferences, parent edges examined and sensitivity/catalog lookups.
Streaming's index/pointers are maintained online rather than rebuilt at publication.
Cumulative state/update counts repeat across budget rows; do not sum them as new
work. These counters are not complete CPU-instruction counts.

Checker context bytes canonically serialize selected payloads, selected input
bindings and the catalog. Canonical storage/context bytes are declared logical
representations, not resident RAM, model-token counts, measured latency or human
review quality. Equal record budgets do not imply equal bytes, memory or compute.
No timing or speedup claim is made.

```bash
python -m fragmentguard.experiments.retrieval --config /workspace/FragmentGuard/experiments/evidence_retrieval/protocol.json --output NEW_DIRECTORY
```

The protocol and input hashes are saved before scoring. The output has raw and
evaluator-joined rows, counts by source/group/budget, every correctness violation,
every missed available proof and an artifact manifest. Any wrong definite verdict,
cached/full-visible disagreement or complete-case label mismatch fails the run.
