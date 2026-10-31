# Current 60-process investigation

The retained baseline has a small number of much faster workers (sample
minimum/maximum about 16.7k/291k), while the candidate is almost uniform near
20k/21k. The aggregate loss does not establish a uniform slowdown of all workers.
Both arms have about 98.4% lifetime CPU occupancy, so a 22% off-CPU increase
is not supported. No per-worker vector or event attribution was retained.

Current source inspection rules out capacity-driven backend substitution in
kd_mmap_init: use_kd is copied from the boot-time mode, with no allocation-based
Native fallback. This is a code finding, not per-worker execution evidence.

The original upstream main.c has SHA256
48d4640f151801fdfb5f3915c822cf280c713df3c1998068e16ce0c961cbf746,
matching the pinned preparation. It sums per-worker differences from shared
64-bit counters spaced 256 bytes apart. The existing score parser conserves
sum/2 over the two post-marker samples. Min/max are per-worker differences;
there is no per-worker vector in ordinary output. The original application
has a verbose option, but changing its measured argv would create a different
instrumentation contract. Do not turn that on or mix such results silently.

First complete the fresh unchanged-application comparisons. If the large process
loss persists, isolate attribution with explicitly separate diagnostic evidence;
source speculation is not a fix. The reader restoration is currently the sole
production optimization. No process-loss remedy is claimed yet.

A further source-only lead is global commitment accounting. In the captured
scope1 source, include/linux/mman.h:76-83 routes vm_acct_memory and
vm_unacct_memory through vm_committed_as. lib/percpu_counter.c:93-112 takes
fbc->lock with raw_spin_lock_irqsave when the per-CPU batch threshold is crossed;
the body rereads and adjusts this-CPU counters while IRQs are disabled.
This can serialize separate mms if that branch is reached. The current records
do not establish its actual batch threshold, sampled contention or contribution
to the 60-process loss. Do not call it the diagnosed hotspot without observation.
Its mandatory this-CPU operations also prevent simply proxying the whole body
on a different CPU while preserving the original per-CPU accounting semantics.
No accounting policy, batching threshold, native body or lock was changed.

The captured mm/util.c:890-893 explicitly cacheline-aligns vm_committed_as and
states that other globals must not share its cacheline. A neighboring-global
false-sharing explanation is therefore not supported by this declaration.
The mmap accounting wrapper passes vm_committed_as_batch, rather than the
ordinary percpu_counter_batch. The captured source does not include that
runtime batch value; do not substitute the generic 128-counter batch for it.
A 128 MiB mapping accounts 32,768 base pages at 4 KiB, but whether it crosses
the actual commitment batch still needs the selected boot's value and path.

A direct Git comparison of f7a84065 and 1b6f256b shows no changes in
include/kd_rwsem_types.h, include/kd_mutex_types.h, the mmap lock types header,
or the mmap adapter body. A changed object layout or new backend-selection
policy therefore cannot explain the difference between those two revisions.
This source finding does not identify which shared resource was contended.

The pinned main.c process mode calls fork() for each worker, whereas thread
mode uses pthread_create(). Therefore the expected steady-state process case
has distinct mm objects and distinct mmap writer gates. Cross-worker contention
on one mmap_lock is not the expected explanation for that mode. This is a source
inference, not a trace proving that every acquisition was uncontended. The
process harness also installs a once-per-second SIGALRM parent-lifetime check;
normal pending-signal handling must continue to preserve successful acquisition
before cancellation. No signal behavior or application code is changed.

Consequently restoring reader entry is primarily the Nano experiment. It is not
by itself a demonstrated remedy for the write-side 60-process mmap/munmap loss.
Fresh promoted/recovery timing must be retained even if it shows no recovery;
a global resource or worker imbalance needs separate attribution before any
additional production change is justified.

The current common actual-MM fixture verifies a writer behind a writer on the
physical gate's exact task-linked wait list. f7a84065 instead waits on the
rwsem phase queue before acquiring that gate. Running the current fixture on
that old protocol would fail its internal queue witness, independently of the
external API outcome. The present fresh MM pair is promoted versus recovery;
it cannot by itself prove parity with a newly measured f7a84065 kernel. A future
fresh three-arm MM comparison needs a source-bound protocol selector in the
fixture: exact target membership on the old phase queue or the new gate queue,
with all cancellation, holder ownership, rollback and downgrade assertions
retained. Merely omitting the writer-queue assertion would not establish the
same correctness evidence. No such selector is implemented in this iteration.
