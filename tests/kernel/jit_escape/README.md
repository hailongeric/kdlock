# Conditional JIT instruction exit check

Run only in the verified recovery guest, following
[VM operations](../../../docs/operations/VM.md). The runner freezes the source,
including private `.inc` implementation files, and builds the provider, daemon,
allocator guard and [kernel payload](payload/README.md)
inside a new output directory. Source and binary hashes record the exact inputs.

JIT means just-in-time compiled code used to execute a waiting task's work on
another lock holder. An instruction **marker** exits that code before an
instruction that must run on the original task. This check uses `RDTSC`, the
safe x86 instruction that reads the processor timestamp counter. It does not
exercise instructions that disable interrupts or change privileged settings.

Set the verified snapshot variables and the pinned Python environment described
in the VM guide before running:

```sh
timeout 900s python3 tests/kernel/jit_escape/run.py \
  --cpus 0-15 --iterations 100000 --warmup-iterations 100000 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-escape-NEW
```

Add `--mutex-api public` to exercise literal `kd_mutex_lock/unlock` calls and
their exact native-continuation unlock routing. The default `outer` retains
the existing cookie shell. Public runs audit the compiled lock capture, named
continuation and unlock imports before loading the module; metadata and result
files keep the two shells distinct. Both execute the same four phases below.

`--family spin` selects ordinary task-context ABI1 DIRECT acquisitions;
`--family rwlock` selects ABI3 DIRECT writers and concurrent local readers.
`--family rwsem` selects the existing ABI2 OUTER writer and sleeping local readers.
The default remains `--family mutex`. Spin/rwlock runs require capability
version 12, both native-exit bit 5 and root-exit bit 11, and an immutable
generation with image requirements exactly 33. Older providers or a static
translation refusal cannot satisfy these positive probes. Mutex/rwsem runs retain
their requirement-1 image; only mutex supports the public/OUTER selection.

For example, after the same recovery and kernel-identity checks:

```sh
timeout 900s python3 tests/kernel/jit_escape/run.py \
  --family spin --cpus 0-15 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-escape-spin-NEW
timeout 900s python3 tests/kernel/jit_escape/run.py \
  --family rwlock --cpus 0-15 --reader-count 2 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-escape-rwlock-NEW
timeout 900s python3 tests/kernel/jit_escape/run.py \
  --family rwsem --cpus 0-15 --reader-count 2 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-escape-rwsem-NEW
```

Rwlock/rwsem default to one reader, using the last selected CPU. `--reader-count`
can reserve more of the selected CPUs, while retaining at least four writers.
Every phase waits for all workers to report readiness before releasing a shared
start barrier and checks every worker's exact progress. Readers default to ten
million operations per phase (`--reader-iterations`), so they can continue
competing through the writer phase. Every hot writer additionally waits a bounded
number of polls for an announced unfinished read attempt before the named marker; zero
worker errors requires that overlap for every hot operation, including each
delegated marker. This announces a request; it does not prove queue membership.
Read completion is recorded inside shared ownership, and the writer explicitly
requires its completion snapshot to remain unchanged through the native suffix.
Early reader exhaustion or missing overlap fails the probe.
Reader operations use a separate READ ioctl and hold shared access
while checking that no writer is active and prefix/suffix values agree.
Writers check that no reader is active at entry and before release. Only writer
operations contribute to prefix, suffix and taken-branch totals or qualify as
marker-event tasks. Joined readers, zero active counts, zero rwlock admission
count and a clear embedded gate are required before phase changes and retirement.

For rwsem, the OUTER wrapper reserves its writer phase and drains accepted
readers before publishing the mutex request. Native continuation uses the
unchanged ABI2 protocol; the original task releases the reservation only after
the gate unlock ACK. The body checks positive admission, which can include other
outer writers, and the probe's accepted-reader count. It does not demand a zero
internal reader count during the body: rejected readers can briefly publish a
speculative count without accessing the payload. After all workers join,
`kd_rwsem_is_idle()` must confirm zero reservations/readers, empty wait queues
and an idle gate. This probe adds no rwsem control ledger, cancellation,
downgrade, mmap integration or fault continuation.
The body observations do not independently isolate reservation release versus
unlock ACK: another writer's reservation could mask an early release of this
writer's reservation. That ordering remains a provider protocol obligation
supported here by source inspection, not an independent result of this probe.

Spin/rwlock workers must start with preemption and IRQs enabled and singleton
CPU affinity. Each returned operation must preserve its CPU, full preemption
count, IRQ state and non-arithmetic processor flags. These observations stay
outside the captured critical section. In the hot native suffix, `RDTSCP`
records TSC_AUX after all arithmetic-flag observations; it is compared with a
native baseline on the same pinned worker CPU without assuming TSC_AUX's
encoding. The named first marker remains `RDTSC`, and the suffix still records
the physical current task. These new families do not use IRQ/BH lock variants,
nested acquisition, cancellation or a checked memory-fault continuation.

The four phases remain in one provider/source session:

1. `cold-warmup`: run with the unusual-instruction branch disabled, leaving it
   present in the code. The image must publish as `NORMAL`, which means ready
   for execution, and no instruction marker may be reached.
2. `cold-delegated`: repeat that workload and require positive, matching entry
   and completed-body counts. A completed body reached its matching unlock;
   publication alone is insufficient.
3. `hot-escape`: after all callers join, enable the branch and run contention.
   Require a validated instruction-exit count, an event naming this exact
   instruction address and one of these worker tasks, and the terminal registry
   state `NATIVE_ONLY`. That state disables future delegation for the entry.
   Prefix/suffix counters, the original-task check and arithmetic condition-flag
   checks must still pass for every operation.
4. `post-ban`: after the prior callers join, run the same taken branch again.
   Neither generated-code entries nor instruction exits may increase, and the
   registry must remain `NATIVE_ONLY`. Operations still execute correctly on
   their original tasks.

The mutex/rwsem controls accept capability versions 6 through 12 only when feature
bit 5 (native instruction exit) is present. Spin/rwlock require the additional
contract described above; the version alone does not establish support.
The private benchmark observation
overlay supplies entry/completion counts, including validated root completions
after helper services; the production `native_escape_count` counts validated
marker events. That count does not by itself prove that a native continuation
completed. The operation and final-retirement checks supply the additional
evidence. The marker log is rate limited, so the test does not require one
printed line per count.

Version 11's optional [direct original-helper route](../../../docs/design/admission.md#direct-original-helper-calls)
is a separate ABI1 spin feature; it does not change this ABI2 mutex marker or
the selected mutex protocol. This probe remains an affected regression check,
not a measurement of direct-call performance. It passed and drained in
[candidate 2](../../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-2-checks).
The final bridge's [candidate 3 checks](../../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks)
passed separately; they did not rerun this unchanged mutex path. The separate
[direct-route comparison](../../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed 567 validated sessions for read-only taskname and xattr tail with 16
and 128 entries. Those spin workloads do not measure this mutex marker path.

Every phase records worker process identifiers, exact per-worker progress,
counter snapshots, registry state and kernel messages. The payload checks all
six arithmetic condition flags carried from a comparison through an
unconditional branch, the marker exit and `RDTSC`; see its README for the flag
names and expected values. Existing mutex ownership, release acknowledgements
and source-lifetime rules remain in force.

A timeout, kernel fault or caller-control error before every worker joins
preserves running callers and loaded modules for diagnosis. Barrier and receipt
I/O errors follow the same rule: before GO, a worker can hold a device reference
while the payload's active count is still zero. The affected
`infrastructure/test_jit_escape_runner.py` unit driver exercises these failures
through the production phase and cleanup dispatcher with substituted callers.
These failures do not prove that work finished and do not authorize forced
unload. Successful completion requires workers to join, zero active execution
records, successful source retirement, ordinary module unload, and final idle
inspection. This is a focused correctness check; no throughput result is claimed.

This check covers the selected KD mutex/rwsem ABI2 instruction-marker path and the
separately negotiated ordinary spin/rwlock root-marker paths. The
[spin address-guard probe](../spin/address_guard/README.md) and
[original strcmp service probe](../spin/string_service/README.md) exercise
separate negotiated boundaries. Their feature bits do not authorize arbitrary
instruction traps, memory faults or replay of a partially executed body.
The string probe now requires valid short and 300-character inputs to complete
delegated comparison calls, without the former helper prechecks. That change
does not alter this instruction marker's continuation or permanent-disable checks.
