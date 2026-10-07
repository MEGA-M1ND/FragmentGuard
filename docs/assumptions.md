# Assumptions

Every result in this repository depends on the assumptions below. If one fails,
the matching outcome stops being meaningful. That would not by itself make the
code wrong. The last section separates the properties the tests support in
general from those that hold only for the four fixtures.

## Inputs

1. **Records are accurate, complete, and ordered.** Each workspace's events
   arrive complete, in strictly increasing tick order, and they say truthfully
   what was read, written, and published. Nothing here collects, authenticates,
   or reconciles real action logs. Out-of-order input is rejected, not sorted.
2. **Resource identifiers are exact and trustworthy.** Two events that name the
   same resource in the same workspace refer to the same object. Aliases,
   renames, copies through channels that are not logged, and content-level
   similarity are all out of scope. Resource names stand in for content. There
   are no files or network destinations.
3. **Workspaces are isolated.** A stream ID marks a workspace boundary. Resource
   state and bindings never cross streams, even when names are identical. Stream
   IDs must be neutral (`streamNN`), so they cannot carry campaign or attack
   labels.
4. **Catalog roots are immutable.** The trusted policy classifies root resources.
   Any event that writes to a catalog root is rejected before checking.
5. **Labels are evaluator-only.** Expected outcomes are read by `reporting.py`
   only after scanner results exist. A test checks that the schema, selection,
   checker, and scanner modules never reference them. Transcript metadata must
   be empty, and the scanner rejects transcripts that have any.

## Observation metadata: input bindings

6. **Every read is bound to the write it actually saw.** `schema.input_bindings`
   records, for each input of each event, the ID of the latest earlier event in
   the same workspace that wrote that resource, or `None` if no earlier event did.
   - It plays the role of a logger recording object versions.
   - It is **causal**: a binding depends only on earlier events in the same
     workspace, and later events cannot change it.
   - It is **label-free**: it holds producer IDs only, never classifications or
     expectations.
   - It is **the same for every view**: each view receives the bindings of
     exactly the events it selects. The views differ only in which events they
     select.

   The bindings are derived from the complete ordered log, so they rest on
   assumption 1. If a real log dropped a write, deriving bindings afterwards
   would bind the read to an older write: the same stale-write failure, moved
   one layer down. Data with missing events needs bindings recorded at the
   source, such as version IDs carried in the records. That would be a schema
   change. It is not implemented, and the fixtures do not need it.

## Selection

7. **Causal only.** A publication's views use only events at or before it. Later
   events cannot change an earlier result.
8. **Correlation follows bindings.** Starting from the publication, the selector
   follows each input's binding to its producer, then that producer's bindings,
   up to the budget and the horizon.
9. **Deterministic, naive branch priority.** Correlation walks depth-first, in
   the order inputs are listed. With a tight budget, the first input's lineage
   can use up the budget before later inputs are visited. This was not
   optimised.
10. **The horizon and budget only remove evidence.** A producer outside the
    horizon, or past the budget, is left out. Its binding stays unresolved.
    Being close in time is a constraint on selection, not evidence of harm.

## Checker

11. **Reads resolve through bindings, never by name alone.** An input bound to a
    selected producer inherits that producer's ancestry. An input bound to a
    producer the view omitted is **unresolved**, even if the view contains an
    older write of the same name. An unbound input is a catalog root if the
    policy lists it, and unresolved otherwise. Each result lists its unresolved
    inputs (`resource<-producer`, or `resource<-none`), including for internal
    publications, which the policy allows anyway.
12. **Restricted status propagates.** Every `read` or `transform` output inherits
    the union of its inputs' ancestry. There is no redaction, summarisation
    exemption, approved declassification, or partial-content reasoning.
13. **Narrow toy policy.** Publishing to `internal` is always allowed. Publishing
    to `public`:
    - raises an alert if restricted ancestry is established;
    - is clear only if all ancestry is resolved and public;
    - is `insufficient_evidence` otherwise.
14. **No model, intent, or harm judgment.** The checker does not judge intent,
    plausibility, or general harmfulness, and calls no model.

## Measurement

15. **Event budgets are not costs.** The three bounded views share a *maximum*
    of 3 selected events. The number they actually select differs.
    - `selected_event_count` is measured.
    - `records_examined` is measured: the records the selector looked up, not
      counting the single shared pass that derives bindings.
    - Tokens, latency, and human review effort are not measured.
16. **Hashes are identity, not authenticity.** Manifest hashes show which files
    a run used and produced. They do not defend against a malicious logger.

## What is demonstrated vs. fixture-specific

**Supported in general:** a reasoned argument plus exhaustive tests over every
sub-view of 400 seeded random streams (`tests/test_properties.py`):

- **Soundness of any view.** For *any* subset of earlier events plus the
  publication, under the binding contract, the checker returns either the
  full-context verdict or `insufficient_evidence`. A view never returns `alert`
  or `clear` where the full log says otherwise.
  - The argument: every resolved binding is a true dependency edge, so the roots
    a view finds are a subset of the true roots. `clear` requires the entire
    lineage to resolve inside the view.
  - The property covers all four views, including the per-agent and
    fixed-window baselines. They can lose evidence, but they can no longer
    replay stale writes.
  - The pre-fix checker broke this property on 71 of 7,366 generated sub-views.
- **Completeness of unbounded correlation.** With a budget and horizon large
  enough to take the whole dependency closure, the correlated verdict equals the
  full-context verdict.
- **Causality.** Bindings and every publication's results are unchanged when
  later events are appended.

These are tests, not a formal proof. They cover the toy schema only: four
operations, two audiences, exact identifiers, and complete logs.

**Checked only on the bundled fixtures and hand-written cases:**

- The four fixtures' expected outcomes: correlated and full context give clear,
  clear, alert, alert.
- The specific selections and counts in reports, such as `e01, e03, e06`.
- That the per-agent and fixed-window views return `insufficient_evidence` on
  fixtures 1, 3 and 4. This shows how the fixtures were built, not how often it
  happens.
- The stale-write regression and its controls in `tests/test_bindings.py`.
- Any comparison *between* views (which one is more often conclusive). Nothing
  here measures that rate. Four designed cases are not a sample.
