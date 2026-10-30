# Bounded same-mm syscall writer witness

This correctness-only diagnostic addresses a missing observation, not a failed
lock acquisition. The October 31 candidate mapping run completed 80,000
mmap/munmap pairs with all 16 workers joined and zero operation, VMA or context
errors, but failed its unchanged strict sleeping-writer requirement. Preserve
that failed receipt and raw log. A later test cannot change its verdict.

The frozen harness is `f4ae82cfdf053c679c5d09ee8e503a7919764c9b`; the compared
providers remain `f7a84065e84474380faa37eeadfdf534abd72a68` and
`22d62d5c13cad3c61c97dd47524da908769f1a52`. This diagnostic changes no production
source, built-in kernel, scored application, archive, or existing runner.

## Exact test boundary

One file binds the target task's actual `mm_struct` with `mmgrab`. A test-only
kernel thread takes an additional `mm_users` reference, acquires that mm's real
write lock, and waits for an explicit release or a fixed ten-second timeout.
It unlocks on its own task and releases its own reference exactly once. No
userspace copies occur while it owns the lock. No new production export or
instrumentation is added.

The target task executes an actual anonymous `mmap` system call and subsequently
`munmap`. An observer forked into a different mm controls the holder through the
same bound file, reads the target's proc task records, and releases the holder.
Thus the observer's own faults cannot depend on the held target mmap lock.
The target does not inspect or release its own held lock from userspace.
After fork the target locks/prefaults its current image and writable stack/data,
then sends a READY handshake before the observer starts the holder. Its held
interval uses inline raw syscalls, and the executable resolves PLT entries at
load time. This avoids making fork COW faults or lazy binding the intended
contended operation.

The client reuses byte-identical `task_state`, `chain_frame`,
`writer_observation`, and `writer_contention` functions from the frozen
`bench/mmap_writer/client.c`, plus its JSON string formatter. Only the proc reader
is supplied by this test: it names the explicit target process and imposes an
absolute observation deadline. Existing exact kernel ELF return offsets, two
`D` state samples, matching wait channel and unchanged nonempty scheduler
counters remain required. The Python validator reuses the original positive
chain verifier and rejects corrupted proof fields. A missing witness fails;
there is no retry or functional-policy fallback in this test.

Every path releases or times out the held lock, then joins the exact holder.
A ten-second bound starts after acquisition; it does not bound acquisition or
join if the underlying lock malfunctions. A runner deadline therefore retains
uncertainty and the module rather than reporting a completed cleanup.
A timeout, failed syscall, missing proof, unknown worker completion, retained
reference or kernel warning fails. Module unload is normal and only follows
actual file/worker/reference drain. A command timeout does not prove drain and
does not authorize force unload. The result identifies this artificial held
writer interval separately from ordinary workload behavior or parking rates.

## Separate prospective mapping continuation

The existing `mmap-functional-v1` policy may be selected explicitly for a new
correctness run. All six original mapping cases must complete, including the
previously unrun lifetime and exit cases. Exact work, identities, callbacks,
joins, positive-proof validation, teardown and kernel health remain required.
A missing ordinary sleeping snapshot is labeled `inconclusive`; arbitrary
nonzero exits cannot be converted to passes. The original strict failure stays
failed. This strict held-writer result remains a separate positive integration
witness, not an invented observation in the original 16-worker run.

Any later timing adapter must bind both new diagnostic receipts explicitly and
record compatibility with the already completed baseline's strict proof. It
must keep the original benchmark inputs, one-round grid, actual boot and source
identities, endpoint qualification and every measured loss. Neither successful
diagnostics nor user-authorized comparisons promote the candidate.

## Validation scope

Source edits and static inspection run on 380G10. Compilation and the live test
run only on the VM, after recovery, source identity and idle checks. The runner
retains extracted classifier bytes, source maps, module/client hashes, actual
writer-site proof, stdout, kernel log and final health. This new diagnostic is
unbuilt and unrun when initially committed; actual VM receipts supply its later
status.
