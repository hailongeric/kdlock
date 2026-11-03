# mmap1 object identity observation

This unscored probe observes the unchanged pinned will-it-scale executable at
`__x64_sys_mmap` entry, using its pointer to the syscall register frame. It
accepts only the testcase's anonymous 128 MiB, read/write, private mapping arguments and the selected upstream task name. It
records the actual current PID/TID and task start time, `current->mm`,
`&mm->mmap_lock`, selected physical backend address, backend field and CPU.
The field types come from the exact verified running kernel build headers.

ABI2 preserves those record fields in order and appends the immutable provider
pointer and route: 0 for Native, 1 for builtin KD, and 2 for a module provider.
The pointer is observed while the originating task holds its mm lifetime;
the probe's existing retained mm reference prevents later address reuse.
Route 2 establishes object binding only. Actual other-task execution still
requires exact retained request enter/returned events joined to this task
lifetime and backing lock; downgrade/read-tail events remain separate evidence.

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

This is a **diagnostic class proof** for those observed process lifetimes. Its
pointer values do not identify the different processes of a later scored
campaign. The scored runner records that limitation explicitly. A kprobe at
entry establishes the object and declared immutable backend for the mapping
call; it does not prove that security checks passed, that lock acquisition
succeeded, that a delegated body ran, or that every mapping was later unmapped.
Existing actual-MM correctness probes supply the separate semantic checks.

## Delegated diagnostic controller

`delegated.py` composes the ordinary provider preparation, translation daemon,
complete builtin writer-site prewarm, explicit execution-session verifier,
unchanged `run_point(diagnostic=True)`, and this observer. It runs exactly one
two-worker lifetime per thread/process model, with no performance acceptance.
The native MM bodies and upstream source/binaries remain unchanged. It builds
and runs only in the designated VM; host source inspection is separate.

In addition to the existing explicit KD/boot/kernel/host/input arguments, the
controller requires hash-bound clean source-state and source-manifest files,
an exact runtime source commit, and a 380G10-produced site audit. The audit is
schema1, with `kernel_component_source_commit`, `vmlinux` containing path/bytes/
sha256/build_id, `section` containing name/start/end/sha256, a complete `records`
list of `{entry,operation,reserved,function,aliases}`, and `entry_sites` containing
nonempty `mmap` and `munmap` entry lists. Entries are JSON integers. The host
decodes the exact built ELF interval between `__kd_rwsem_sites_start` and
`__kd_rwsem_sites_end`; the input section can be merged into `.rodata`. The
interval size must equal 16 times the record count, operations are 1/3 and
reserved is zero. Exact-bound function aliases are retained; the operation
subsets identify `vm_mmap_pgoff` and `__vm_munmap`. The supplied audit hash binds
that host artifact to the verified schema2 vmlinux hash/size/BuildID. Historical
addresses from another kernel are refused.

```text
PY tests/kernel/mmap1_identity/delegated.py \
  --inputs PREPARED_INPUTS/inputs.json --inputs-sha256 HASH \
  --source-commit EXACT_RUNTIME_COMMIT \
  --source-state SOURCE_STATE --source-state-sha256 HASH \
  --source-manifest SOURCE_MANIFEST --source-manifest-sha256 HASH \
  --sites HOST_SITE_AUDIT --sites-sha256 HASH \
  --mode kd --kernel-variant kdscope5-kd --boot-id CURRENT_BOOT_UUID \
  --kernel-source /mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build \
  --kernel-baseline /root/kdlock-kernel-baselines/linux70-kdscope5-kd-20261103 \
  --host-state FRESH_HOST_STATE --host-reference HOST_REFERENCE \
  --host-reference-sha256 HASH --output FRESH_DATA2_OUTPUT
```

The controller and daemon start before activation and keep their original mms.
The preparing controller writes `prepare` itself, then waits with a deadline
for exactly every audited site to become ready under its actual TGID. It
captures the resulting immutable registry/images, activates the generic
factory, and only then launches the original fresh application exec. There is
no task-name-specific provider selection and no partial-site activation.

Continuous bounded kmsg collection covers provider load through final unload;
run_point also continuously drains its own diagnostic cursor. The observer
STOP/decode runs in-process, preserving its repeated equal buffers and exact
mm reference totals. Completed roots must match the actual observed worker
MM/backing and distinct origin/executor identities for mmap and munmap.
Returning primitive transactions must preserve root/image identity, actual
O-side execution and same-E return. GS memory transactions also pair exact
instruction/SP/operand identity and done-to-resume values/flags. Each family
requires sequences from one through its last observed sequence, with no gaps
or unmatched worker-root events. Other complete worker MM roots are counted
separately from the mmap/munmap subset; an actual zero service count remains
zero rather than implied coverage. The report keeps actual episode counts and
enter-to-return wall ns, including Native services and observation overhead;
it does not call this JIT-active time or physical batch length.

After normal app exit and observer STOP, the controller deactivates the
factory and requires bindings/frames to drain before normal daemon closure,
writers0, source RETIRE and normal module unload. A timeout, missing image,
unsupported continuation, log loss, unmatched root or failed lifetime check
retains the current state; it never authorizes forced unload or task exit.
The second model gets a fresh provider/source session. Scored comparisons
still require their existing separate correctness and host endpoint receipts.

## Bounded syscall-return pairing

The optional `pair_limit` observation defaults to zero, preserving the ordinary
entry-only observer and its ABI2 snapshot. A nonzero value, at most eight,
observes that many complete 128MiB mmap/munmap pairs per recorded task lifetime.
Two external kretprobes surround `__x64_sys_mmap` and `__x64_sys_munmap`, outside
the translated MM call graph. They retain the original six mmap arguments,
actual originating task/start/MM/backing identity, per-task invocation sequence,
returned address and matching munmap result. Auxiliary state is preallocated;
the native MM bodies, application and production provider remain unchanged.

Bounded entry/return markers share the continuously collected kmsg stream with
the existing executor trace. The parser assigns each audited root identity and
generation to the unique open syscall for that origin lifetime, requiring its
other-task enter/release-or-read-tail/returned sequence before the origin's
matching wrapper return. This distinguishes executor completion from actual
origin-side syscall-function return. A successful mmap address must be the
same address passed to successful munmap. The original application must still
exit normally with valid positive progress counters.
At least one sampled munmap invocation must contain the exact delegated
downgrade/read-release/returned sequence before its origin wrapper returns.
An unrelated read tail elsewhere in the lifetime cannot satisfy this sample.
The existing subsequent-same-executor writer criterion remains separate and
does not imply an independently observed reader-drain experiment.

STOP closes admission and unregisters every probe before dropping the existing
exact MM references. Its one-time summary records both kretprobe instance misses
and underlying kprobe misses, unfinished invocations and completed pair counts.
Any miss, unfinished pair, identity change or incomplete marker stream fails
pair coverage. Repeated STOP keeps the existing equal ABI2 buffers. Sampling
limits remain explicit; these observations do not account for every application
invocation or directly inspect VMA/page-table effects. No probe handler walks
VMAs, takes a blocking mmap lock, allocates or sleeps. These are unscored
diagnostics requiring their own frozen source and VM fixture results.
