# Next experiment (proposal — discuss before running)

**Question:** without evaluator labels, does resource-lineage selection still
recover the relevant evidence when the metadata is less explicit than in the
four milestone-1 fixtures?

Nothing in this proposal runs automatically. It needs no GPU and no paid API.

## Dataset

- Have someone who did not write the selector or checker author **8–12** new,
  harmless synthetic cases. Use the same event schema and the abstract
  restricted/public catalog. No real data, credentials, targets, or payloads.
- Include:
  - **ambiguous or missing metadata:** a dropped producer event, a missing input,
    a renamed intermediate resource, a resource reused for unrelated content
  - **matched benign collaboration:** the same agents, resources, and handoff
    shapes as the policy-violating cases, ending at an internal audience or at
    public-only ancestry
  - **branching lineage**, where budget and branch priority matter
  - a case where a stale write can mislead a non-causal view, so that this known
    limitation shows up in the results rather than being hidden
- The author writes `ground_truth.json` separately. Only the evaluator reads it.

## Procedure

1. **Freeze the parameters before looking at labels.** Budget 3, horizon 100,
   depth-first branch priority, and checker v0.1.0. Record the config hash from
   `manifest.json`.
2. Check the schema with `fragmentguard replay --streams new_cases.json`. Fix
   authoring errors only. Do not tune the selector.
3. Run once in direct mode and once in scout mode, each to a new output
   directory. Keep the first attempt even if it is wrong.
4. Load the labels afterwards. Report per-case outcomes for all four views, with
   `insufficient_evidence` counted separately from `clear`.
5. Review every disagreement by hand. For each, record whether the cause was
   missing evidence, a stale view, branch priority, or fixture wording.

## What to measure

Measure false alerts, unknown outcomes, selected events, records examined, and
how much a person has to review. Do not optimise only for detections. Make no
aggregate rate claims from 8–12 cases.

## Before any model monitor

A later model-based monitor should first show that it can judge a few
**complete-evidence** cases correctly. Until it can, comparing evidence views
cannot be interpreted. Then also measure tokens and selection overhead. Estimate
cost, agree a spending cap, and get written funding approval before any paid
call.

## Stop conditions

Stop and discuss the design if any of these happen:

- relevant context cannot be identified without labels
- a complete-evidence monitor cannot solve the policy task
- every apparent advantage traces back to how the fixtures were worded

Each of these is a useful finding.

## Questions for a mentor

- Is resource provenance a useful first step toward cross-agent monitoring, or
  is it too narrow?
- Which accessible trajectories have reliable action metadata and benign
  controls? The motivating paper's authors offer FakeLab to safety researchers
  on request. Is requesting it realistic within the sprint?
