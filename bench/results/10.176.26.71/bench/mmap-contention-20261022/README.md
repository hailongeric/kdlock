# Actual mmap contention investigation, 2026-10-22

Status: source review and focused checks complete; one bounded diagnostic pair
is ready for admission.
No implementation change or performance acceptance is claimed. The seven
original mutex causes remain unresolved.

This stage starts at clean `d45e0b0` on `master`. The main agent is the sole
writer and VM executor. Helpers review read-only and report no files touched.
The same recovery VM is idle on `6.1.159-kdclobber2`, boot
`e8e0a914-ef13-4063-ab95-e5e89c1eb7da`, with the exact 73 runtime modules.
Recovery preservation and the real snapshot were rechecked. No run was
interrupted. The initial host observation had 68 QEMU threads; the separately
retained diagnostic host prerequisite observation had the original 67 and
passed. Neither observation replaces any earlier rejected endpoint.

## Evidence and hypothesis, recorded before execution

The six retained 16-worker mmap observations have KD/Native whole-rate ratios
`0.291196`, `0.300803`, and `0.275174`. All six endpoints failed; these are
descriptive observations. Native used 27.417–27.868 worker CPU microseconds per
completed cycle; KD used 191.133–212.688. CPU time includes user and kernel work.
The prior [report](../../tests/serial-continuation-20261022/ACTUAL_MM.md) and its
archives remain unchanged.

The frozen client uses sixteen threads sharing one exact mm, mmap lock and
file object, with workers on CPUs 0–15 and collector on CPU 63. A completed
cycle is an untouched one-page shared mmap followed by successful munmap.
All six records have exact maps/closes/completed counts, sixteen joins, zero
payload faults and no retained VMA/file/mm references. `observe=0` means that
zero `contended_mmaps` is not evidence of an empty queue. Page faults remain
a separate workload; no TCLock actual-MM case is appropriate here.

The candidate ELF binds both syscall paths to the killable writer adapter.
KD first reserves exclusive admission, then owns the physical gate, then
drains readers. Admission stays closed until after physical unlock, so local
writers queue before the gate. This path does not use the ordinary writer's
16,384-probe polling loop. Release reopens admission and wakes all phase
waiters. Munmap can downgrade to a reader before teardown, allowing an admitted
writer to wait again for reader drainage. Native uses rwsem optimistic spinning
and head-writer wakeup; its downgrade wakes eligible readers. Exact physical
ownership, signal unwind and reader accounting must remain intact.

**Falsifiable hypothesis:** much of the extra KD worker CPU work is in phase
wait/wakeup and scheduler processing, rather than the physical mutex queue or
common VMA/file/callback work. Source structure makes this plausible; it does
not demonstrate the cause of the observed rate difference.

## Smallest diagnostic

Run one Native then one KD 16-worker profile, serially, using the unchanged
candidate image, frozen client and payload. Reuse completed both-mode
correctness for those exact binaries. Before either profile, run two basic
programs and directly affected diagnostic-control tests in the recovery VM.
Require the unchanged full host/guest admission gate before each load. Do not
run a full matrix or retry a refused profile until it happens to qualify.

Add only inherited `cpu-clock:k` sampling at 99 Hz with kernel-only call chains,
strict frequency selection and the monotonic clock. The retained perf tool
runs on collector CPU 63, without updating its global build-ID cache. The
unchanged client sets worker placement. Recording covers client startup and
exit; analysis selects exact validated worker TIDs, expected CPUs and each
worker's `active_started_ns .. kernel_finished_ns` interval. Retain raw perf
data, sample periods, call chains, tool identity, lost/throttle records and
excluded samples. Raw evidence is archived before export and static analysis
on 380G10. Missing/unresolved stacks and low sample coverage are
limitations, never evidence of zero cost.

The source controller captures the fixed endpoint immediately after the
recorder exits, before validation, unload or export. This includes recorder
flush after client completion and is explicitly a diagnostic endpoint; it
does not replace the earlier plain-client endpoints. Full endpoint checks and
all original business/drain oracles remain. Rates from this instrumentation
class are never performance acceptance. Observer overhead is not isolated by
this single pair and repetition variance is unavailable.

Predeclared interpretation:

- Excess KD on-CPU samples in admission wait/wake or scheduler descendants
  support a subsequent narrow scheduler/stack diagnostic of wake competition.
- Excess in the physical gate/OSQ redirects attention to unexpected gate
  contention; exclusive local admission predicts little such activity.
- Excess predominantly in common mmap/munmap, VMA, file or callback work
  redirects the investigation to that work and its interaction with ordering.
- Little phase-related CPU excess weakens this CPU-cost hypothesis. On-CPU
  sampling cannot measure blocked time or distinguish all inlined phases.

One sampled pair cannot establish causation or justify a protocol change.
No QEMU cause will be inferred from another temporal correlation. Identifying
initiating operations or activity during measurement is a separate unresolved
requirement. New p95 collection remains deferred.

## Diagnostic preparation

Revision `34b43f8` adds the diagnostic wrapper and four focused tests. Read-only
review found no execution blocker. The retained perf binary has SHA-256
`be41fc3678db80aa92593a72034ebd6ec4c574c2dca2523f294dff5a0667aca3`;
its own help confirms the required options. Sampling settings, including the
callchain depth limit, are captured and must remain identical between modes.

The idle synchronization copied 23 changed files (including completed prior
reports) and verified all 4,046 approved hashes; it deleted nothing. In
`checks-1`, dependencies, two basic programs and four new diagnostic tests
passed. The copied existing control test could not import its omitted
`serial.py` helper, so the aggregate attempt remains failed. `checks-2`
included that unchanged helper and passed all ten control tests. No test was
removed or weakened. Both attempts remain separately retained. Final checks
confirmed idle recovery and the exact 73-module set before any candidate boot.
