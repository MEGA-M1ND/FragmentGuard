# Agent pilot artifacts (scripted only)

**Every run here used the scripted backend.** Hand-written plans drove the real
tool executor and recorder; no model chose any action. These runs check the
engineering. They are not model evidence. See `docs/agent_pilot.md`.

They were produced on 12 October 2026 from clean code commit
`08410f65a81aced5a2e8c67dbf78b65575571aa4` (package fingerprint
`5a9dccbf9d941d907b5133a90c46ca437243564c473415bab4e061085fe1ef51`) under
`runs/agent-pilot/`, then copied here unchanged.

| Directory | What |
| --- | --- |
| `live-preflight.txt` | A live freeze and a live `agent-run` with the committed template: both refused (no authorization) |
| `scripted-dev01/`, `scripted-dev02/` | The two development episodes, plus `inspection.json` |
| `scripted-rehearsal-freeze/freeze.json` | The freeze record (SHA-256 `509c6a14…19226`) |
| `scripted-rehearsal-run/` | 12 episodes in the frozen order, `dataset/` (scanner input), `evaluator/` (ledger labels and evidence trails), `run_summary.json` |
| `scripted-rehearsal-direct/`, `scripted-rehearsal-scout/` | Label-free replays (`--gate none`) in direct and scheduled mode |
| `scripted-rehearsal-analysis/` | `pilot_report.md` / `pilot_report.json` (post-hoc join of labels and pairs) |

`tests/test_preservation.py` verifies the artifact hashes in both replay
manifests. Paths recorded inside the artifacts (for example
`runs/agent-pilot/...`) are the relative paths at run time.

An earlier, identical-outcome rehearsal from commit `8ce9a4a` is kept locally
under `runs/agent-pilot-attempt1-8ce9a4a/` and is not committed. It was
superseded when the `output_limit` agent outcome was added (see
`docs/dev_log.md`).
