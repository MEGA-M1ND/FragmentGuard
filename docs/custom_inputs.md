# Running custom streams, policy, configuration, and labels

Up to commit `e34344e`, only `fragmentguard replay` accepted custom inputs, and
`fragmentguard demo` always ran the four bundled fixtures. `demo` now accepts the
same custom inputs in **both** execution modes.

| Input | `replay` (core only) | `demo --mode direct` | `demo --mode scout` |
| --- | --- | --- | --- |
| Streams | `--streams F` | `--streams F` | `--streams F` |
| Trusted policy | `--policy F` | `--policy F` | `--policy F` |
| Budget / horizon | `--budget N --horizon N` | same | same |
| Evaluator labels | not accepted (label-free by design) | `--labels F`, read after scanning | same |
| Label gate (exit code) | n/a | `--gate methods` or `none` | same |

Without `--streams`, `demo` uses the bundled fixtures and their bundled labels.
With `--streams`, no labels are used unless you pass `--labels`. The labels file
is located before the run, so a typo stops it early. Its contents are read only
after scanner results exist.

## Worked example

`examples/custom_inputs/` contains:

- the stale-write regression stream (`stream11`);
- its benign overwrite control (`stream12`);
- the stale-restricted-write control (`stream13`);
- a stream with two publications (`stream14`), whose labels are given per
  publication.

```bash
fragmentguard replay --streams examples/custom_inputs/streams.json \
  --policy examples/custom_inputs/policy.json            # authoring check, prints JSON

fragmentguard demo --mode direct --output runs/custom-direct \
  --streams examples/custom_inputs/streams.json \
  --policy examples/custom_inputs/policy.json \
  --labels examples/custom_inputs/labels.json \
  --budget 3 --horizon 100 --gate full_context_reference

fragmentguard demo --mode scout --output runs/custom-scout \
  --streams examples/custom_inputs/streams.json \
  --policy examples/custom_inputs/policy.json \
  --labels examples/custom_inputs/labels.json \
  --budget 3 --horizon 100 --gate full_context_reference
```

Reviewed outputs of both commands are in `examples/custom_inputs/runs/`.

## File formats

- **Streams:** a JSON list of `{"stream_id": "streamNN", "events": [...]}`.
  - Events use exactly the seven fields in `README.md`.
  - Stream IDs must be neutral (`stream` followed by 2–6 digits).
  - No other keys are allowed anywhere, so labels cannot ride along with the data.
- **Policy:** `{"resource": "public" | "restricted", ...}`. These resources are
  immutable catalog roots: any event that writes one is rejected.
- **Labels (evaluator-only):**
  ```json
  {"expected": {"stream11": "alert", "stream14": {"e04": "alert", "e06": "clear"}}}
  ```
  - A bare verdict applies to a stream that has exactly one publication.
  - A mapping gives one verdict per publication ID, and must cover exactly that
    stream's publications.
  - Mismatched streams or publications are listed under `evaluation.problems`,
    and the gate fails.
- **Configuration:**
  - `--budget` is the maximum number of selected events per bounded view.
  - `--horizon` is the correlation look-back in ticks.
  - Both are recorded in `report.json` and in `manifest.json` with a config hash.

## How results are judged

- Every method is compared with the labels and reported in
  `evaluation.per_method`, with three counts kept separate:
  - `match`
  - `insufficient_evidence`
  - `contradicts_label`
- Only the `--gate` methods decide the exit code. The default gate is
  `correlated,full_context_reference`, which suits the bundled fixtures.
- For other data, choose the gate deliberately:
  - `full_context_reference` checks the labels and checker agree on complete
    evidence.
  - Gating a bounded view treats its `insufficient_evidence` as a failure.
  - `none` reports agreement without gating.

In the example, correlation at budget 3 returns `insufficient_evidence` on
`stream11`, `stream12` and `stream14/e04`. Depth-first branch priority spends the
budget on the `snapshot` branch, and the true producer of `scratch` is left
unselected. The fixed window happens to contain that producer for `stream11` and
`stream14/e04`, so it returns `alert` there. This describes three hand-written
cases. It is not a rate.

## What stays fixed

- The label boundary: scanner input is streams + policy + config only.
- The checker and bindings are identical in all modes.
- The output directory must be new.
- The manifest hashes every input file that was actually used (`inputs.*.sha256`).
