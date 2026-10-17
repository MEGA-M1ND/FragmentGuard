# Review of the existing missing-evidence experiment

This review preserves all original observations and reports. It verifies the
frozen intervention contract, independently counts the existing results and
reproduces the scoring. It introduces no new workflows, masks or model calls.

## What the experiment actually removes

The 636 observations cover 29 target publications. They include 29 no-deletion
controls and 607 distinct observations with at least one earlier payload hidden.
Each source publication has every subset of earlier records represented once.
The target publication remains visible, as do order, ticks and version identities.

Producer pointers are frozen from the complete trace **before** masking. A masked
observation retains the trusted catalog, visible records and their exact producer
references, plus identity headers giving hidden event IDs, ticks and produced
version identities. It removes hidden input edges, contents, agents and operations.
Streaming state starts empty for each observation; it does not retain sensitivity
labels from the unmasked history. Missing referenced payloads stay unresolved.

The identity headers and producer references are a strong assumption. This tests
unavailable payloads/history with trustworthy metadata, not an unlogged write,
missing producer metadata, dishonest pointers or broken identity. Catalog-root
writes and malformed/cross-workspace/noncausal metadata are rejected as integrity
failures. They must not be interpreted as safe publications.

## Independent checks performed

For every frozen observation, reconstruct its complete source prefix, derive its
producer bindings before deletion, apply the recorded mask and compare the whole
resulting observation with the saved payload. All matched. Check that masks are
unique, exhaustive, and retain the target: all passed. Re-run the scoring from the
frozen specification: raw outputs, evaluator-joined rows, summary and baseline-win
list all reproduce byte-for-byte. Inspect the scoring boundary: original histories,
labels and pair definitions are joined after raw method output is saved. No hidden
ancestry or full-history sensitivity state enters the method inputs.

The review record is
`examples/handoff_metadata/offline-check-20261017/missing-evidence-review.json`.
Reproduce free scoring with:

```bash
python -m fragmentguard.experiments missing --spec /workspace/FragmentGuard/examples/missing_evidence/first_analysis/specification --output NEW_DIRECTORY
```

## Counts with controls separated

Cells show **definite / uncertain**. Every definite verdict below agrees with
the unmasked reference; no wrong clear or wrong alert occurred.

| Method | 29 no-deletion controls | 607 masked observations | All 636 |
| --- | ---: | ---: | ---: |
| Per-agent | 1 / 28 | 31 / 576 | 32 / 604 |
| Recent-event window | 14 / 15 | 74 / 533 | 88 / 548 |
| Correlation | 20 / 9 | 152 / 455 | 172 / 464 |
| All visible history | 29 / 0 | 155 / 452 | 184 / 452 |
| Streaming sensitivity | 29 / 0 | 155 / 452 | 184 / 452 |

Streaming matched all-visible checking in every observation. Correlation retained
more definite decisions than the window in these cases, but still showed no
advantage over sensitivity propagation. The three additional all-visible/streaming
decisions among actual deletions should not be conflated with the nine bounded-view
gaps in the controls. The per-agent definite fixture outcomes include internal
publications, which the policy permits even with unresolved ancestry; they are not
evidence that per-agent context recovered missing public ancestry.

The six window wins over correlation in the original result set include **three
controls and three masked observations**, not six deletion-only wins:

| Observation | Source / stream | Hidden event IDs |
| --- | --- | --- |
| obs00236 | Scripted / stream04 | none (control) |
| obs00237 | Scripted / stream04 | e001 |
| obs00238 | Scripted / stream04 | e002 |
| obs00242 | Scripted / stream04 | e001, e002 |
| obs00576 | Stale-write regression / stream11 | none (control) |
| obs00596 | Stale-write regression / stream14 | none (control) |

## What follows

The results support conservative uncertainty under the trusted-pointer contract.
They do not establish real-world safety, general attack-detection accuracy or
robustness to unlogged execution. These are interventions on the same self-authored
traces; category memberships overlap and the 607 masks are not independent trials.
No significance, speedup or equal-compute claim follows from their counts.

The information costs differ: streaming receives the full arriving visible history
and retains version states; correlation builds an index and retrieves a bounded
set for checking. A three-event checker budget is not three total events read or
an equal memory budget. Correlation's supported contribution remains bounded
supporting evidence, not improved verdicts relative to streaming in this experiment.
Before broadening the observation claim, specify which recorder identities and
pointers would remain trustworthy. Future work should assess evidence retrieval
and explanation quality under that explicit contract, while retaining propagation
as the stronger verdict baseline. No additional paid run is needed for this review.
