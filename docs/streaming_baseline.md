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
