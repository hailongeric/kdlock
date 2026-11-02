# JIT continuation check

Run only in the verified recovery guest, following
[VM operations](../../../docs/operations/VM.md). The runner freezes the source,
including private `.inc` implementation files, and builds the provider, daemon,
allocator guard and [kernel payload](payload/README.md)
inside a new output directory. Source and binary hashes record the exact inputs.

## General killable admission mode

The selected-phase candidate adds a separate functional mode:

```sh
timeout 900s python3 tests/kernel/jit_continuation/run.py \
  --mode killable --family rwsem --cpus 0-3 \
  --output /root/kdlock-evidence/10.176.26.71/tests/killable-continuation-NEW
```

It reuses this runner's source freeze, module, allocator guard, daemon,
immutable-image audit and normal drain. The integer entry audit checks the
Native return jump over the captured `XOR EAX,EAX` success label. Its image
requires the explicit budget-resume and retained service-queue contracts
(requirements 384, image protocol 3). Existing
continuation modes retain their original bodies and phase sequence.

Eight preallocated diagnostic slots record original task IDs, API results and
body effects. Snapshots inspect canonical queue order/state under the object's
guard. Each queued cancellation runs with a callable writer still acquired;
head, middle and tail positions are controlled separately. A selected writer
also cancels while an ordinary reader retains its credit. Failure must return
`-EINTR`, unlink and finish rollback before the controller releases the holder.
The canceled user's `SIGKILL` exit is expected and retained alongside the
in-kernel API result and zero body prefix; it is not a successful user return.

A nested conventional killable call must observe the logical origin's signal
while remaining on the parent executor. Its canceled child has no prefix, its
parent retains its earlier effects and completes its successful acquisition,
and the inner holder remains acquired until that evidence is saved. A final
case downgrades on the executor, runs a bounded scalar read tail containing
`PAUSE`, and requires a fresh subsequent writer to drain that read credit.
Additional bounded cases acquire four distinct rwsem and four distinct mutex
children under the outer rwsem (total depth 9), release them outside reverse
acquisition order, release the outer while all eight children remain acquired,
and acquire/release one mutex child 128 times under a single outer. That last
case alternates conventional false and public clobber true requests; a separate
true-only case retains its own receipt. These permission controls still execute
on the same actual parent executor and do not claim migration to another child
executor.

Optional `service_trace` is enabled only for these short checks. Every positive
root needs matching `enter` and `returned` events with an exact nonzero request
identity/generation and an actual executor different from its original task.
Nested cancellation and downgrade/read-release events must name that executor
and the corresponding exact records. Child grant/release events retain distinct
invocation generations, requested delegation permission and actual depth. The
early-outer case requires all eight grants before outer release and every child
release afterwards. API timing or a published image cannot
substitute for these events. The generic API observer remains
`proxy_proof = false` and is not used to infer delegation.

All observations, including failed phases, remain in the output directory.
The controller never forces module removal or releases holders to turn a
failed cancellation into a pass. Diagnostic holders have a 30-second bound;
expiry records a failure before normal lock release. This mode reports no
performance scores, does not run the original RDTSC phases, and does not claim
MM execution. Source is unvalidated until matching VM receipts exist.

The active family is named `jit_continuation`. Its runner lives at
`tests/kernel/jit_continuation/run.py`, its module is `jit_continuation_test.ko`,
and its device is `/dev/kd_jit_continuation_test`. The payload's build controls
use `JIT_CONTINUATION_*`; the affected unit driver is
`infrastructure/test_jit_continuation_runner.py`. This naming update preserves
all ioctl command numbers, layouts, phase labels, result keys, runtime counters
and continuation semantics. Fixed results and archived source retain their
original names. The rename is not a fresh functional or performance result;
the basic and affected VM checks must run against the resulting source commit.

JIT means just-in-time compiled code used to execute a waiting task's work on
another lock holder. An instruction **marker** exits that code before an
instruction that must run on the original task. This check uses `RDTSC`, the
safe x86 instruction that reads the processor timestamp counter. It does not
exercise instructions that disable interrupts or change privileged settings.
With capability v13/bit13, an eligible sole-outer ABI2 mutex gate instead services
RDTSC on the original waiter and returns to the same immutable JIT image. That
gate also serves explicitly prepared rwsem writers; runtime has no separate API
family discriminator. Their write admission remains held through service and
reentry, while readers always execute locally. The runner checks the capability
explicitly; spin/rwlock and nested-spin cases retain the before-instruction
native-suffix expectation.

Set the verified snapshot variables and the pinned Python environment described
in the VM guide before running:

```sh
timeout 900s python3 tests/kernel/jit_continuation/run.py \
  --cpus 0-15 --iterations 100000 --warmup-iterations 100000 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-continuation-NEW
```

Add `--mutex-api public` to exercise literal `kd_mutex_lock/unlock` calls and
their exact native-continuation unlock routing. The default `outer` retains
the existing cookie shell. Public runs audit the compiled lock capture, named
continuation and unlock imports before loading the module; metadata and result
files keep the two shells distinct. Both execute the same warmup and four
asserted phases below.

`--family mutex --mixed-spin` adds literal public `kd_spin_lock/unlock` calls
inside the outer mutex. These macros emit the shared unpinned clobber shell.
It checks the one-CAS acquired path, original-task instruction escape
while the spin ticket remains owned by the executor, native unlock ACKs and
the restored task's preemption pin. The inner word must drain before each
phase transition. The outer mutex serializes all uses of this inner lock, so
this variant does **not** validate failed-CAS ownership transfer, the separate
DIRECT shell's inlined preemption/heat prefix, or multiple-owner transfer chains.
Production-code unit fixtures in `tests/unit/mutex/test_mutex_mixed.py` and
`tests/unit/execution/test_remote_outer.py` cover the physical owner exchange,
pending CALL, exact ticket and ACK ordering with scheduler/queue substitutes;
those substitutes are not live-kernel validation.

`--family spin` selects ordinary task-context ABI1 DIRECT acquisitions;
`--family rwlock` selects ABI3 DIRECT writers and concurrent local readers.
`--family rwsem` selects the unified prepared ordinary ABI2 writer and sleeping
local readers; its compiled capture is audited separately from historical OUTER
cookie callers.
The default remains `--family mutex`. Spin/rwlock runs require capability
version 12 or 13, both native-exit bit 5 and root-exit bit 11, and an immutable
generation with image requirements exactly 33. Older providers or a static
translation refusal cannot satisfy these positive probes. ABI2 images use
requirements 65 when the provider advertises original-task instruction service,
otherwise 1. Prepared rwsem writer gates expect the same RDTSC service/reentry
contract while preserving their reader exclusion. Only mutex supports the
public/OUTER selection and the extended four-instruction variant.

## Bounded original-task instruction reentry

`--family mutex --origin-instructions` adds a bounded four-instruction sequence:
RDTSC, RDTSCP, CPUID leaf 1/subleaf 0, and a second RDTSCP. It requires v13/bit13
and cannot be combined with nested spin or another lock family. Use the public
entry, for example:

```sh
python3 tests/kernel/jit_continuation/run.py --family mutex --mutex-api public \
  --origin-instructions --cpus 0-15 --iterations 10000 --warmup-iterations 10000 \
  --output /mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/origin-insn-NEW
```

Singleton-affinity workers sample Native RDTSCP TSC_AUX and CPUID leaf 1 outside
the protected interval. Both in-body RDTSCP results and all four CPUID outputs
must match that worker's Native values. CF/PF/ZF/SF/OF from a known CMP are
checked after each instruction, including a real conditional branch. LAHF would
itself end delegation, so eligible mutex and prepared rwsem writer bodies omit it. AF preservation is
covered by the full-flags runtime/codegen fixture, not this live payload.
Four per-instruction effect
counters, prefix/suffix and returned worker results must be conserved exactly.
These are functional observations, never benchmark scores.

Cold → taken → cold → taken must retain one image/generation. Each taken phase
requires completed JIT roots and exactly four successful waiter services and
four actual same-image reentry witnesses per delegated root. The ordinary mutex
RDTSC-only variant expects one of each. The service counters are mandatory cold
protocol witnesses, distinct from publication or inferred execution.

The extended variant then enables `origin_instruction_force_suffix` only while
idle. Every delegated root must execute the first instruction once through the
waiter service, record one post-instruction suffix transition, and record zero
JIT reentries/completions. The remaining body executes locally. The runtime's
validated post-instruction PC and instruction counter establish the no-replay
boundary; timestamps alone are not an instruction-execution counter. All four
body effects and flags still pass. The flag is cleared while idle and a final
cold phase must delegate again. Ordinary retirement retains exact frame/source,
queue, task and physical-owner obligations; the probe never weakens them.

This candidate is unvalidated until its VM receipts exist. It covers the three
bounded scalar instructions, not arbitrary instructions or helper reentry.

For example, after the same recovery and kernel-identity checks:

```sh
timeout 900s python3 tests/kernel/jit_continuation/run.py \
  --family spin --cpus 0-15 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-continuation-spin-NEW
timeout 900s python3 tests/kernel/jit_continuation/run.py \
  --family rwlock --cpus 0-15 --reader-count 2 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-continuation-rwlock-NEW
timeout 900s python3 tests/kernel/jit_continuation/run.py \
  --family rwsem --cpus 0-15 --reader-count 2 \
  --output /root/kdlock-evidence/10.176.26.71/tests/jit-continuation-rwsem-NEW
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

For rwsem, explicitly prepared ordinary `kd_down_write/up_write` reserve the
writer phase and drain accepted readers before publishing the mutex request. Native continuation uses the
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

The warmup and four asserted phases remain in one provider/source session.
The following taken-phase description applies to the before-instruction native
suffix controls. Eligible v13 sole-outer ABI2 writer gates instead require the exact
instruction-service/reentry counts described above:

1. `cold-warmup`: run with the unusual-instruction branch disabled, leaving it
   present in the code. The image must publish as `NORMAL`, which means ready
   for execution, and no instruction marker may be reached.
2. `cold-delegated`: repeat that workload and require positive, matching entry
   and completed-body counts. A completed body reached its matching unlock;
   publication alone is insufficient.
3. `hot-escape`: after all callers join, enable the branch and run contention.
   Require a validated instruction-exit count, an event naming this exact
   instruction address and one of the taken-phase worker tasks, and registry
   state `NORMAL`. Every delegated body in this phase must produce a marker;
   none may be reported as a returned JIT completion.
   Prefix/suffix counters, the original-task check and arithmetic condition-flag
   checks must still pass for every operation.
4. `cold-after-escape`: clear the condition only after the prior callers join.
   Require positive matching JIT entries/completions and zero instruction exits.
   This demonstrates that the earlier native suffix did not ban later requests.
5. `hot-repeat`: enable the condition again and require new positive matching
   JIT-entry/marker counts, zero JIT completions, and all native effect checks.
   This detects a one-shot marker or lost future eligibility.

Every asserted phase requires the same registry record, immutable generation,
code address and published image bytes. No re-preparation or replacement can
stand in for persistent eligibility. A before-instruction native marker finishes
the current invocation's entire suffix; the v13 bounded instruction service
returns eligible ABI2 writer invocations to the same image. Independent
entry bans remain sticky and are covered separately by the image/registry tests.

The mutex/rwsem controls accept capability versions 6 through 13 only when feature
bit 5 (native instruction exit) is present. Spin/rwlock require the additional
contract described above; the version alone does not establish support.
The private benchmark observation
overlay supplies entry/completion counts, including validated root completions
after helper services; the production `native_escape_count` counts validated
marker events. That count does not by itself prove that a native continuation
completed. The operation and final-retirement checks supply the additional
evidence. The marker log is rate limited, so the test does not require one
printed line per count or a printed event in each taken phase. Each taken phase
must independently increment its marker counter; all retained events must match
the exact image, instruction and writer tasks from those two phases.

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
five arithmetic condition flags carried from a comparison through an
unconditional branch, the marker exit and `RDTSC`. Native-suffix family/nesting
variants retain LAHF's additional AF check; eligible ABI2 writers omit that separate
native marker. See the payload README for the tested flag names and values.
Existing mutex ownership, release acknowledgements
and source-lifetime rules remain in force.

A timeout, kernel fault or caller-control error before every worker joins
preserves running callers and loaded modules for diagnosis. Barrier and receipt
I/O errors follow the same rule: before GO, a worker can hold a device reference
while the payload's active count is still zero. The affected
`infrastructure/test_jit_continuation_runner.py` unit driver exercises these failures
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
does not alter this instruction marker's continuation or repeated-eligibility checks.
