# Opt-in mapping and fault transactions

This is a supporting callback/backing-lock experiment for stage 2 in the
[project roadmap](../ROADMAP.md). Actual mmap-lock substitution has a separate
[adapter](../../kernel_integration/mmap_lock/README.md). Backing-reader gains do
not establish that adapter's performance or the planned mmap1 result.

This integration owns a small, preallocated device mapping. It does **not**
replace `mm_struct::mmap_lock`. A virtual memory area (**VMA**) describes a
mapped address range; the kernel's native mmap rwsem still protects every VMA
and all of its existing participants. A separate private lock protects this
driver's backing pages, metadata and active fault-in request. These are distinct
objects with distinct responsibilities, not two protocols for one lock.

The payload is [mapping.c](../../workload_modules/mmap_fault/mapping.c). Its
fixed-width [interface](../../workload_modules/mmap_fault/mmap_fault_uapi.h)
creates one backing object per open file. Creation initializes the chosen lock
and all pages before a release-store publishes the object. Reconfiguration is
rejected. Pages contain immutable values, making missing, stale or corrupted
mapping contents observable without introducing a page-writeback protocol.

## Supported cases and fallback

KD uses ordinary `kd_down_read/write`, matching releases and ordinary write-to-read
downgrade. No generated image is prepared, no fault runs on a combiner's task,
and no rwsem call-admission refusal is removed. The currently supported KD
mapping is shared, read-only, non-executable and not inherited across fork.
Permission increases to writable or executable are prevented through the VMA's
maximum permission bits. Allocation, user copies and page-table insertion occur
outside the private lock.

Native uses a private Linux rwsem for equivalent backing work. Explicit requests
for private writable mappings and fork inheritance can fall back to that backend
**before publication**, if `MF_ALLOW_FALLBACK` is set. The reply records both
requested and selected backend and the fallback decision. Without permission,
unsupported requests fail with `EOPNOTSUPP`; an existing KD object is never
reinterpreted or protected by a Native lock. Shared writable mappings are rejected
for every backend because this module has no shared writeback/page-mkwrite contract.

TCLock uses the maintained task-context rwlock only for the short, non-sleeping
backing critical sections. It is not a sleeping rwsem replacement. Its supported
mapping shape matches KD's read-only shared shape. A request requiring downgrade
selects a fresh Native object before publication or fails; a live TCLock object
cannot switch backend. Only equivalent supported cases belong in the private-backing comparison;
execution classes and observation settings remain separate.
The common payload is compiled against one provider at a time, with Native
available in either build; the selected build mode is recorded in module info.
TCLock may combine only the short backing writer work. The fault handler and
native mmap ownership transitions still execute on the originating task.

The normal CPU fault callback obtains a backing-page reference under the chosen
reader lock, releases that lock, and transfers the reference to the kernel's
ordinary fault completion. The original task executes this callback. Remote-mm
fault callbacks are refused; this stage does not establish remote access, DAX,
filesystem callbacks, userfaultfd, huge pages or generic fault replay.

## Exact fault-in scope

The controlled fault-in ioctl calls the real `handle_mm_fault()` on the caller's
own mapping. It retains the ioctl's VFS file reference and an explicit `mmget()`
reference. One request per backing object is admitted at a time. A stack scope
is published under the backing writer lock and binds the exact originating task,
`mm`, request and native mmap acquisition. Only that task's callback may use it.
The scope is removed before returning from the ioctl, after its final unlock.

The scope's `held` field records its own successful native mmap acquisition.
Return flags check that record; they never overwrite ownership or independently
authorize an unlock. The controlled outcomes are:

| Outcome | Native mmap ownership on callback return | Ioctl continuation |
| --- | --- | --- |
| Ordinary page completion | Held | Release once after completion |
| RETRY | Explicitly released | Reacquire and refind/revalidate the VMA |
| RETRY with NOWAIT | Retained | Return `EAGAIN` after one matching release |
| COMPLETED | Page inserted, then explicitly released | Return without another unlock |

NOWAIT here specifies the fault retry's ownership rule. It does not claim that
acquiring the private backing reader lock or entering the ioctl never waits.

COMPLETED returns `NOPAGE | COMPLETED`: the captured kernel's `__do_fault()`
recognizes NOPAGE as a callback that has already supplied the page-table entry.
The COMPLETED bit records the separate mmap release. Returning COMPLETED alone
would not satisfy that callback interface. This path is restricted to the
validated shared read-only mapping with `VM_MIXEDMAP` set at mmap creation.

After a drop, no VMA pointer is reused. The ioctl finds the current VMA, checks
address containment, file identity, callback identity, private object and access
mode again, including the current `VM_READ` permission. Removing that permission
with `mprotect(PROT_NONE)` is refused before calling `handle_mm_fault()`.
Replacing the VMA at the same address causes `ESTALE`. The focused
test pauses one request after its actual release so another thread can replace
the mapping; a bounded pause timeout reports failure and never establishes drain.

Normal CPU faults have no active scope, so these controlled drop/completion
branches are unavailable to them. They use ordinary callback completion. This
restriction avoids attributing ownership to a request that does not retain the
file and `mm` through the entire transition. It does not emulate all architecture
fault-handler branches or claim those branches ran in the hardware-fault path.

## Lifetime, modes and validation limits

VFS references protect the backing object through open descriptors, VMAs and
ioctls. The initial VMA and clone/split callbacks maintain explicit VMA counts.
Page references survive independently when the kernel installs PTEs or creates
private copy-on-write (**COW**) pages. Closing the last descriptor while a VMA
remains must still permit a later fault. Only final file release can inspect idle
and free backing storage. An invariant failure retains storage and a module pin
for diagnosis instead of freeing live state.

The private KD downgrade uses ordinary exclusive admission, changes to a reader,
and finishes with `kd_up_read()`. No delegated downgrade, cancellation after
publication, non-owner release or nested rwsem JIT ledger is introduced. Native
mmap acquisition remains killable; cancellation must leave the scope unowned.
Signal-driven cancellation and additional mapping-option combinations require
separate coverage and must not be inferred from successful ordinary cases.

The [focused runner](../../tests/kernel/mmap_fault/README.md) keeps source, binary,
kernel and callback receipts. Correctness, returned-JIT evidence and performance
acceptance are separate. This driver integrates callbacks for owned mapping state; it does not replace
the actual mmap lock. The separate [Linux 7 MM adapter](../../kernel_integration/linux70/MMAP.md)
has its own identities, correctness prerequisites and actual shared-MM timings.
The [private-MM campaign](../../bench/results/10.176.26.71/bench/catalog-linux70-mm-trusted-20261027/README.md)
records this backing experiment's completed Linux 7 measurements. Neither scope
establishes full-kernel, RT, lockdep or generic fault-path equivalence. Older
full-MM reviews retain their historical status rather than an active blocker list.

## Separate workload tasks

`mmap` does not itself require touching the mapped range. The split client uses
`MAP_SHARED | PROT_READ` without `MAP_POPULATE`, `mlock`, memory access or a
fault-in helper in its mmap-only task. One completed operation is one successful
`mmap`/`munmap` pair. Both the fault-callback count and private backing-lock
acquisition counts must stay zero. The driver retains Linux's native mmap lock;
this control does not establish a KD or TCLock mmap-lock implementation.

The page-fault task creates its VMAs before the start barrier. Each worker owns
an independent native `mm` and shares the same backing object. It discards its
own PTE with `MADV_DONTNEED`, reads the page and checks the immutable value. One
completed fault-cycle operation includes that reset and read; it is not an
isolated lock-acquisition or hardware-fault duration. The callback and reader
acquisition counts must equal the completed fault cycles exactly. Ordinary
reader acquisitions remain concurrent and local. There is no artificial writer
counter and no reader delegation or positive-JIT requirement for this workload.

The concurrent case adds one real metadata writer to fifteen fault readers;
its epoch updates and writer pairs have a separate exact oracle. In the VMA-only
case every descriptor closes before the first fault, then all workers fault and
unmap before final release. That case relies on the final release's exact idle,
pairing and error checks; the freed object cannot provide a post-release snapshot.

TCLock comparisons are restricted to its supported resident backing operations.
Actual native mmap mutation, task/GS-dependent critical sections, sleeping
critical sections and user-memory access inside a combined body are unsupported
TCLock replacements and are not timed as TCLock cases. Reader-only KD execution
is reported as local. Delegation of a genuine exclusive backing update would be
a different workload with its own execution evidence; it must not be obtained
by serializing this read-only lookup.
