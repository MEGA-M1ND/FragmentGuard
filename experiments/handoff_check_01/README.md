# Four-case successor handoff check: ready for capped review

PR #4's ledger-derived mapping changes what agents receive. This is a new,
diagnostic executor-protocol check, not a repeat or replacement of pilot 2.
Run only sc11/sc04/sc09/sc05, once each, in the filtered original order. Sources,
scenario instructions, plans, catalog and selection (3/100/input-order DFS) are
unchanged. The evaluator file contains only pairs B/F, and no development episodes
are configured. Failed and incomplete outcomes must be kept without retries.

The scripted rehearsal completed 4/4; all four actual publisher inputs contain
the intended ledger mapping and passed file/ledger/binding checks. Direct and
real scheduled Scout replays agree. Those results establish wiring, not live
model compliance. Evidence is `examples/handoff_check_01/`.

Exact model: `anthropic/claude-haiku-5-5`, with anthropic 1.13.0. Official standard/
global prices and no-generation model access were checked for this packet. A
maximum of 84 requests, 12,000 context bytes + 2,000 overhead tokens, 2,048 output
tokens and the 2x input-price reservation multiplier gives a pessimistic ceiling
of **$0.321216**. Proposed cap: **$0.35 for ONE invocation**. Each actual request
is checked against its context and reserved spend bounds before calling the model.

`limits.proposed.json` remains `live_enabled: false`. The original experiment brief
requires a new explicit spending authorization for another invocation; pilot 2's
one-invocation $1 approval has been consumed. Review the exact `review-packet.json`
(code/package/input hashes, scope and commands). No paid invocation has started.

After a fresh $0.35 approval, recheck prices/model availability and the pinned
hashes, create a fresh approved limits copy outside tracked source, and use:

```bash
AUTHORIZED_LIMITS=/workspace/.fragmentguard/handoff-check-01/limits.authorized.json RUN_ROOT=/workspace/.fragmentguard/handoff-check-01/run-01 bash experiments/handoff_check_01/run-reviewed.sh
```

The command sequence verifies package/input hashes, cap, settings and live
preflight, freezes a clean checkout, runs exactly four episodes, replays without
labels, then joins evaluator labels and compares streaming post hoc. The old pilot
2 limits or enabled example files do not authorize this invocation. Actual live
instruction following remains untested until the new run is authorized and made.
