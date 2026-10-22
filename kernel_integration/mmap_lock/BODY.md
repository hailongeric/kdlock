# Minimal actual-MM body experiment

Status: basic programs and receipt guards passed; the first kernel build failed
on header ordering and split-directory include resolution. Corrected build and
live VM validation are pending. Preserve the
installed `kdmm1` local-only results and the `kdclobber2` recovery kernel.

The first supported in-tree body is `madvise_vma_behavior()` for DONTDUMP/DODUMP
over one complete, isolated, ordinary anonymous VMA. Admission checks run while
the combiner physically owns that mm's actual KD mmap write lock. Exact range
boundaries prohibit splitting; unmapped gaps prohibit merging. File/device
callbacks, special/huge/locked/growing VMAs, userfaultfd, named VMAs and memory
policies are refused before effects. The original in-tree helper performs the
flag update. This is fixed compiled-body execution, not a JIT-image claim or
general mmap syscall delegation.

An explicit test opt-in enables this entry for an existing KD mm without
changing its backend. Readers retain the concurrent local KD read protocol.
All other MM paths retain their prior routing. Newly created mms start with the
entry disabled; a refusal cannot be reset within the same mm lifetime.

The queue uses the existing per-CPU mutex nodes and independent OSQ/delegation
links. A node lends its OSQ membership to its own physical acquisition and
points to its caller's retained typed request; no packet or frame is copied.
Published producers poll with preemption disabled. A same-CPU predecessor or
exhausted slot refuses publication and permits a sleeping local acquisition.
The experimental queue is bounded FIFO (256 bodies per acquisition); it does
not change the loadable provider's existing NUMA policy or ABI2 interface.

Only the physical owner executes a supported body and releases the writer
phase. A refused queued request becomes permanently non-delegable for this mm
entry and is handed to its origin before any body effect. The origin's exact
slot, task, mm, state and physical-owner record authorize the native continuation.
The physical owner waits for its ACK, then releases the request for retirement.
No VMA pointer crosses a lock drop, and the retained mm reference outlives every
remote completion. Queued cancellation retains its link until the owner consumes
it before body admission. Cancellation after admission cannot replay effects.
Published cancellation is not an eager unlink: a cancelled waiter can return
only after its predecessor/owner consumes the link. Bounded signal-response
latency and general Linux killable-lock equivalence are not established for this
opt-in body entry. Ordinary mmap-lock killable APIs retain their local protocol.

The [focused probe](../../tests/kernel/mmap_lock/body/README.md) requires actual
different-task completion, exact business effects, shared readers, native
handback, sticky refusal and complete cleanup. Untouched mmap and page fault
remain separate workloads. The existing fault retry, completed-fault, remote-mm
and lifetime checks remain required; no unsupported TCLock MM workload is added.
Full arbitrary MM body delegation, general JIT integration and optimization
remain outside this minimal path. Performance tuning and p95 are deferred.
