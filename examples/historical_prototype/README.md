# FragmentGuard

A first, offline prototype for selecting related events across agent trajectories.
This version runs a deterministic resource-provenance checker on four harmless
synthetic streams. It does not execute agent actions or call a model API.

**Status:** the Scout database round trip and direct invocation of a decorated
Scout scanner work. The full Scout scan scheduler is blocked in this hosted
runtime. This is a code smoke test, not a replication of a paper's finding.

## Get the first example running

Use Python 3.12. The first run used Python 3.12.14, Inspect AI 0.3.277, and
Inspect Scout 0.5.4.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m fragmentguard.run --mode direct --output runs/my-first-run
```

Run these commands from the project directory. On Windows, use the interpreter
in `.venv/Scripts/` instead. `requirements.lock.txt` records the complete installed
dependency versions from the first environment; `requirements.txt` pins the two
direct dependencies. Output directories must be new, so a rerun cannot overwrite
earlier evidence.

The successful run is included in `runs/direct-first-run/`: `report.json` gives
method outcomes and fixture hashes; `scanner-results.json` contains the scanner's
returned results; `transcripts/` contains the Scout database.

To try the full scheduler on a normal local machine:

```bash
.venv/bin/python -m fragmentguard.run --mode scout --output runs/local-scout-run
```

That command uses Scout's mock model setting and the same deterministic scanner.
It remains unverified here because the scheduler failed before scanning. See
`FIRST_RUN.md` for the failures; do not interpret those aborted jobs as completed
evaluations. The project does not patch Scout, psutil, or runtime restrictions.

## What the example does

The trusted toy catalog marks one resource as restricted and one as public.
Publication to an internal audience is allowed; publication of a restricted
resource's descendants to a public audience should raise an alert. All resource
names are abstract identifiers. There are no credentials, real files to publish,
network destinations, or commands in the fixtures.

Three agents can read, transform, and publish a resource. Other events are
interleaved. For each publication, four views feed the **same** checker:

| View | Evidence available at that point |
| --- | --- |
| Per agent | Up to three events from the publishing agent |
| Fixed window | The last three events in the stream |
| Correlated | Up to three events selected by latest-producer resource links, within a 100-tick horizon |
| Full context reference | All past and current events in the stream |

The reference view is a diagnostic, not a matched-budget baseline. The three
bounded views have a maximum event budget, not equal token cost or equal
computational cost. The correlation algorithm searches the available history;
its lookup cost has not been measured or optimized.

Outcomes are `alert`, `clear`, or `insufficient_evidence`. Missing provenance
stays missing; it is never silently scored as clean. Each result lists the
selected event IDs and how many events the checker reviewed. The evaluator reads
`ground_truth.json` only after scanner execution. Labels and campaign membership
are not included in the monitor input. Stream IDs define isolated workspaces,
not inferred attack groups.

## Assumptions and limits

- Records are complete, ordered, accurate, and independently supplied. This
  prototype does not collect or authenticate real action logs.
- Resource identifiers are exact and local to each workspace; catalog roots are
  immutable. Renaming, aliases, missing events, and ambiguous resource identity
  need separate evaluation.
- Transformations preserve restriction status. The toy checker has no concept
  of approved declassification, redaction, intent, or general harmfulness.
- The four cases were designed alongside the checker. Their outputs verify the
  wiring and policy logic; they cannot estimate detection rates on real agents.
- No model-generated trajectories, LLM monitor, adaptive adversary, FakeLab
  reproduction, or Inspect Scout scheduled scan has completed.

The motivating paper is [Multi-Agent AI Control: Distributed Attacks Hamper
Per-Instance Monitors](https://arxiv.org/abs/2607.07368). This project has not
obtained or run the authors' FakeLab artifacts. The current example demonstrates
a simple provenance handoff, not the paper's distributed repository attacks.

## Next step

First verify the full scheduler on your local machine. Then discuss whether to
request the paper's artifacts or use an independently authored, benign toy
dataset with less explicit resource links. Before model comparisons, check that
each model can solve a complete-evidence example; otherwise a context-selection
comparison will not be interpretable. See `NEXT_EXPERIMENT.md` for a bounded plan.
