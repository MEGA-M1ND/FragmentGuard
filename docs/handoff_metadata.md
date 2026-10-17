# Ledger-derived handoff revision

Pilot 2 remains preserved at its recorded inputs, messages and outputs. This
executor revision adds metadata for future executions; it does not change or
rerun pilot 2. No live generation is authorized by this change.

The original handoff gave the publisher only opaque handles. The task named
`summary`, but the user message did not identify which handle had that name.
The new message appends a version 1 JSON payload computed from committed versions:

```json
{
  "version": 1,
  "artifacts": [
    {"handle": "v002", "name": "subset"},
    {"handle": "v003", "name": "summary"}
  ],
  "latest_by_name": {"subset": "v002", "summary": "v003"}
}
```

Every handed intermediate/version remains listed; unnamed versions have a null
name. Repeated names map to the last committed version **within this handoff**,
while the artifacts list keeps older versions. This is deliberately separate from
the workspace's mutable global aliases. A background operation could reuse the
same name; the message instructs the recipient to use the mapped immutable handle
so that unrelated alias replacement cannot redirect the requested artifact.
No target is selected from assistant prose, evaluator labels, catalog sensitivity,
ancestry or condition/pair membership. Only version ID and display name are exposed.
The same contract applies at both agent boundaries, symmetrically across twins.
The existing handles remain in the transcript for compatibility.

The transcript now records the exact initial user message and handoff metadata.
A new `handoff_contract_sha256` fingerprint freezes the message contract. Existing
pilot freezes reject execution with this new protocol; historical recorded traces
remain replayable without generation. No old freeze fingerprints are rewritten.
The additional message bytes must be included in future context/spending preflight;
previous live limits and approvals cannot simply be reused.

## Actual-input checks

`tests/test_handoff.py` captures messages at the real backend boundary. Its offline
publisher resolves the intended name solely from that message, then passes the
immutable handle to the existing publication tool. Cases cover all four failed
scenarios, multiple intermediates, repeated names, a background alias overwrite,
an absent target and an unnamed version. Poisoned assistant final prose is not
forwarded. Missing targets remain incomplete rather than being guessed. A test
also verifies that the old pilot 2 freeze cannot execute this changed protocol.

For reviewable snapshots of all twelve normal scenario inputs:

```bash
python -m fragmentguard.experiments.handoff --config /workspace/FragmentGuard/experiments/agent_pilot_02/pilot_config.json --output NEW_DIRECTORY
```

The runner records the actual first publisher backend request, including system,
user and tool schemas, and independently compares the mapping and intended target
with the execution ledger. It checks files and normalized bindings too. Its
scripted completion alone is not the evidence: the delivered input is captured
and checked explicitly. Catalog/evaluator files are never opened. These checks
establish input availability and correct handle resolution, not live compliance.

Observed offline outcome: 12/12 captured publisher inputs passed every ledger,
intended-target, artifact and binding check. Snapshots:
`examples/handoff_metadata/offline-check-20261017/publisher-inputs.json`.
These include `summary -> v003` for sc05/sc11 and `report -> v005` for sc04/sc09,
without hiding any intermediate processor versions. The targeted input tests also
pass the replacement-name, background overwrite, unnamed-version and absent-target
cases. No live model was called.

The independent [missing-evidence review](missing_evidence_review.md) separates
no-deletion controls from actual masking and preserves every previous result.
