# Regression evidence review, 2026-10-21

Status: **the pipecap execution-path difference is established; its cause and
historical host interference remain unresolved. No new timing or acceptance.**

This stage follows the completed [84-session recovery replay](../mutex-recovery-followup-20261021/README.md).
It does not repeat the already completed adapter synchronization or
[actual mmap-lock correctness stage](../../tests/mmap-kd-kernel-20261021/README.md).
The checkout was clean at `930dbeeb607309183465bdbbf42a2512a8fe1182` on `380G10`;
the same VM was idle on recovery release `6.1.159-kdclobber2`, boot
`88449cfc-cea9-4647-a294-bc601e372146`, with the original 73 runtime modules.
The main agent remained the sole writer. Both helpers performed read-only
source/archive review and reported **no files touched**. No in-flight run was
interrupted, no parallel test ran, and no host or kernel setting changed.

## What the failed host endpoint establishes

The replay's preflight contained 67 QEMU tasks. Its immediate endpoint at
`09:25:06.881411 UTC`, 0.894800 seconds after matrix completion, contained
100. The original 67 TID/name/affinity rows match exactly; the additional
33 rows are all named `worker` and pinned to CPU 63. These receipts do not
contain task start times, runtime, I/O, state or wait channels. They cannot
reconstruct worker activity during the measurements, exclude TID reuse, or
bound the run's interference. The failed endpoint remains failed.

The new, bounded read-only `qemu-snapshot-1` at `09:56:55.912272 UTC` captured
**74 tasks before and after**. None of the earlier 33 extra TIDs remained.
The seven later workers were sleeping in `futex_wait_queue` on CPU 63, with
summed lifetime scheduler runtime **7,563,295 ns** and lifetime write accounting
**1,761,280 bytes**. These are cumulative counters for different threads, not
measurement-window deltas. They support disk-writing activity by the later
workers but cannot identify the earlier workers' activity or its timing cost.
Even all seven later workers' user/system tick counters were zero; treating
zero tick deltas as zero work would be incorrect.

This observation also fails the required 67-thread count. No timing session
was started from it, and no later quiet observation may replace the historical
immediate endpoint. The raw snapshot is retained
[here](../../raw/bench/mutex-causal-boundary-20261021/qemu-snapshot-1.json),
SHA-256 `14e94a505c3f343ca8f6136835ff6ce4329a64d9d5d058f58f7f8ab9c94bebaa`.
It used the unchanged [read-only snapshot tool](../../../../mutex_api_compare/qemu_snapshot.py),
existing QEMU PID 257489 and exact command hash, with a 45-second remote bound.
The command completed successfully; this was not a benchmark or a full
environment-preflight pass.

A proposed group-CPU residual was reviewed but **not implemented or accepted
as an interference bound**. Subtracting original-thread CPU from whole-process
CPU requires verification against the actual host kernel's live/dead task
accounting and timestamp brackets. At 100 ticks/second, independent rounding
of two counters across the process and 67 tasks alone can permit 1.36 seconds
of slack. Even a valid CPU bound would not bound I/O, cache effects, host kernel
workers or collector delay. Earlier continuous-observer results retain their
missed-lifetime and observer-cost limitations; see the
[prior diagnostic](../pipecap-causal-20261021/README.md).

## Pipecap: physical acquisition versus delegation

The six original recovery-session logs establish more than a zero completion
count. Every OUTER session has lifetime delegation slowpath, combiner, JIT
success/resume, gate-owned acquisition/release and task-reroute counters equal
to zero. Thus these loaded OUTER sessions never entered the delegation queue;
there is no evidence of queued work failing to return. DIRECT entered that
queue and returned generated bodies in every repetition.

| Repeat | OUTER measured returns | DIRECT measured returns | OUTER lifetime queue entries | DIRECT lifetime queue entries |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0 | 1,271,599 | 0 | 2,639,726 |
| 1 | 0 | 1,485,068 | 0 | 2,977,547 |
| 2 | 0 | 1,129,127 | 0 | 2,411,562 |

The final heat records show only 2–3 CPU checks per OUTER worker, versus
563–764 for DIRECT. Every recorded OUTER lock heat value is zero; all five
DIRECT worker lock heat values are one. This supports cold admission under
sparse OUTER contention. It does not reconstruct every admission decision:
final heat entries/contentions are residual observations, while `checks` and
provider lifetime totals include warmup.
Zero resource/JIT failures do not mean zero admission refusals. No heat
threshold, queue condition, resource check or probe was removed.

Both callers protect the same pipe-capacity read. Their execution classes and
delegated fractions differ, so dividing their rates cannot isolate same-path
API cost. Earlier nominal RETURNED_JIT pairs also had substantially different
returned fractions. The retained [source/ELF audit](../pipecap-owner-20261021/static-binding-checks.json)
shows additional DIRECT return/general-unlock work while physical ownership is
held. Its duration and contribution remain hypotheses, not measured causes.

## Smallest next control and prerequisites

A separately named diagnostic can retain the frozen OUTER acquisition and
replace only its workload's unlock macro with the existing DIRECT general
unlock. The frozen provider already exports that route, and OUTER's zero-cookie
branch already uses it. Keep the original provider, headers, symbol versions,
body, ABI2 continuation, n16, CPU placement and all admission settings. Build
only the derivative workload in a new VM directory; never overwrite or relabel
the original baseline. This control has **not been implemented or run**.

Before timing, require the basic and affected resource/routing checks, including
physical ownership after scheduler restoration, unrelated task/borrowed-lock
records, exact native unlock ACKs, gate-owner release ordering, delegated return
and final retirement. The existing OUTER fixture's nonzero-cookie branch uses
local unlock, so it does not already validate this derivative. Also require
the derivative's syscall correctness and exact callsite/image/import audit.

If those checks and the unchanged fresh host gate pass, use three fixed serial
hybrid repetitions paired with three fresh original OUTER controls. Keep
`jit_timing=0`; avoid the previously perturbing owner polling, in-lock clocks
and boundary-counter pauses. A shift in delegation behavior could establish
that the general unlock shell is sufficient under those conditions. It would
not identify an individual instruction cost, clear historical host failures or
by itself establish a production optimization. An unchanged result leaves
acquire-wrapper/return/spill placement and other causes open.

## Evidence and disposition

The [inert review](review.py) verified the prior manifest and all four archive
hashes, read six logs and their records without executing archived code, checked
ownership balance/final drain, reconstructed the thread difference and bound
the new observation. [Structured results](review.json) retain every source
member/hash, counter, CPU heat record and later worker identity. The original
archive manifest remains
`a57c35c0a11df0812b6a621a688c50229e5cc6c9fdde60868e1799640cf281d1`;
no original receipt or measurement was rewritten.

This stage changed only reporting and offline evidence review. **No new VM
tests, builds or timing sessions ran.** Earlier basic plus 19 affected checks
and all 84 drained sessions retain their original scope. Variance remains in
the [prior per-repeat report](../mutex-recovery-followup-20261021/review-1/groups.json);
no samples or source revisions were pooled. The [final idle receipt](final-idle.json)
confirms the unchanged recovery boot and original 73 runtime modules.

All seven points—c08/3,4,5; pipebytes/3,5; pipecap/5; RCUHT/2—remain
`UNRESOLVED_CAUSE`. Acquisition-only latency, strict low-count rwlock execution,
shared-lock performance and earlier class gaps remain unresolved. Sampled
complete-operation p95 is separate evidence. Mmap and page fault remain separate
workloads with local concurrent readers; unsupported TCLock MM bodies are not
scheduled. Performance acceptance remains open.
