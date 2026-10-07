# First run: reviewed example artifacts

These two runs were produced on 7 October 2026 from commit
`cecc763b451b6a7d4843e420426cf402e38314c2` with a clean tree
(`git_dirty: false`). The commands were the documented ones, run from the
repository root:

```bash
fragmentguard demo --mode direct --output runs/my-first-run   # copied to direct/
fragmentguard demo --mode scout  --output runs/my-scout-run   # copied to scout/
```

Each run was copied here unchanged. Every file listed in each `manifest.json`
still matches its recorded SHA-256 hash.

| Run | Path completed | Model generation | `manifest.json` SHA-256 |
| --- | --- | --- | --- |
| `direct/` | Scout database round trip, then a direct scanner call (scheduler skipped) | none: no model was created (design guarantee, not instrumented) | `69ec7a85cd163e438c97634832a8bec9e637ad2e735e1c915bba7908d5db980b` |
| `scout/` | Scout scheduled scan with `mockllm/model`, recorded by Scout | none: Scout's summary records 0 tokens and empty `model_usage` (measured) | `3250f0cd84b2217aa113df5df67f73d303df5c45a4ad157808afa736a1d87d6d` |

Fixture fingerprints (also in each manifest):

- `streams.json` `d85b3e34…6ac2520`
- `policy.json` `882c757a…0f34eb`
- `ground_truth.json` `0837ca67…5429e2` (evaluator-only)

Config hash for budget 3, horizon 100: `1379a9f2…49bf4`.

Both modes produced identical scanner outcomes:

| Stream | Expected | Per agent | Fixed window | Correlated | Full context |
| --- | --- | --- | --- | --- | --- |
| stream01 | clear | insufficient_evidence | insufficient_evidence | clear | clear |
| stream02 | clear | clear | clear | clear | clear |
| stream03 | alert | insufficient_evidence | insufficient_evidence | alert | alert |
| stream04 | alert | insufficient_evidence | insufficient_evidence | alert | alert |

Each `report.md` has the evidence IDs and selected/examined counts.

These outcomes come from four hand-designed cases that were written alongside
the checker. They show that the wiring works and that missing evidence stays
missing. They are not detection rates.

Hashes establish file identity, not authenticity. Scout's own files under
`scout/scans/` record the transcripts location as `runs/my-scout-run/transcripts`:
the relative path at run time, before the run was copied here.
