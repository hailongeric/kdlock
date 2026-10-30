# mmap1 object identity observation

This unscored probe observes the unchanged pinned will-it-scale executable at
`vm_mmap_pgoff` entry. It accepts only the testcase's anonymous 128 MiB,
read/write, private mapping arguments and the selected upstream task name. It
records the actual current PID/TID and task start time, `current->mm`,
`&mm->mmap_lock`, selected physical backend address, backend field and CPU.
The field types come from the exact verified running kernel build headers.

A fixed 128-entry table records each task lifetime once. The probe takes one
`mmgrab` per record to prevent recorded object reuse until observation ends.
Stopping unregisters the kprobe (waiting for handlers) before dropping those
exact references. The stop ioctl returns a frozen table and acquired/released
reference totals. Overflow, duplicate-lifetime inconsistency, a missing worker,
wrong backend, or an unmatched `/proc` task identity fails the observation.
There is no allocation, scheduling, MM body rewrite or lock replacement in the
probe handler. A private native raw spinlock serializes only this diagnostic
record table. None of this is present in scored runs.

The runner builds only in the development VM, freezes probe/runner sources,
verifies schema-2 kernel and boot identities, loads the observer for each model,
and invokes the original prepared mmap1 executable through the benchmark
runner's normal lifetime helper. Two workers prove one shared mm for threads
and two distinct mms for processes. Counts from these instrumented executions
are not performance scores. The observer is stopped and exact references
released before normal module unload. Failure or timeout preserves evidence
and does not imply drain or authorize forced unload.

The payload snapshot excludes generated `*.mod.c` files. Kbuild regenerates
those files in the copied build directory, so treating an old generated file as
an immutable source input causes the subsequent source check to fail before
the observer or application starts. The real payload `.c`/`.h` files and
Makefile remain captured and verified.

A frozen comparison cohort may execute an explicitly hash-bound external copy
of the corrected diagnostic runner. Record its distinct source commit and byte
hash, and bind both the executed path and its retained copy in `result.files`.
The ordinary scored runner can then recheck those exact diagnostic inputs while
the cohort's provider, original mmap1 executables and validators stay frozen.

This is a **diagnostic class proof** for those observed process lifetimes. Its
pointer values do not identify the different processes of a later scored
campaign. The scored runner records that limitation explicitly. A kprobe at
entry establishes the object and declared immutable backend for the mapping
call; it does not prove that security checks passed, that lock acquisition
succeeded, that a delegated body ran, or that every mapping was later unmapped.
Existing actual-MM correctness probes supply the separate semantic checks.
