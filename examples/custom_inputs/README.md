# Custom-input example: stale-write regression and controls

Evaluator-only labels are in `labels.json`. The case author also wrote the
checker, so these are regression cases, not a benchmark.

| Stream | Case | Label |
| --- | --- | --- |
| `stream11` | e01 public→scratch, e02 scratch→snapshot, e03 restricted→scratch, e04 publishes [snapshot, scratch] publicly | alert |
| `stream12` | the same shape, with e03 rewriting scratch from the public root (benign overwrite control) | clear |
| `stream13` | a stale restricted write by agent a, a public overwrite by agent b, then agent a publishes | clear |
| `stream14` | `stream11` followed by a public overwrite and a second publication (per-publication labels) | e04 alert, e06 clear |

The runs in `runs/` were produced on 7 October 2026 from commit `b28e7fe` with a
clean tree, using the commands in `docs/custom_inputs.md`
(`--budget 3 --horizon 100 --gate full_context_reference`). Both modes gave
identical outcomes, and the gate matched.

| Stream / publication | Per agent | Fixed window | Correlated | Full context |
| --- | --- | --- | --- | --- |
| stream11 / e04 | insufficient_evidence | alert | insufficient_evidence | alert |
| stream12 / e04 | insufficient_evidence | insufficient_evidence | insufficient_evidence | clear |
| stream13 / e03 | insufficient_evidence | clear | clear | clear |
| stream14 / e04 | insufficient_evidence | alert | insufficient_evidence | alert |
| stream14 / e06 | insufficient_evidence | clear | clear | clear |

Before the fix (checked by running commit `4461cf9` on these streams), the
correlated view returned `clear` for `stream11` and `stream14/e04` (missed
alerts) and for `stream12` (a clear resting on a stale write). The per-agent view
returned `alert` for `stream13` (a false alert). No view now returns a verdict
that contradicts full context.

At budget 3, correlation does worse here than the fixed window. Depth-first
branch priority spends the budget on the `snapshot` branch, so `scratch`'s true
producer is left out. This holds for these hand-written cases only.

| Run | `manifest.json` SHA-256 |
| --- | --- |
| `runs/direct/` | `54e630e3ea18cf7df521e3fc2110495a0fedc8868bcb1f080b64efb204163404` |
| `runs/scout/` | `30b20d6370d2fc4741d0f98fe81993ade3676afb615f11e56ee1e95e79197931` |
