# FragmentGuard — presentation notes

## A 90-second walkthrough

Imagine three AI agents: one reads a confidential document, one writes a summary, and one publishes it. A monitor watching only the last agent may miss where the information came from.

I built FragmentGuard to test whether following artifact history across agents helps. It records actions and dependencies, then compares several ways of checking a simple rule: restricted information should not be published publicly.

The most useful result changed the interpretation of the project. Correlation did better than a monitor looking only at recent events. But a simple baseline that remembered each artifact's sensitivity matched full-context decisions on all 37 complete publication cases.

That makes sense: if every output inherits its inputs' sensitivity, we can propagate that fact as the workflow runs. We also tested supporting evidence. Within three records, the stronger baseline supplied enough evidence for 30 cases, versus 27 for the original selector.

When records were hidden, uncertainty increased sharply. The study still assumed trustworthy metadata, so it does not establish safety against dishonest agents or broken logging.

The contribution is a reproducible prototype and a lesson for advanced-agent oversight: compare against persistent state, and distinguish a correct decision from the evidence needed to justify it. The next useful question is what happens when the provenance itself is unreliable.

## A short visual walkthrough

1. Show the [workflow figure](figures/workflow.svg). Point out that the relevant history crosses agent boundaries.
2. State the verdict result: sensitivity tracking matched full context on **37/37** complete publications.
3. Show the [supporting-evidence figure](figures/support.svg). Explain that **30/37 versus 27/37** concerns returned records at a three-record budget, not verdict accuracy. The masked panel uses a different denominator.
4. End with the boundary: exact, trusted metadata and a simple policy. The concrete follow-up is to challenge that metadata.

## Questions reviewers may ask

**Isn't this just taint tracking?** The strong verdict baseline is a form of familiar taint tracking. The project's contribution is testing the original monitor against it, separating cached verdicts from raw evidence, and preserving the negative result in a reproducible implementation.

**Why is this relevant to advanced AI safety?** Delegated workflows distribute information needed for oversight. This prototype studies one narrow part of that problem: maintaining dependencies across agents. It does not test strategic deception or demonstrate that a deployed system would prevent harm.

**How strong is the evidence?** It supports an implementation-level conclusion under explicit assumptions. The 37 cases overlap in structure, and the 607 masks are interventions on existing traces. Neither is a set of independent real-world attack trials. The report explains why verdict agreement is expected under the policy.

**What happened in the live runs?** Each pilot completed 8 of 12 workflows. Four failed at an artifact-name handoff. Those failures are included in the record. A mapping derived from the execution ledger passes offline checks; its live effectiveness remains untested.

**What would justify continuing the work?** A realistic recorder contract, tests with missing or incorrect producer metadata, and measurements of false clear decisions, uncertainty, evidence sufficiency and resource use. A more complex selector would need a demonstrated benefit under those conditions.

Use the [submission summary](submission.md) for the written application and the [full report](../docs/final_report.md) for methods, results and evidence links.
