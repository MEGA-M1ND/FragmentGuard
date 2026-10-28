# FragmentGuard — submission summary

A publisher releases a summary. Its own actions look routine, but an earlier agent created that summary from confidential material. Can a monitor recover the relevant history across agents—and does it need more than a persistent sensitivity flag?

**Question and safety relevance.** FragmentGuard studies this problem in a controlled three-agent workflow. Advanced AI systems may delegate tasks and pass artifacts through long chains, placing safety-relevant history outside any one agent's context. A recorder and monitor could make that history available for review before an external action. This project tests the monitoring step under an explicit information-flow policy; prevention of real-world harm remains unmeasured.

**What I built.** An installable Python prototype records actions and immutable artifact versions, tracks exact dependencies, and checks whether restricted information reaches a public destination. I compared local monitoring, recent events, resource correlation, full context, and two persistent-state baselines. Evidence includes two twelve-scenario live pilots, scripted cases, and controlled record omissions. Raw records, incomplete workflows and costs are preserved.

**What changed my conclusion.** Correlation initially looked useful: in pilot 2 it resolved 7/8 completed publications, versus 4/8 for a recent-event window. But simple sensitivity tracking matched full-context decisions on all **37 complete publications** in the final comparison. That is expected when outputs inherit their inputs' sensitivity and provenance is exact. The stronger baseline changed the interpretation: the initial improvement depended on what the comparison method remembered.

Correct decisions and supporting records are separate requirements. With a three-record evidence budget, tracking with stored provenance supported **30/37** complete publications, versus **27/37** for the original selector. Among **607 observations with records hidden**, the counts were 155 versus 152. Streaming and all-visible checking agreed, with 452 observations remaining uncertain. Neither method made a wrong definite decision under the trusted-metadata assumptions. No overall cost or speed advantage was established.

**Execution and limits.** Each live pilot completed 8/12 workflows. The same four publishers could not identify the intended artifact from opaque handles. A ledger-derived mapping was implemented and checked against actual model inputs offline; live compliance is untested. The implementation has **113 passing tests**, CI, pinned dependencies and reproducible saved results. Cases are small, overlapping and self-authored. These counts measure consistency with a toy policy, not real-world attack detection. No independent replication is claimed. Implementation and drafting were assisted by OpenAI Codex.

**Contribution and next step.** The project provides an auditable negative result: with trusted provenance and this policy, familiar sensitivity propagation is a sufficient verdict baseline. Oversight evaluations should compare methods with persistent state and distinguish decisions from supporting evidence. The next useful test would challenge producer metadata and measure incorrect clear decisions, uncertainty and resource costs under realistic logging conditions.

**Project and evidence:** https://github.com/MEGA-M1ND/FragmentGuard

**Full write-up:** https://github.com/MEGA-M1ND/FragmentGuard/blob/main/docs/final_report.md
