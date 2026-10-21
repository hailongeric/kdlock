# Native shared-mm mmap writer stage

Status: **Native shared-mm correctness complete; performance unaccepted; actual
KD mmap-lock integration blocked.** `live-3` at `b9fe567` passed both basic
programs and all six focused cases with exact drain and normal unload. At
`b043da5`, four timing-client validations and twelve controlled sessions passed
and drained. Eighteen corrupt receipts were rejected. Both earlier stack-probe
failures remain archived. The immediate host endpoint failed at 76 versus the
original 67 QEMU threads. All seven mutex regression causes remain unresolved.

This stage uses the same sole writer on 380G10 and sole serial executor
in the existing `10.176.26.71:2222` recovery VM. It changes no kernel, Native lock,
admission rule, access setting or KD/TCLock protocol.

The preceding [split campaign](../mmap-fault-split-20261021/README.md), evidence
commit `f5233fb`, remains fixed. Its 48 timings use independent address spaces;
its 73-versus-67-thread endpoint failure and all seven mutex causes stay open.
This new Native baseline uses pthreads sharing the actual mm and mmap lock.
Mmap/munmap do not touch their ranges. No private backing-state lock substitutes
for native mmap locking. TCLock's unsupported full mmap critical sections are
excluded, and no delegated-reader work is introduced.

The payload binds each file to an exact mm descriptor, verifies caller/VMA
identity, retains VFS/VMA lifetime and an `mmgrab` reference, and treats any fault
as a failure. The test distinguishes shared threads from a forked child that
merely inherits the descriptor. Native lock-queue observations are separately
labelled and never authorize an unlock. See the [workload contract](../../../../../bench/mmap_writer/README.md).

A complete inert kernel C/header/assembly/configuration capture is retained for
host-side participant inventory. The current KD object/API cannot coherently
replace the actual native member without converting all participants and the
missing ownership/mode/context interfaces. The source inventory and concrete
integration work are recorded in [INTEGRATION.md](INTEGRATION.md); a Native
baseline is not KD integration.

## Stack probe diagnosis

`live-1` at `4a960ab` passed the two basic programs, builds, scope and single-worker
cases, then failed the required sixteen-worker blocked-writer stack check.
No sixteen-worker pass was recorded. After the client exited, exact module
health showed `files=0 mm_refs=0 destroyed=3 release_errors=0`, no workers
remained, and normal unload succeeded. `live-2` added bounded raw observations
and retained worker joins and teardown before reporting the same failure.

`live-2` at `3e19abb` again failed the expected unfiltered stack shape. It retained
80,000 completed map/unmap cycles, sixteen exact worker joins, 79,608 nonempty
queue observations, zero fault/context errors and zero final VMAs. Final module
health was again `files=0 mm_refs=0 destroyed=3 release_errors=0`; normal unload
succeeded. The failure log includes one stdout/stderr interleaving, preserved
verbatim. The corrected client flushes its receipt before reporting failure.

Captured `kernel/stacktrace.c:97,136` uses
`stack_trace_consume_entry_nosched()` for `/proc` task stacks; it filters
`in_sched_functions()`. The exact kernel ELF confirms that both lock helpers
are in the filtered scheduler-text range. Consequently the previous requirement
could never observe the requested helper frames. The retained top return PCs
are `vm_mmap_pgoff+0xab` and `__vm_munmap+0x93`. Independently decoded instructions
immediately before both return PCs call `down_write_killable`; the captured
source binds the argument to the actual current mm's mmap lock.

The revised positive proof requires those exact ELF-bound return sites plus
bracketing `D` task state, matching wait channels and unchanged scheduler
execution counters. This remains a required actual blocked-writer observation;
queue counts alone cannot pass it. ELF SHA-256:
`7125f9b8e76ee72315f83e7129dbf5be38bdbe56ba5b3461f4997290907d9402`.
The [fixed call-site receipt](../../../../../tests/kernel/mmap_writer/writer_sites.json)
records disassembly hashes and Build ID. Raw ELF and disassembly remain in
`raw/tests/mmap-writer-native-20261021/kernel-capture-1/`.

## Focused correctness completion

`live-3` completed 1,000 one-worker and 80,000 sixteen-worker map/unmap cycles.
The latter observed 79,106 nonempty native queues and a sleeping writer TID
3069158 at `vm_mmap_pgoff+0xab`, with unchanged scheduler counters and exact
shared mm/mmap-lock identity. Every cycle had zero fault callbacks, zero clones
and matching create/close counts. Scope checks rejected a forked mm and invalid
mapping modes, then verified one VMA split and both closes. One- and sixteen-VMA
lifetime cases closed every descriptor before unmapping. Process exit closed
its remaining untouched VMA. All six processes left zero file/mm references
and zero release errors; final `destroyed=6`. No kernel fault matched the log.

The separate timing revision uses the validated payload binary with queue
observation off. Its timing client first requires four serial validations
(1/16 workers, plain/sampled) before a twelve-session plan: the same two worker
counts, both observation modes and three repetitions. Each run lasts two
seconds; collector 63, workers 0..N-1, 300 ms settling/window, 10 ms progress,
256-operation checkpoints and one latency sample per 64 operations remain
unchanged. Whole-cycle latency includes mmap plus munmap. Thread CPU time uses
`CLOCK_THREAD_CPUTIME_ID`; no stack sampler runs during timing. Native callback
accounting remains instrumentation and is part of this baseline's scope.

The [actual mmap-lock integration audit](INTEGRATION.md) records the captured
participant inventory, current API gaps, downgrade/fault ownership transitions,
origin context and lifetime work. KD integration remains explicitly blocked;
no Native/KD protocol is mixed and no private side lock substitutes for mmap.

Before the controlled campaign, host receipts 4 and 5 showed 75 and 96 QEMU
threads versus the original 67. These observations are retained. No timed
campaign was started from either state, and no worker was killed or host setting
changed. Timing-client validation results are not pooled with later repetitions.

## Controlled Native measurements

Run `timing-run-1` uses frozen `b043da5` inputs and the validated payload from
`live-3`. All twelve sessions drained, with 8,791,264 completed map/unmap cycles,
zero payload fault callbacks and 71,644 sampled cycle latencies. Basic programs
also passed during `timing-prepare-1`. Repetitions and instrumentation modes
remain separate from that four-session validation and the earlier independent-mm
baseline. No stack sampling or queue query runs during measured cycles.

| Workers | Mode | Whole cycles/s median | Whole range | CV | Peak cycles/s median | Cycle p95 median |
| ---: | --- | ---: | --- | ---: | ---: | ---: |
| 1 | plain | 658,172 | 435,976–658,964 | 17.96% | 661,433 | not sampled |
| 1 | sampled | 657,058 | 656,978–658,761 | 0.13% | 661,331 | 1.585 us |
| 16 | plain | 108,217 | 108,135–132,484 | 9.85% | 113,493 | not sampled |
| 16 | sampled | 106,278 | 105,708–107,378 | 0.65% | 110,079 | 69.515 us |

The plain one-worker first repetition was slower; it is retained. The plain
sixteen-worker first repetition was faster; it is also retained. Sampling
ratios are confounded by repetition variation and cannot isolate observer cost.
The sampled sixteen-worker p95 ranged from 64.099 to 72.269 us. These are
instrumented Native controls, not accepted scaling or KD/TCLock speedup claims.
See [every repetition](per-repeat.csv) and [full ranges/CVs](timing-summary.json).

Fresh host receipt 6 matched all original 67 QEMU threads before timing.
The immediate endpoint, captured before evidence copying, contained 76 threads.
Original QEMU PID/arguments, CPU frequency policy, NUMA configuration, pinning
and snapshot identity matched. The extra service workers invalidate the strict
endpoint; neither a later settled state nor a throughput median replaces it.
No runtime cause is inferred from this endpoint observation alone.

## Preservation and remaining work

The [archive manifest](archives.json) covers development failures, correctness,
timing, the complete kernel input capture, exact kernel ELF/disassembly and
metadata. Raw archives are at
`bench/results/10.176.26.71/raw/tests/mmap-writer-native-20261021/archives/`;
the original guest stage and sibling `-archives` directory are retained.
Archive manifest SHA-256: `715b83ea8fc3d091900247b5482f733f401f27bfe023a88e9ae8eafff3c18a17`.
The [independent inert review](offline-review.json) passed 31,923 checks
over 1,748 members (1,589 files, 0 symlinks). It
recomputed source/Git bindings, exact identities and callback counts, observed
peak windows, sample coverage, p95 and variance without executing retained
workload code. Full captured kernel source separately passed 61,567 per-file
hash checks. [Final health](final-health.json) verifies 1,517 retained input
hashes, zero matched per-session kernel faults and final idle. The
[status receipt](final-status.json) retains every attempt and acceptance gate.

The actual mmap-lock integration audit is blocked on coherent object/API and
participant conversion, downgrade/non-owner/nested semantics, exact release
and origin context, and MM/VMA/file/page lifetime contracts. No guest kernel
was changed. Reader delegation remains absent, unsupported full TCLock MM
critical sections are excluded, and all seven mutex causes remain
`UNRESOLVED_CAUSE`. Earlier host-interference and returned-JIT gaps remain at
their existing evidence state. No production optimization or global acceptance
is claimed. Only the main agent edited this stage's files and ran its tests; no helpers were
active or spawned, and no test runs overlapped or were stopped. During final
report review, unrelated edits became staged in `docs/LOCKS.md`,
`docs/design/kd_only_mutex.md` and `docs/design/mutex_implementation.md`. Their
authorship was not established. They subsequently appeared in separate commit
`133e5a5` and were preserved outside this stage's edits;
global single-writer coordination is therefore not claimed. All VM work had
already completed before those edits appeared.
