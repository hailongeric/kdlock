# Native shared-mm mmap writer workload

The current Native runner targets Linux 7 and requires a fresh ELF-bound writer
witness; its port has not yet been executed. The new [Linux 7 shared-MM runner](linux70.py)
adds an explicit one-round Native/KD plan for a separately enabled kernel. Its
build, boot and correctness prerequisites are in the
[Linux 7 MM plan](../mmap_fault/LINUX70_PLAN.md).

The historical [built-in mmap comparison](../mmap_lock/README.md) reused this payload
and timed client with a separately checked 6.1 kdmm31 Native/KD mode. A qualified
validation pair and the [October 26 exploratory MM screen](../results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md)
have completed under their own policies. The original 24-session proposal and
later three-repeat scaling matrix retain their separate stopped/unrun status.
The original runner's `NATIVE_MMAP_LOCK` labels cannot establish KD execution.
Historical boot identities and instruction offsets do not authorize Linux 7.

This is a stage 2 diagnostic in the [project roadmap](../../docs/ROADMAP.md).
It maps untouched 4 KiB read-only device ranges. The planned mmap1_threads target
uses 128 MiB anonymous private read/write mappings with the same shared-mm
topology; it requires a distinct runner/validation record.

This workload measures actual Native `mm_struct::mmap_lock` writers. Pthreads
share one address space and issue ordinary `mmap`/`munmap` calls without touching
the mapped ranges. It is separate from page-fault workloads and from the earlier
independent-process mmap control. This original Native runner installs or times
no KD or TCLock lock. The kdmm31 comparison instead selects the built-in backend
for the actual mm while preserving native MM bodies on the originating task.

The standalone [payload](../../workload_modules/mmap_writer/mapping.c) binds an
open file to the exact originating mm. Every identity ioctl and mmap callback
checks that mm; identities contain the actual mm and mmap-lock addresses, TGID
and TID in privileged evidence. Forking a process that inherits the descriptor
must fail the identity/mmap checks with `EXDEV`. Sharing a file alone is not
accepted as sharing an mm.

Each VMA retains the file, and every file retains one `mmgrab()` reference to the
mm descriptor. This is deliberately not an `mmget()` reference to `mm_users`,
which could form a cycle through the file's VMAs and prevent exit teardown.
Final VFS release alone permits freeing the object and dropping that reference.
VMA creation, split/open and close counts check the lifetime relation; counters
never grant ownership, authorize an unlock or replace references. A fault
callback is always a failure: there are no backing pages in this Native writer
payload. The module retains state on a release invariant failure.

The optional read-only `observe=1` setting counts instances in which the native
rwsem wait queue is nonempty while the actual mmap writer calls the module.
It does not acquire, release, replace or extend the native mmap lock. At sixteen
workers, correctness requires a positive observed contention count without
padding the body. This is a queue observation, not an acquisition-latency or
per-waiter ownership record. Keep observed and unobserved timing separate.

The focused [correctness runner](../../tests/kernel/mmap_writer/README.md)
checks actual shared-mm identity, Native writer contention, rejected foreign
mm/modes, split/unmap accounting, descriptor-closed VMA lifetimes and process-exit
teardown. Timing must follow successful validation. Reader delegation and the
discarded artificial writer lookup have no role in this workload.

During correctness only, the controller samples its workers' kernel stacks.
The Native writer proof expects `/proc` to filter `__sched` lock helpers. The required
positive receipt binds the first remaining return PC to an independently
decoded `down_write_killable(&mm->mmap_lock)` call in the exact kernel ELF.
Both bracketing task states must be `D`, both wait channels must match that
caller, and scheduler execution counters must remain unchanged. A generic
rwsem queue, arbitrary mmap frame or running task is insufficient. The runner
checks the whole ELF hash, raw stack, return offset, exact TID and shared mm.
No permissions are changed; missing evidence fails. This sampler is excluded
from timing. The two earlier failures and their raw observations are retained
in the stage report.

The [timing runner](timing.py) requires the six-case correctness receipt, reuses
its validated payload binary, and validates both 1/16-thread plain/sampled
clients before measurement. The Native baseline uses `observe=0`; callback
accounting remains enabled. It runs two seconds per session, three repetitions,
collector CPU 63 and workers 0..N-1, preserving the preceding setup's 300 ms
settling/window, 10 ms progress and 256-operation checkpoints. Sampled mode
measures every 64th complete mmap/munmap cycle with per-worker offsets. Both
modes use identical stop-clock frequency. CPU time is per-thread, and all
identities, exact callbacks, joins, sample counts and final module drain are
required. Repeated measurements use strict original host preflight and retain
an immediate endpoint check; a failed endpoint prevents acceptance.

The sampled interval covers the complete successful mmap/munmap cycle. It does
not separate mmap from munmap or isolate lock acquisition. The workload primarily
exercises writer ownership, including possible munmap downgrade; it does not
measure sustained concurrent-reader scaling. Zero payload fault callbacks do
not mean zero incidental process or kernel faults. Native/KD comparison results
must retain these limits, each observation mode and every repetition separately.
No performance gain follows from the retained rejected timings.
