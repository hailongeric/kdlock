# Phase accounting across warmup and cleanup, 2026-10-21

Status: implementation and focused validation in progress. No timing permitted.
The checkout was clean at `bdd8472` on 380G10, without a source writer or index
lock. Fresh read-only checks found the same recovery VM drained, with its
original 73 modules, boot `88449cfc-cea9-4647-a294-bc601e372146` and kernel
`6.1.159-kdclobber2`. The main agent remains the sole writer/VM executor;
helpers perform read-only review and report no files touched.

The [previous control](../mutex-prewarmup-20261021/README.md) saw full gates pass
before and immediately after one original warmup, then an endpoint worker
failed the unchanged 67-task gate. Its five-second accounting cadence captured
no samples during warmup or any later phase. This control tests the specific
hypothesis that the endpoint worker is born during post-warmup validation or
cleanup/control I/O, rather than remaining from warmup. A birth interval wholly
after the post-warmup full capture would distinguish those alternatives. Phase
association cannot identify which operation caused a birth or delayed I/O.

Keep the existing five-second pre-warmup quiescence protocol, exact original
67 TIDs/names/placement and every full-gate/guest/ownership/ACK/lifetime check.
Use the same frozen provider, client, workload, translator and original warmup.
The guest runner is unchanged. After selecting the pre-gate full capture, arm
one uniquely identified **60-second, nonrenewable** window through the existing
observer connection after a passing host gate, taking a baseline accounting read before its ACK. The
added round trip precedes the guest pre-gate reply and is recorded separately;
the absolute arm budget is ten seconds. A missing/late ACK never releases the
guest, whose existing timeout retains uncertain state.

Within the window, read every **250 ms from the previous scan's completion**;
never issue catch-up reads. Also read at existing phase marker requests before
their ACK, retaining the preceding phase and the pending marker separately.
For full gates, capture first, then take a linked accounting read before the
capture ACK. Ready control requests take priority over periodic accounting;
an already-running read can still delay a request and is recorded. No deliberate
accounting read precedes the immediate post-warmup full capture. The endpoint
full capture remains in its original position, followed by accounting while
the window remains active; it is never replaced with a later quiet capture.
Window expiry is explicit and missing endpoint accounting remains a coverage
gap. The neutral `accounting-window-armed` label identifies observer state,
not the exact original-work interval. A failed following accounting read retains
the completed full capture plus its error; the coordinator does not release
the guest on a failed required ACK.

Keep continuous sample sequence numbers, TID/start-tick identity checks before
and after each read, partial/disappeared rows, CPU/I/O counters, BOOTTIME birth
intervals and per-task/scan clock brackets. Full capture CPU/wall cost stays
separate from following accounting and ACK latency. Preserve observer total
CPU/wall cost, source/guest control chronology and the changed preparation
history. No timed command, throughput matrix or performance acceptance is
permitted. Denser sampling still misses short lifetimes, exited-worker tails,
capture-length gaps and non-atomic changes; differently named extra threads
have identity but no worker-specific CPU/I/O read in the existing observer.

Run basic and directly affected checks serially before the live control, then
verify normal retirement, final drain, recovery state and frozen hashes.
Preserve all refusals and uncertain resources. All seven mutex causes and
acquisition latency remain unresolved; complete-operation p95 is separate.
Readers remain concurrent/local, mmap and faults stay separate, and unsupported
TCLock critical sections remain excluded.
