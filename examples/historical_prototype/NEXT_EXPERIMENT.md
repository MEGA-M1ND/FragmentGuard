# Next experiment — discuss before running

**Question:** can resource-based evidence selection recover relevant context
from mixed agent streams without using evaluator labels?

Start with a small independently authored toy set. Keep policy decisions
harmless and explicit, such as whether an abstract restricted record may be
included in a public report. Include matched benign collaborations using the
same resources and handoff patterns. Do not generate or execute cyber attacks.

## Three candidate directions

1. **Evidence robustness:** remove or rename one resource link at a time to
   measure how readily the selector becomes uncertain instead of producing an
   unsupported clean verdict.
2. **False alerts under collaboration:** add benign agents that share resources
   and interleave handoffs, to find whether correlation drags unrelated context
   into review.
3. **Monitor prerequisite check:** give a small model monitor complete evidence
   for a handful of clear toy-policy cases; only compare selected views after
   that monitor demonstrates it can judge the underlying task.

## A bounded pilot

- Verify one full Scout run locally, using the existing deterministic checker.
- Have another person or a separate author write 8–12 new cases without tuning
  the selector on their labels. Keep labels in an evaluator-only file.
- Freeze selector parameters and keep all decisions causal in time.
- Compare per-agent, fixed-window, and correlated views with the same checker.
  Keep full context as a diagnostic and report insufficient-evidence outcomes
  separately from clear results.
- Inspect disagreements manually. Record evidence reviewed and lookup overhead;
  avoid aggregate performance claims from such a small sample.

Stop if relevant context cannot be identified without labels, if a complete-
evidence monitor cannot solve the policy task, or if all apparent improvements
come from fixture wording. Those outcomes are useful findings about the design.

## Funding

The next offline checks need no GPU or paid API. If a model pilot becomes useful,
estimate actual input/output tokens and provider prices, agree on a spending
cap, and apply for a small grant before incurring reimbursable costs. A $50–100
grant is a possible initial request range from the course guidance, not an
estimate of this prototype's cost. Written funding approval is still required.

## Questions for the mentor

- Is this resource-provenance problem a useful first step toward cross-agent
  monitoring, or is it too narrow for the intended safety question?
- Which accessible trajectories have reliable action metadata and benign
  controls, and can we use them within the sprint?
- Is requesting FakeLab artifacts realistic for a course participant, or should
  the project stay focused on open tooling and evidence-selection audits?
