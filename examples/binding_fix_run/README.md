# Bundled fixtures after the binding fix

These runs were produced on 7 October 2026 from commit `b28e7fe` with a clean
tree. That commit includes the stale-write fix (`e34344e`). The commands were
run from the repository root, and each run was copied here unchanged:

```bash
fragmentguard demo --mode direct --output runs/fix-bundled-direct   # -> direct/
fragmentguard demo --mode scout  --output runs/fix-bundled-scout    # -> scout/
```

| Run | Path completed | Model generation | `manifest.json` SHA-256 |
| --- | --- | --- | --- |
| `direct/` | Scout database round trip, then a direct scanner call | none: no model was created (design, not instrumented) | `7252149ec627c360ebc70a67fcc282cccc7488c2b47dbd73b88f58fe3a4ffa67` |
| `scout/` | Scout scheduled scan with `mockllm/model` | none: Scout recorded 0 tokens and empty `model_usage` (measured) | `3a167a0316d46623e1920de1451ea6d125ba53e72a3e4cf0149a54e996c22eae` |

The outcomes are identical to the pre-fix runs in `../first_run/`. The binding
fix does not change any bundled-fixture verdict, because none of the four
fixtures overwrites a resource after it has been read. What changed:

- each result now lists `unresolved_inputs`, for example `summary<-e03` for the
  per-agent and fixed-window views;
- `records_examined` for the correlated view is now the number of records the
  selector dereferenced (3 per publication).

The stale-write regression itself is exercised in `../custom_inputs/runs/`.
`tests/test_preservation.py` verifies every artifact hash in these manifests.
