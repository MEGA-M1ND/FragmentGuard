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
