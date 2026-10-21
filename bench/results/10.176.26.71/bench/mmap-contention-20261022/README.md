# Actual mmap contention investigation, 2026-10-22

Status: source review and focused checks complete. The single diagnostic
attempt was refused at 72 QEMU threads versus the required original 67, before
either workload or profiler started. Both planned profiles remain unrun.
Recovery is restored and idle. No implementation defect or causal performance
explanation was demonstrated.
No lock protocol change or performance acceptance is claimed. The seven
original mutex causes remain unresolved.

This stage starts at clean `d45e0b0` on `master`. The main agent is the sole
writer and VM executor. Helpers review read-only and report no files touched.
At stage start, the same recovery VM was idle on `6.1.159-kdclobber2`, boot
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

## Exact source and emitted paths

The [source review receipt](source-review.json) binds the candidate ELF
(`7c7305c78f5466276a79e3cde4d2809dce67a9677896b30e268d8f4e3d08f236`)
and Build ID `687ff5a29315d732f93a618e50ac407c794bbf9b`. The local upstream
archive matches captured SHA-256
`1f207ebe93980829ecc0a18b694816f22b715e9893767731651969a168342b9e`.
Selected native rwsem, mmap, util and wait sources were copied directly from
that verified archive for offline inspection; ancestor and integration patches
leave those paths unchanged. The generated KD rwsem is separately bound by the
captured candidate manifest, SHA-256
`5082e25dcdb075effbf51da9f4f1879ca53ddcea36976c7150f8998234a0f252`.

Exact emitted return locations distinguish the following call paths. They
identify instructions/callers, not observed execution counts or blocked time.

| Call | Return location |
| --- | --- |
| mmap writer acquisition | `vm_mmap_pgoff+0xae` |
| munmap writer acquisition | `__vm_munmap+0x96` |
| Adapter calling KD / Native | `kd_mmap_write_lock_killable+0x30` / `+0x3e` |
| KD phase wait / reader-drain wait | `kd_mmap_down_write_killable+0x78` / `+0x11f` |
| KD wake after writer release / downgrade | `kd_mmap_up_write+0x5a` / `kd_mmap_downgrade_write+0x74` |
| Native initial spin / queued spin / sleep | `rwsem_down_write_slowpath+0xc8` / `+0x298` / `+0x2af` |

The source and ELF support a specific next discriminator, not a fix: separate
sampled gate/OSQ, writer wait/wake, reader release/downgrade, and common MM work.
Generic scheduler or wake symbols require an uninterrupted caller chain;
interrupt work and missing ancestry remain unknown. Retain sampled leaf and
caller context separately. The existing gate has no demonstrated defect that
would justify changing ownership, admission, signal unwind or reader drainage.

## Diagnostic attempt and recovery

Run identifier: `mmap-contention-20261022/pair-1`. The coordinator revision is
`ff6dc91`; the guest diagnostic remains `34b43f8`. The one-shot Native candidate
boot was `6829007d-ec9d-43a1-8c9e-d01ba81f9b21`. Recovery image/default and all
5,686 recovery module files were preserved; the exact 73 runtime modules were
restored and boot logs had no configured kernel-fault matches.

The single fresh post-boot host capture failed the original host prerequisite:
**72 threads versus 67**, SHA-256
`dc1a87a8e664715e15d4e2d72823bcec4cd95d89f962ce15c6b04d9e7491ec13`.
The guest profile command was never invoked, so its deeper candidate admission
gate did not run. No payload was loaded, no perf recorder started and no new
rate, stack distribution or repetition variance exists. Native and KD are
explicitly unrun in [pair-result.json](pair-result.json). There was no quiet-state
retry, substituted endpoint, broad matrix or protocol change.

Recovery returned to `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`68924d08-9913-4e43-91f8-3643e3331c09`, with the exact 73 modules, preserved
recovery artifacts and no configured fault matches. Known floppy boot I/O
messages remain in the full logs. See [recovery transition](recovery-transition.json).
The [fresh final health](final-health.json) rechecks that same boot, idle state,
all 73 modules and preservation after the evidence transfer.

All seven original causes remain **unresolved**: c08 at 3/4/5 workers,
pipebytes at 3/5, pipecap at 5, and RCUHT at 2. The mmap wake-competition
hypothesis is also unresolved. The prepared pair is the next discriminator once
the original admission requirements can be met; this report does not authorize
weakening them. QEMU initiating operations, activity during measurement and
causal rate effects remain unestablished. Earlier rejected measurements,
variance and source versions remain distinguishable and unchanged.

## Artifacts

The [artifact index](artifact-index.json) binds the check, candidate-transition
and recovery archives by run path, size and SHA-256. The
[independent pretransition review](pretransition-review.json) checked all 242
members and 201 source bindings, preserving the failed import attempt. Tar
timestamps match inventory at floating-point precision; exact nanosecond
equality is not claimed. Raw source/disassembly review, synchronization logs,
all host captures and command receipts are under
`raw/bench/mmap-contention-20261022/`. The original campaign's artifacts remain
under their original paths and identities.

The [pair archive review](pair-archive-review.json) verifies four additional
groups containing 56 files and six directories, including the complete boot
chain and preserved recovery receipts. The final control seal is manifest
`6e4d22b19d429d634e6baa7f97a713e003192d902d604475e096a0817ff74cc8`.
It includes the exact refused host capture and 168 source-side files, including
all earlier stage archives, commands and source review. The sealed report is
the snapshot before these final archive links and audit records were appended.
All [31 prior archives](prior-preservation.json), totaling 17,850,550 compressed
bytes, were rechecked and remain unchanged. Helpers touched no files.
The [final independent audit](final-archive-review.json) passed 2,331 checks
with zero errors across the final seal and its nested evidence. All eight stage
archives, totaling 1,958,321 compressed bytes, are accounted for; no preservation
gap was found. This evidence-completeness result does not resolve the refused
diagnostic or any performance cause.
