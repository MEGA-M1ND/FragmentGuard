# Sensitivity propagation and missing-evidence experiments

## Complete traces

The independent `fragmentguard.streaming.StreamingSensitivity` API receives one
validated event and its exact producer references at a time. Each output version
stores a restriction flag and unresolved references. Public publication alerts
if any known branch is restricted, remains uncertain if only unresolved ancestry
remains, and otherwise clears. Internal publication clears under the existing
policy. Outputs are keyed by producer ID and resource; old versions are retained.
It neither walks ancestry backwards nor calls the existing checker.

For compatibility with the seven-field historical schema, the experiment derives
producer bindings in one shared complete-log pass. The manifest reports events
and input references processed by that pass. This is not an end-to-end streaming
recorder. The existing normalized pilot versions are immutable and were checked
against the execution ledger when originally recorded.

```bash
python -m fragmentguard.experiments compare --config /workspace/FragmentGuard/experiments/streaming_baseline/comparison.json --output NEW_DIRECTORY
```

Run from any directory with the editable package installed. Outputs are additive
schema v1: raw five-method `outputs.json` is written before opening evaluator
labels/pairs, then `evaluated.json`, `summary.json`, and `manifest.json`. The
manifest fingerprints source, inputs, packages and fixed selection settings
(budget 3, horizon 100, depth-first input order). Ledger labels are used only
post hoc. A nonzero exit exposes streaming/full-context or full-context/label
mismatches. Incomplete live episodes remain in execution coverage, without
fabricated monitoring verdicts. Scripted, synthetic and live datasets are
reported separately.

The baseline sees all arriving events and retains version states and identity
headers. Bounded methods receive selected records at the checker. Their budget
of three is not three total records read or equal memory/compute/token cost.
Raw rows include checker event counts, selection records examined, cumulative
streaming input updates, state writes, retained versions and unresolved entries.
These are operation/storage counts, not timing measurements. No speedup is claimed.

## Stage 1 observations

At source `8bcd0e0` (see manifest for the full commit and package hash), streaming
matched full context and evaluator labels on all 24 publications: four synthetic,
twelve scripted and eight completed historical live episodes. There were zero
mismatches. Correct verdict counts for per-agent/window/correlation/full/streaming
were respectively 1/1/4/4/4 (fixtures), 0/5/7/12/12 (scripted), and 0/4/7/8/8 (live).
The live execution coverage remains 8/12; sc04/sc05/sc09/sc11 had no publication.

This toy policy is implementable with simple forward sensitivity propagation.
Correlation adds bounded evidence retrieval/explanations, not a demonstrated
verdict advantage over the streaming baseline under complete, exact logs.

## Pilot 2 publication clarification

`experiments/agent_pilot_02/scenario_diff.json` records hashes and field-level
changes. sc05/sc11 (pair B) now request `summary`; sc04/sc09 (pair F) request
`report`, in both cases explicitly created by this episode's processor.
Processor instructions and the existing plans independently identify these names.
All other fields, lineage, ordering, backgrounds and scenario bytes are preserved.
Sources, catalog, plans and evaluator pairs are shared unchanged; selection stays
3/100/depth-first. No executor change is needed: `publish_resource.handle` accepts
an artifact name, resolved through the episode-local version ledger.

The scripted rehearsal verifies execution and target resolution, not live model
compliance. Paid generation is pending separate explicit authorization. The
proposed limits keep `live_enabled: false`. Their $1 cap and $0.963648 ceiling
use **historical** price assumptions, not current verified prices. The official
pricing page request was blocked by proxy HTTP 403 during this task; refresh it
before requesting a live invocation. `ANTHROPIC_API_KEY` was unset. Never put a
credential value into this packet or chat.

Pilot 2 rehearsal: 12/12 complete, 6/6 pairs evaluable. Direct and real scheduled
Scout replays agree. All 12 published versions match the expected target name,
were created by the processor, resolved by display name, match actual published
bytes, and pass file/ledger and normalization binding checks. Verification:

```bash
python experiments/agent_pilot_02/verify_rehearsal.py --execution examples/agent_pilot_02/rehearsal-run --config experiments/agent_pilot_02/pilot_config.json --output NEW_VERIFICATION.json
python -m fragmentguard.experiments compare --config experiments/agent_pilot_02/comparison.json --output NEW_COMPARISON
```

Raw rehearsal evidence is in `examples/agent_pilot_02/`; its freeze records the
source commit. Streaming/full-context separate all six scripted pairs; correlation
separates three, window two, per-agent zero. On sc04, window alerts while
correlation is uncertain (the late restricted branch loses to depth-first budget
use). Neither separates pair F because the allowed twin is also uncertain under
the bounded views. Both B twins exceed the lineage budget. These limitations
remain intact. No live pilot 2 trace has been generated.

The exact future command sequence is
`experiments/agent_pilot_02/live-review-commands.sh`. It requires a separately
authorized limits file and a fresh run root; it never enables the proposed file.
Use the currently documented CLI flags; replay does not supply labels, comparison
and analysis join them afterward. Refresh pricing, install the optional provider
package, verify model availability via a no-generation endpoint if available,
and inspect credential presence before a future authorized invocation.

## Missing-evidence contract and preregistered interventions

`fragmentguard.observation` is a separate schema v1 API. Complete-input parsing
and latest-producer binding are unchanged. Freeze a complete valid stream before
hiding records. The mask removes event payloads AND hidden consumers' input edges.
Only visible inputs' frozen pointers and trusted identity headers (workspace,
event ID, tick, produced resource/version IDs) survive. No hidden input contents,
agent, operation, ancestry or sensitivity labels are passed to any method.
Headers permit causal/workspace/output validation even when a payload is absent;
this is a stronger logging assumption than merely retaining raw seven-field logs.

Malformed/cross-workspace/future/non-producing pointers, missing pointer metadata,
header mismatches and catalog-root writes raise integrity errors. An earlier
producer whose declared identity exists but whose payload is unavailable yields
unresolved ancestry. References to old versions are legal. Catalog names never
substitute for missing produced versions. Correlation skips absent records without
falling back to older writes; the checker retains the unresolved pointer.
Streaming starts from empty state for EVERY observation, and preserves restriction
when another branch is unknown.

Two separate commands freeze the intervention file/hash before any scoring:

```bash
python -m fragmentguard.experiments freeze-masks --config /workspace/FragmentGuard/experiments/missing_evidence/comparison.json --output NEW_SPEC
python -m fragmentguard.experiments missing --spec NEW_SPEC --output NEW_RESULTS
```

For each target publication, use its causal prefix only, always retain the target,
and enumerate all subsets of earlier payloads (at most ten earlier records; larger
logs fail rather than silently sampling). Single non-publication and direct-producer
omissions and the no-deletion control are identified as overlapping categories.
Equivalent masks are deduplicated. Ticks/order/IDs remain unchanged. This includes
the original fixtures, scripted rehearsal, eight completed live traces, and the
existing stale-write custom regressions. New pilot 2 rehearsal traces are structurally
the same and are not counted again as independent cases.

The scoring command verifies frozen source/policy and observation hashes, writes
raw outputs first, then loads the full unmasked histories, evaluator labels and
pair membership for analysis. `full_context_reference` in masked rows means all
VISIBLE records; the separate `reference` field is the unmasked verdict. Controls
must reproduce the existing complete pipeline's statuses and evidence IDs for
all four views, and streaming must match the unmasked full reference. Opposite
definite verdicts are errors and make the command fail. Per-workflow, pair and
category counts retain uncertainty separately. These are post-hoc interventions
on existing cases under trustworthy identity/pointer metadata, not held-out data
or evidence of safety with dishonest pointers or unlogged actions.

## Missing-evidence observations

Source `103c0cc` produced the frozen specification and initial scores. New
experiment manifests use `experiment-manifest.json` to avoid confusing the
historical demo-manifest schema; prior manifest contents and hashes are retained.
The specification hash was saved before scoring. An additive post-hoc
`baseline_wins.json` enumerates every fixed-window or streaming definite verdict
where correlation is uncertain, including IDs, masks and unresolved pointers.

There were **636 unique observations** of 29 target publications (3,180 method
outputs), with 29 no-deletion controls. All controls reproduce the original four
views; streaming matches the unmasked full reference. No wrong clear, wrong alert,
reference/label disagreement or control violation occurred. Streaming matched the
all-visible checker in all 636 observations. Definite/uncertain counts:

| Dataset | Observations | Per-agent | Window | Correlation | All-visible / streaming |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original synthetic fixtures | 160 | 32 / 128 | 36 / 124 | 64 / 96 | 64 / 96 |
| Original scripted rehearsal | 248 | 0 / 248 | 17 / 231 | 44 / 204 | 52 / 196 |
| Eight completed live pilot 1 traces | 168 | 0 / 168 | 9 / 159 | 40 / 128 | 41 / 127 |
| Stale-write regression inputs | 60 | 0 / 60 | 26 / 34 | 24 / 36 | 27 / 33 |

These counts include no-deletion controls and overlapping intervention categories;
observations are interventions on the same traces, not independent trials. The
32 per-agent definite results in the fixture dataset include internal publications,
which are allowed even with unresolved ancestry. Streaming/all-visible retain 184
definite verdicts, while 452 become uncertain. The machine-readable summary groups
by workflow, pair and category; `became_uncertain` identifies each mask and missing
reference for formerly definite public publications. There is no evidence here of
robustness to corrupted metadata. Sensitivity state retained from before a deletion
was deliberately excluded.
