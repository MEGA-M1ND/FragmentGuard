# Assumptions

Every result in this repository depends on the assumptions below. If one fails,
the matching outcome stops being meaningful. That would not by itself make the
code wrong.

## Inputs

1. **Records are accurate and ordered.** Each workspace's events arrive complete,
   in strictly increasing tick order, and they say truthfully what was read,
   written, and published. Nothing here collects, authenticates, or reconciles
   real action logs. Out-of-order input is rejected, not sorted.
2. **Resource identifiers are exact and trustworthy.** Two events that name the
   same resource in the same workspace refer to the same object. Aliases,
   renames, copies through channels that are not logged, and content-level
   similarity are all out of scope. Resource names stand in for content. There
   are no files or network destinations.
3. **Workspaces are isolated.** A stream ID marks a workspace boundary. Resource
   state never crosses streams, even when names are identical. Stream IDs must be
   neutral (`streamNN`), so they cannot carry campaign or attack labels.
4. **Catalog roots are immutable.** The trusted policy classifies root resources.
   Any event that writes to a catalog root is rejected before checking.
5. **Labels are evaluator-only.** `ground_truth.json` is read by `reporting.py`
   only after scanner results exist. A test checks that the schema, selection,
   checker, and scanner modules never reference it. Transcript metadata must be
   empty, and the scanner rejects transcripts that have any.

## Selection

6. **Causal only.** A publication's views use only events at or before it. Later
   events cannot change an earlier result, and a test checks this.
7. **Latest write wins.** For each input, correlation follows the latest earlier
   producer in the same workspace. When replaying, the checker lets the latest
   *selected* write replace earlier state.
8. **Deterministic, naive branch priority.** Correlation walks depth-first, in
   the order inputs are listed. With a tight budget, the first input's lineage
   can use up the budget before later inputs are visited. A test shows this
   giving `insufficient_evidence` where budget 4 gives `alert`. This was not
   optimised.
9. **The horizon and budget only remove evidence.** A producer outside the
   horizon, or past the budget, is left out and stays unknown. In the fixtures, a
   bounded correlated verdict is always either the full-context verdict or
   `insufficient_evidence`; this is tested for every budget and horizon from 0 to
   7. Being close in time is a constraint on selection, not evidence of harm.
10. **Non-causal views can be stale.** Per-agent and fixed-window views are not
    closed under dependencies. If a write the view did not see replaced the one
    it did see, the checker replays the stale state. That can produce a wrong
    `clear` (see `test_per_agent_view_can_be_misled_by_unseen_overwrite`). This is
    a property of the baselines, and it is reported, not corrected.

## Checker

11. **Restricted status propagates.** Every `read` or `transform` output inherits
    the union of its inputs' ancestry. There is no redaction, summarisation
    exemption, approved declassification, or partial-content reasoning.
12. **Narrow toy policy.** Publishing to `internal` is always allowed. Publishing
    to `public` raises an alert if restricted ancestry is established, is clear
    only if all ancestry is known and public, and is `insufficient_evidence`
    otherwise.
13. **No model, intent, or harm judgment.** The checker does not judge intent,
    plausibility, or general harmfulness, and calls no model.

## Measurement

14. **Event budgets are not costs.** The three bounded views share a *maximum*
    of 3 selected events. The number they actually select differs. Selected
    counts and records examined are measured and reported. Tokens, latency, and
    human review effort are not measured.
15. **Four designed cases are not a sample.** The fixtures were written with the
    checker in mind. They verify the wiring. No rate, interval, significance
    test, or generalisation claim follows from them.
16. **Hashes are identity, not authenticity.** Manifest hashes show which files
    a run used and produced. They do not defend against a malicious logger.
