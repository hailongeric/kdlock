# Native shared-mm mmap writer workload

This workload measures actual Native `mm_struct::mmap_lock` writers. Pthreads
share one address space and issue ordinary `mmap`/`munmap` calls without touching
the mapped ranges. It is separate from page-fault workloads and from the earlier
independent-process mmap control. No KD or TCLock lock is installed or timed.

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
This kernel's `/proc` unwinder filters `__sched` lock helpers. The required
positive receipt binds the first remaining return PC to an independently
decoded `down_write_killable(&mm->mmap_lock)` call in the exact kernel ELF.
Both bracketing task states must be `D`, both wait channels must match that
caller, and scheduler execution counters must remain unchanged. A generic
rwsem queue, arbitrary mmap frame or running task is insufficient. The runner
checks the whole ELF hash, raw stack, return offset, exact TID and shared mm.
No permissions are changed; missing evidence fails. This sampler is excluded
from timing. The two earlier failures and their raw observations are retained
in the stage report.
