# Project goal and three-stage development plan

The goal is relevant in-kernel lock replacement and evaluation of unchanged
applications such as will-it-scale `mmap1`. This roadmap defines deliverables
and completion gates. [VM operations](operations/VM.md) owns execution procedures;
[workloads](BENCHMARK_WORKLOADS.md) defines implemented benchmarks, and
[open work](TODO.md) records present limitations.

## Ultimate goal

Replace declared groups of Linux spinlocks, mutexes, rwlocks and rwsems while
preserving their required API, context and lifetime behavior. Evaluate complete
applications on matched Native and KD kernels. Loading a provider or measuring
an extracted critical section does not complete kernel replacement.

| Stage | Required evidence | Current position |
| --- | --- | --- |
| 1. Lock mechanism | Correct local/delegated execution and repeatable gains in a declared favorable regime, with adverse cases reported | Functional coverage and favorable exploratory nano cases; repeated current confirmation remains open |
| 2. Scoped MM | Actual mmap/fault correctness plus predeclared improvement or parity against Native | Linux 7 shared-MM checks and timings complete; Native faster at every measured count |
| 3. Broader integration | Complete declared call-site replacement and unchanged-application comparison | Planned |

## Current position

The [Linux 7 catalog](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
covers 52 lock/API configurations and three MM suites: 3,402 selected observations.
The 29 checked-source, 22 trusted-source and one prepared lock/API configurations
retain separate frozen identities. Private-MM and shared-MM kernels also remain
separate. This closes selected one-round coverage, not a repeated baseline or
a performance acceptance gate.

Current KD mutex defaults are total cap 1024 and NUMA boundary 1024; KD spin
retains its 1024-body limit. The user selected equal limits on October 28 to
remove the earlier count-based local cutoff. The favorable nano bodies are one
or sixteen padded counters with 256 post-unlock rounds. Their recorded
768-boundary evidence does not establish performance under the new default.
[Performance](PERFORMANCE.md) includes losses and local `NO_JIT` results as well
as returned-body wins.

The normal development kernel is `7.0.0-38-kdlock1`; its mmap backend is disabled.
The separate `7.0.0-38-kdmm1` image runs the actual adapter in Native/KD modes.
Native MM bodies remain unchanged and execute on their original task. Linux 6.1
adaptation, operation-specific MM delegation and prepared teardown are retired.

Bounded runtime repairs preserve PAUSE and later image eligibility after
supported native-escape instruction markers, and retain Native inner/context
CALL boundaries and ordinary spin context compatibility. Address-guard fallback
still disables the entry. Typed original-task RDTSC/RDTSCP/CPUID services can reenter
the same JIT in their documented ABI2 scope; generic Native CALL fallback still
finishes the waiter suffix. These implementations do not establish arbitrary
branch-only return or close the selected syscall, MM or performance gates. The
[f7 focused checks and 210-point nano record](../bench/results/10.176.26.71/bench/continuation-perf-nano-20261030/README.md)
retains observed losses and false performance acceptance. The subsequent
[original-body syscall comparison](../bench/results/10.176.26.71/bench/kernel-api-f7a84065-20261030/README.md)
completed all 126 sessions and 63 pairs: 40 KD gains and 23 losses, with separate
scoped functional JIT evidence. It does not close the performance gate. Later
MM comparisons are authorized on that isolated candidate and remain pending. See
[the current limitations](TODO.md#current-implementation-gaps).

## Stage 1: establish the mechanism and performance envelope

Use the ten maintained nano profiles and the existing micro/API cases. Compare
Native, supported TCLock and KD on the same payload, call shell and CPU placement.
Keep a callable/local KD control distinct from a delegating interface. Readers
of rwlock/rwsem execute locally; a reader-policy gain is not a delegation gain.

Every claim requires exact data, progress, source and binary identity, physical
ownership, unlock ACKs and final retirement. Measure returned bodies separately
from entries and publication. Collect profiles in separate labelled runs before
attributing an effect to batching, cache traffic, scheduling or NUMA locality.

### Stage 1 completion

Confirm a repeatable mutex gain over Native on a declared count set. Include
uncontended and adverse points, matched controls and repeat variability. Record
TCLock where its API is equivalent. Rwlock and rwsem require their own local
reader/writer and delegated-writer evidence; a mutex win does not validate them.

## Stage 2: prove scoped MM improvement or parity

### Integration boundary

Use the [Linux 7 mmap adapter](../kernel_integration/linux70/MMAP.md) to change
the lock backend and minimal API/lifetime wrappers. Every user of one mm follows
its backend selected before publication. Preserve reader concurrency, killable
acquisition, downgrade, exact asynchronous read-release references and teardown.
Native mmap/munmap/advice/fault algorithms stay on the original task.

The adapter uses local KD readers and writers. Nano JIT batching therefore does
not explain its current behavior. Profile actual phase admission, reader drain,
writer handoff and wake/retry costs before selecting an optimization. Mmap's
killable path bypasses the ordinary uninterruptible polling stage.

### Workload matrix

| Workload | Operation and topology | Status |
| --- | --- | --- |
| `mmap1_threads` | Shared-mm threads; repeatedly map/unmap an untouched 128 MiB anonymous private read/write range | Runner implemented; matched actual-backend comparison pending |
| `mmap1_processes` | Same operation in independent processes/mms | Separate runner model implemented; matched comparison pending |
| Actual minor faults | Precisely declared access/reset method on actual Native/KD mmap backends, with backing implementation fixed | Generic throughput driver still needed |
| Existing shared-mm device test | Shared-mm threads; untouched 4 KiB read-only shared device mmap/munmap | 42 Linux 7 points complete; KD below Native at all counts |
| Existing private backing faults | Independent mms; reset PTE and read a checked preallocated page | Supporting experiment; actual mmap lock stays Native |
| Existing independent-mm device test | Untouched device mmap/munmap in independent processes | Native control; no backing-lock work in timed operation |

The [implemented mmap1 runner](../bench/mmap1/README.md) uses unchanged upstream
`75f66e45697e6f5f49c33dd950c4e6b289198f8f` executables, with frozen build reuse
and a separate actual worker/mm identity observation. Implementation alone is
not a completed application comparison or MM performance result.

`MAP_PRIVATE` does not create a separate mm for each pthread. Sharing an fd does
not establish a shared mm either. The 4 KiB device test and reset-plus-read
fault cycles must not be relabelled as `mmap1` or isolated fault latency.

### Implementation sequence

1. Freeze the benchmark revision, source/configuration, executable, backend mode,
   CPU/NUMA placement, counts, duration, repetitions and performance criterion.
2. Prepare one unchanged `mmap1` executable for both modes, keeping thread and
   process results separate and checking actual backend/mm identity.
3. Run basic plus affected correctness/lifetime checks before timing. Validate
   cancellation, downgrade, fork/exit and required read-share transitions.
4. Prepare one fault class with explicit setup/reset/touch costs and an exact
   data/fault-count oracle. COW, major faults and retry variants are separate cases.
5. Diagnose the shared-MM loss with separate bounded profiles, make one justified
   change, and retain both baseline and candidate, including regressions.
6. Confirm the declared primary cases in a separately planned repeated comparison.

### Stage 2 completion

Correctness and performance have separate gates. Declare an allowed regression
`epsilon` before measuring; parity means `KD/Native >= 1 - epsilon` on the required
count set with enough repeated evidence to assess uncertainty. A proposed 5%
tolerance is a planning choice, not a current runner rule or accepted result.
The primary thread/fault cases and process control must meet their declared
requirements. A private-backing gain cannot offset an actual shared-mm loss.

## Stage 3: replace relevant kernel locks and evaluate applications

Inventory object groups and every API participant before conversion: construction,
static initialization, layout, aliases/callable symbols, try/signal/killable/I/O,
nesting, IRQ/BH/preemption, downgrade, non-owner release and destruction. Convert
all users of an object together. Unsupported groups remain entirely Native.

Retain KD physical exclusion, ABI2, the 32-byte mutex, preallocated separate queue
memberships, exact waiter/executor pin lifetimes, immutable mutex images and exact
owner/source/ACK/frame retirement. Runtime context obligations remain even though
production trusts source and skips semantic analysis. Trust adds no missing ABI
or backend support. The October 29 requested pin-on-proxy handshake is tracked
in [open work](TODO.md#october-29-api-and-execution-work); it is not yet baseline
behavior. PREEMPT_RT, debug mutexes and lockdep configurations are explicitly
excluded. Whole-kernel replacement and ww_mutex require separate integration;
oversubscription remains deferred.

Deliver a reviewable kernel patch/configuration and coverage map, then compare
unchanged applications on matched kernels. TCLock is an optional comparator
only where a compatible actual-kernel integration exists; the current module
port does not supply a general mmap backend.

## Measurement and decision rules across stages

Keep source versions, topologies, call shells, workloads and instrumentation
separate. Preserve every failure and unrun coordinate. `NORMAL`, entered JIT,
returned JIT, correct data, drain and timing qualification are distinct.

The completed catalog uses one two-second round per point, fixed 2 GHz host
policy and an explicitly exploratory auxiliary-worker policy. Strict timing
qualification remains failed; no repeat variance is available. New confirmation
work needs its own declared policy and repetitions. Publish each workload's table
and chart at its completed boundary. A timeout does not establish drain.

## Milestones and next actions

| Next deliverable | Remaining work |
| --- | --- |
| Stage 1 confirmation | Repeated favorable/adverse nano comparison with local controls |
| Exact `mmap1` | Execute the implemented pinned runner with actual worker/mm identity; keep Native/KD and thread/process results separate |
| Actual fault throughput | Defined fault class, fixed backing implementation and exact accounting |
| Scoped MM acceptance | Correctness plus declared improvement/parity; current loss remains unresolved |
| Broader replacement | Per-object API/lifetime coverage and matched application evaluation |

Operations follow the concrete task authorization and [VM rules](operations/VM.md).
This roadmap does not authorize kernel changes, installation or reboot by itself.
Superseded campaign plans and paper/artifact comparisons are indexed in
[history](history/README.md), not active execution instructions.
