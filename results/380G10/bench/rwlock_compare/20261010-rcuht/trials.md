# RCUHT rwlock optimization trials

These are separate candidate screens, not extra rounds in the final comparison.
All timed screens use the same two mixes, four post-work rounds, CPU prefixes,
three rounds, two-second interval and warmed 300 ms peak methodology. Source
and binaries are frozen independently in each evidence directory. The final
[full matrix](README.md) reruns all three backends at all fifteen thread counts.

The original ABI1 hash writer refused JIT admission after its inline writer
admission atomics widened address provenance. Two attempted existing-guard and
pointer-precomputation candidates still refused. They were discarded. ABI3 moves
writer admission into the native caller/combiner prelude, preserving strict
payload admission and the existing spin packet/completion protocol. A pre-body
refusal cancels that admission; native retry reacquires it before entering the
restored body. The first ABI3 live probe passed with 34,248 returned JIT writers.

The table shows **best warmed peak / median whole-run Mops/s** at 36 workers.
Every cell has three JIT-positive rounds, except the marked NO_JIT cells.

| Candidate | Evidence directory | 1% writes | 20% writes | Decision |
| --- | --- | ---: | ---: | --- |
| ABI3, every writer takes the gate, compact 8-byte object | `screen-baseline` | 12.768 / 11.972 | 3.701 / 3.622 | Starting point |
| Ungated native fast writer, compact count/gate | `screen-fast` | 11.680 / 11.576 | 4.440 / 4.292 | Keep fast writer, continue tuning |
| Readers retry the counter instead of queuing | `screen-reader-retry` | 6.196 / 6.000 (NO_JIT) | 3.059 / 2.734 | Reject |
| Two NUMA reader counters and separate writer flag | `screen-striped` | 10.146 / 9.543 (NO_JIT) | 1.586 / 1.282 | Reject |
| Separate count/gate cache lines, fast-writer pre-read, reader-unlock SUB | `screen-isolated` | 14.013 / 12.682 | 5.292 / 4.931 | Retain; measure full matrix |

The retained implementation uses 128 bytes per lock instead of eight. Its
improvement over the first ABI3 candidate at 36 workers is 9.8%/5.9% for
peak/whole throughput at 1% writes, and 43.0%/36.1% at 20%. The three final
changes were measured together; these screens do not isolate each change's cost.
They also do not establish parity at unmeasured thread counts.

`screen-baseline` contains 72 sessions with Native, TCLock and KD at 1, 8, 16 and
36 workers. `screen-fast`, `screen-striped` and `screen-isolated` contain 24 KD
sessions each at those four counts; `screen-reader-retry` contains 18 KD sessions
at 8, 16 and 36. JIT-positive and NO_JIT rounds remain separate in each summary;
the baseline's 1%/16-worker group and the retry candidate's 20%/8-worker group
are split. [trial-statistics.csv](trial-statistics.csv) retains all groups.

All completed screens passed their data/progress/drain checks. Rejected candidates
also passed their functional exclusion checks; performance is why they were
rejected. Failed admission attempts, initial fixture/build corrections, successful
functional probes and every raw timing sample remain in the complete evidence
archive. They are not counted as passing rounds of the final matrix.
