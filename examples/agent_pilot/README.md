# Agent pilot artifacts

**All runs here except `live-dev01/`, `live-dev02/` and `live-pilot-*` used
the scripted backend.** Hand-written plans drove the real tool executor and recorder; no
model chose any action. These runs check the engineering. They are not model
evidence. See `docs/agent_pilot.md`.

**`live-dev01/` and `live-dev02/` are the two live development episodes**, run
once each on 12 October 2026 with `anthropic/claude-haiku-5-5` from code commit
`c81ddad` (only `live_enabled` changed in the two dev limits files). They were
copied unchanged from `runs/agent-pilot/`. They are development runs, not pilot
evidence. Both completed; $0.0012641 was accounted in total.

**`live-pilot-*` is the live twelve-scenario pilot (agent-pilot-01)**, run
once on 12 October 2026 with `anthropic/claude-haiku-5-5` from clean code
commit `25595eb`, under the reviewer's $1.00 authorization. 8 of 12 episodes
completed; $0.0105118 was accounted. It was copied unchanged from
`runs/agent-pilot/live-pilot/`.

The scripted runs were produced on 12 October 2026 from clean code commit
`08410f65a81aced5a2e8c67dbf78b65575571aa4` (package fingerprint
`5a9dccbf9d941d907b5133a90c46ca437243564c473415bab4e061085fe1ef51`) under
`runs/agent-pilot/`, then copied here unchanged.

| Directory | What |
| --- | --- |
| `live-dev01/`, `live-dev02/` | Live development episodes on Claude Haiku 5.5, plus `inspection.json` |
| `live-dev-commands.txt` | Their preflights (refused, then passing) and the two commands' output, verbatim |
| `live-preflight.txt` | A live freeze and a live `agent-run` with the committed template: both refused (no authorization) |
| `live-pilot.limits.authorized.json` | The authorized limits copy used by the freeze and run (SHA-256 `fc623835…`); only `live_enabled` differs from `experiments/agent_pilot/live/pilot.limits.json` |
| `live-pilot-commands.txt` | Preflight, freeze, run, replay and analysis commands with their output, verbatim |
| `live-pilot-freeze/freeze.json` | The live freeze record (SHA-256 `259f0580…`) |
| `live-pilot-run/` | 12 live episodes (4 incomplete, kept as recorded), `dataset/`, `evaluator/`, `run_summary.json` with the budget ledger |
| `live-pilot-direct/`, `live-pilot-scout/` | Label-free replays (`--gate none`) in direct and scheduled mode |
| `live-pilot-analysis/` | `pilot_report.md` / `pilot_report.json` |
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
