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

## Observed results

Canonical artifacts: `examples/evidence_retrieval/first-comparison/`. The final
runner reproduced the initial raw/evaluated rows and summary byte-for-byte;
its portable policy resolution requires the frozen policy hashes rather than
assuming the old machine's absolute paths. There were 673 separately tagged
observations and 6,730 evidence rows, with zero correctness violations. Streaming's
cached verdict matched the full-visible checker throughout.

| Checker budget | Complete: correlation / streaming+provenance | Masked only: correlation / streaming+provenance |
| --- | ---: | ---: |
| 1 | 1 / 1 of 37 | 31 / 31 of 607 |
| 2 | 3 / 5 of 37 | 51 / 53 of 607 |
| 3 | 27 / 30 of 37 | 152 / 155 of 607 |
| 4 | 35 / 36 of 37 | 154 / 155 of 607 |
| 8 | 37 / 37 of 37 | 155 / 155 of 607 |

Cells count sufficient raw evidence for a definite visible-reference verdict,
not attack accuracy. At budget 3 the additional complete-case proofs were scripted
sc04 and regression publications stream11/e04 and stream14/e04. Their known
restricted branch was shorter than the first public branch. The stronger baseline
used its cached restriction state to retrieve that proof within three records.
The masked observations add three analogous gains; no-deletion controls duplicate
complete cases and are reported separately in JSON. The post-hoc oracle found 18
missed available proofs across the original correlation budget rows and none for
the stronger baseline on these cases; this is not a general optimality result.

At budget 3 over the 37 complete publications, correlation dereferenced 124 payload
records versus 109 for streaming+provenance, and produced 22,225 versus 22,246
canonical checker-context bytes in total. The baseline additionally retained a
median 300 (maximum 484) canonical state bytes per prefix. Both used the common
archive, median 518 (maximum 901) canonical payload bytes, and shared bindings.
These declared encodings and partial operation counts do not establish an overall
speed, RAM, token or dollar advantage. State is built afresh per experimental
prefix, including repeated source prefixes; no amortized service cost is measured.

Conclusion: these cases establish no supporting-evidence advantage for the original
correlation selector over streaming sensitivity with provenance. The stronger
baseline supplies at least as many proofs here but pays for online state and
retained pointers. Bounded evidence remains a useful output requirement; an
information-cost advantage for correlation has not been demonstrated.

The reference cache copies parent references and identity headers that a production
implementation could share with its archive. Its serialized state size is not a
minimum memory requirement for propagation. The stronger baseline is itself a
provenance-retrieval system: this compares two concrete implementations/priorities,
not all possible correlation techniques.
