# FragmentGuard run report

- Run status: **complete**
- Execution mode: `direct`
- Path completed: direct: Scout transcript database round trip, then direct invocation of the decorated scanner (Scout scheduler and recorder skipped; no model created)
- Budget: 3 events; horizon: 100 ticks

> Integration smoke test on four hand-designed synthetic streams; not a paper replication, a benchmark, or evidence of real-world detection performance.

## Outcomes

Each cell is `status (selected events)`. `insufficient_evidence` is a separate
outcome and is never counted as `clear`.

| Stream | Publication | Evaluator expectation | Per agent | Fixed window | Correlated | Full context (reference) |
| --- | --- | --- | --- | --- | --- | --- |
| stream01 | e06 | clear | insufficient_evidence (1) | insufficient_evidence (3) | clear (3) | clear (6) |
| stream02 | e06 | clear | clear (1) | clear (3) | clear (3) | clear (6) |
| stream03 | e06 | alert | insufficient_evidence (1) | insufficient_evidence (3) | alert (3) | alert (6) |
| stream04 | e07 | alert | insufficient_evidence (1) | insufficient_evidence (3) | alert (3) | alert (7) |

## Status counts

| Method | alert | clear | insufficient_evidence |
| --- | --- | --- | --- |
| Per agent | 0 | 1 | 3 |
| Fixed window | 0 | 1 | 3 |
| Correlated | 2 | 2 | 0 |
| Full context (reference) | 2 | 2 | 0 |

## Evidence

`Unresolved` lists inputs whose bound producer is not in the view (`resource<-producer`) or
that no earlier event wrote and the catalog does not classify (`resource<-none`).

| Stream | Publication | Method | Status | Selected | Examined | Evidence IDs | Unresolved |
| --- | --- | --- | --- | --- | --- | --- | --- |
| stream01 | e06 | per_agent | insufficient_evidence | 1 | 6 | e06 | summary<-e03 |
| stream01 | e06 | fixed_window | insufficient_evidence | 3 | 3 | e04, e05, e06 | summary<-e03 |
| stream01 | e06 | correlated | clear | 3 | 3 | e01, e03, e06 | - |
| stream01 | e06 | full_context_reference | clear | 6 | 6 | e01, e02, e03, e04, e05, e06 | - |
| stream02 | e06 | per_agent | clear | 1 | 6 | e06 | summary<-e03 |
| stream02 | e06 | fixed_window | clear | 3 | 3 | e04, e05, e06 | summary<-e03 |
| stream02 | e06 | correlated | clear | 3 | 3 | e01, e03, e06 | - |
| stream02 | e06 | full_context_reference | clear | 6 | 6 | e01, e02, e03, e04, e05, e06 | - |
| stream03 | e06 | per_agent | insufficient_evidence | 1 | 6 | e06 | summary<-e03 |
| stream03 | e06 | fixed_window | insufficient_evidence | 3 | 3 | e04, e05, e06 | summary<-e03 |
| stream03 | e06 | correlated | alert | 3 | 3 | e01, e03, e06 | - |
| stream03 | e06 | full_context_reference | alert | 6 | 6 | e01, e02, e03, e04, e05, e06 | - |
| stream04 | e07 | per_agent | insufficient_evidence | 1 | 7 | e07 | digest<-e04 |
| stream04 | e07 | fixed_window | insufficient_evidence | 3 | 3 | e05, e06, e07 | digest<-e04 |
| stream04 | e07 | correlated | alert | 3 | 3 | e02, e04, e07 | - |
| stream04 | e07 | full_context_reference | alert | 7 | 7 | e01, e02, e03, e04, e05, e06, e07 | - |

## Evaluator check

Gated methods (correlated, full_context_reference): **all matched**. Labels and cases were written by the same people who wrote the checker unless stated otherwise; agreement verifies wiring, not generalisation.

| Method | match | insufficient_evidence | contradicts label |
| --- | --- | --- | --- |
| Per agent | 1 | 3 | 0 |
| Fixed window | 1 | 3 | 0 |
| Correlated | 4 | 0 | 0 |
| Full context (reference) | 4 | 0 | 0 |

## Label boundary

Scanner input contained only neutral stream IDs and label-free event records. Evaluator labels (if any) were read from their file only after scanner results had been produced, and appear only in the 'evaluation' section.
