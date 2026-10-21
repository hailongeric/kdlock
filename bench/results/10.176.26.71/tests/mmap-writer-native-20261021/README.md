# Native shared-mm mmap writer stage

Status: `live-3` at `b9fe567` passed both basic programs and all six focused
Native correctness cases, with exact drain and normal unload. The first two
stack-probe failures remain retained below. The four serial Native timing-client validations at `b043da5` also passed and
drained. Controlled timing is waiting for the original host precondition. Overall acceptance remains false.

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
integration work will be recorded here; a Native baseline is not KD integration.

## Stack probe diagnosis

`live-2` at `3e19abb` again failed the expected unfiltered stack shape. It retained
80,000 completed map/unmap cycles, sixteen exact worker joins, 79,608 nonempty
queue observations, zero fault/context errors and zero final VMAs. Final module
health was again `files=0 mm_refs=0 destroyed=3 release_errors=0`; normal unload
succeeded. The failure log includes one stdout/stderr interleaving, preserved
verbatim. The next client flushes its receipt before reporting failure.

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
