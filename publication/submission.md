# FragmentGuard — submission summary

**Project question:** Can resource provenance recover safety-relevant evidence across agents, and does that approach add value over simple sensitivity tracking?

**Why it matters for advanced AI safety:** As advanced agents delegate tasks and pass artifacts through long workflows, an oversight system watching one agent can miss dependencies that make a downstream action consequential. FragmentGuard isolates this issue with a toy information-flow policy. Its contribution is a reproducible comparison of context-limited monitoring, persistent state and supporting-evidence retrieval—not a general detector of harmful intent.

**What I did:** I built an installable Python prototype with a three-agent sandbox, action recorder, immutable artifact versions, strict producer bindings, deterministic policy checker and Inspect Scout integration. I compared per-agent context, a recent-event window, lineage correlation, full context, streaming sensitivity and streaming with provenance. The work includes two twelve-scenario live pilots, offline comparisons and exhaustive record-omission interventions. Incomplete episodes and their costs were retained without retries.

**Main findings:** With complete, exact provenance and the declared restriction-preserving policy, streaming sensitivity matched full-context verdicts on all 37 publications in the final comparison. At a three-record checker budget, streaming with provenance supplied sufficient raw evidence for 30/37 publications, versus 27/37 for the original correlation selector. Among 607 observations with records hidden, those counts were 155 versus 152; no wrong definite verdict occurred under the trusted-pointer contract. Neither comparison establishes an overall cost advantage: the methods retain different state and perform different work.

Both live pilots completed 8/12 episodes. Four publishers could not identify the target artifact from opaque handles; clarifying the name alone did not fix this. A ledger-derived mapping was then implemented and verified against actual backend inputs offline. Its live compliance remains untested. The prepared four-case live successor was not run and is outside the completed study.

**Quality and limitations:** The recorded implementation has 113 passing tests, CI checks, pinned dependencies, hashes and preserved raw evidence. Cases are tiny, self-authored, overlapping and not held out. The policy is deliberately simple, resource identity is exact, and the missing-record analysis assumes honest producer metadata. Counts are not general attack-detection accuracy or proof of deployment safety. No independent replication or external review is claimed.

**What the negative result tells us:** A context-limited monitor is not a sufficient baseline when persistent provenance state is available. In this setting, simple propagation was enough for verdicts, and the original selector showed no supporting-evidence advantage over the stronger baseline. The useful next research question is how this changes under a realistic recorder contract and measured resource costs.

**Recorded cost:** $0.0209384 accounted for the two live pilots; $0.0222025 including two development episodes, using supplied historical rates. No paid calls were made for publication.

**Project:** https://github.com/MEGA-M1ND/FragmentGuard

**Full write-up:** https://github.com/MEGA-M1ND/FragmentGuard/blob/main/docs/final_report.md
