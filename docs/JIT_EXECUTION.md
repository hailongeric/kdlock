# JIT execution flow

This guide follows ordinary requests. Family-specific acquisition belongs in
[spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md),
[rwlock](design/rwlock_implementation.md) and [rwsem](design/rwsem_implementation.md).
[Translation policy](design/admission.md) defines trusted source; the
[register ABI](JIT_REGISTER_ABI.md) defines machine-state capture and exits.
The selected [lock replacement contract](design/kdlock_lock_replacement_contract.md)
defines general current-position handback. Its retained-worker runtime wiring
is committed, with production checkpoint `da55414f` and subsequent focused
component passes. The later `58af0a53` probe passes cold CALL and indirect-JMP
handback but fails its overall checker at a post-RET continuation. Candidate
`bccf877c` records subsequent harness fixes. The later bounded mmap1
[learning run](../bench/results/10.176.26.71/tests/mmap1-continuation-2d8eb6e3-20261109/README.md)
ends at its settlement deadline and recovers normally, without accepted
throughput. The [release-unit correction](../bench/results/10.176.26.71/tests/release-units-40edde00-20261109/README.md)
passes focused component checks and a provider build; it has not been loaded
or measured.

## Preparation and entry

1. Register the continuation and matching backend/ABI after its source is live.
   Unified direct mutex calls may register their internal numeric continuation.
2. Decode leased text within the original bounded selected graph and publish a
   complete image for that scope. A complete kernel CFG, eager ordinary-callee
   closure and all-site MM prewarming are not required. Kernel/module source is
   trusted; semantic context, loop/value and entry-input proofs are not run.
   Ordinary string callees use generated CALL/RET without named helper routes.
3. Attempt the family-specific physical acquisition. A hot caller may still
   acquire locally without a frame. Delegation also requires a ready image,
   correct runtime context and available request/ticket resources.
4. A published waiter release-orders its shared frame/packet and queue membership.
   It polls pinned on its reserved stack. The executor uses that existing packet;
   it does not copy a second request to simplify lifetime accounting.

Publication makes a request eligible for possible combiner execution. It is not
an irrevocable delegation decision: a waiter receiving physical ownership may
execute its own body and serve other requests as combiner. Local selection and
remote execution must claim the same exact request exclusively before effects.
The ordinary KD mutex queue implements this local-versus-proxy election under
its wait lock. Retained service roots currently use a separate route: after
admission commitment, a service worker claims the root and the origin transfers
its gate to that worker. They do not yet join the ordinary local/combiner
election. This is an actor-selection gap, not a property established merely by
publishing a request, and the release-unit correction does not resolve it.

Ordinary spin/rwlock pairs protect preemption and IRQ/BH state. Explicit spin
IRQ/BH variants are local. Published mutex waiters are pinned even though physical
owners and supported service paths may sleep. Heat never authorizes ownership.

## Batch execution and return

A combiner holds physical exclusion while selecting requests. Each request keeps
its exact ticket/acquisition, frame and image binding. Batch preparation checks
layout, ABI, packet and supported simple-path conditions. A refused preparation
leaves the prior binding unchanged. An existing source lease may cover the batch,
but each request still needs readiness and exact owner checks.

Rwlock ABI3 acquires exclusive writer admission before the first body. An unstarted
refusal cancels it while retaining the gate; a native retry must reacquire it.
A progressed native remainder keeps admission until its matching writer unlock.
Rwsem outer writers reserve/drain before entering the mutex queue.

The terminal clobber unlock can complete with IP/SP/BP only. If its exact fast
completion conditions do not hold, the wrapper constructs the original CALL once,
materializes FULL and uses the dispatcher. Supported controls/scalar services may
resume at validated continuations. An ordinary untranslated callee finishes the
remaining invocation on the origin; it does not resume JIT after arbitrary native
work or reset the body.

Retained ABI2 service images end a source unit at every recognized release,
including a nested or unrelated release, a typed Native release and downgrade.
The compiler does not pair releases with acquisitions. A release inside a callee
also ends that path; its caller's original suffix is retained only when the
callee has a release-free return path. Generated exit/dispatch code does not
authorize original source after the release in that unit.

Runtime performs the real release and completes its CALL exactly once. If all
required owners are released, ordinary final completion applies. Otherwise the
exact saved post-release IP/SP and complete packet use the existing native
handback with remaining owners and source/image lifetimes intact. Downgrade
keeps its real read credit through the native read tail and matching read
unlock, without reacquisition. This route does not implement separate nested
JIT images or JIT-to-JIT continuation units; a full-root returned-JIT counter
may remain zero even when the native tail completes correctly.

Supported instruction markers resume the origin before the selected instruction
with the declared arithmetic flags. Prior stores and locks remain owned; the entry
retains its existing eligibility for later invocations. The optional ABI2
original-task instruction service instead retains node/frame/owner through an
intermediate ACK and resumes the same image after exact RDTSC/RDTSCP/CPUID.
Its source, flags and remaining-budget contract is separate from a native suffix.
Generic faults, the legacy untyped IJ-error path and budget errors are not
arbitrary recovery boundaries. The negotiated current-position miss path below
has its own packet and ownership requirements. Optional address guards and old
string-service/direct-call routes belong to checked/historical compatibility,
not current trusted-source emission.

## Current-position handback and implementation status

The required correction uses exactly the original translator, original GS
lowering, wrapper and daemon. O is the origin and E is the physical executor.
On untranslated code, O resumes at the first
source instruction E has not executed, with current IP/GPR/SP/BP. Preserve
completed stores and all ownership obligations. A CALL that already pushed its
source return word resumes at its target without another push. A RET that
already popped its source word resumes at the resulting target without another
pop or adjustment. An unexecuted source instruction resumes at that instruction.
No progressed body restarts from entry.

Actual indirect CALL/JMP/RET edges use IJ miss learning with their source-site
and target identities. Direct untranslated callees retain CALL miss learning.
The daemon updates later replacement images; the current invocation neither
waits for that image nor reenters it after ordinary native suffix execution.
Bound immutable generations and source leases remain retained independently of
publication and each owner's final unlock/ACK.

Checkpoint `ebae17c1` adds the negotiated current-position packet for eligible
cold ABI2 images and routes ordinary misses through existing native handback.
The later source checkpoint `10ef078a` removes the separate reached emitter/
cache/dispatcher and corrects the cold miss header. Runtime `a6fe0bb2` consumes
`KD_EXE_RUN_HANDOFF` in the retained worker, registers exact Native owner routes,
accepts the origin's copied packet and performs typed release/ACK handling
before synchronous retirement. At `da55414f`, production acceptance, typed
release, final ACK and terminal retirement pass a three-mode component join.
Task/physical primitives are supplied, recursive unwind is represented manually,
and root storage remains accessible until thread joining. This is not a live
kernel/JIT stack-switch result.

General flags/SIMD restoration and IRQ/NMI conflict handling are deferred and
unsupported in this phase. Existing typed flags contracts remain distinct.
`KD_EXE_RUN_ERROR` and executed-state BUG checks cannot be relabelled as a
successful handback or removed to conceal a missing path. The owner's focused
`ebae17c1` checks include passing packet/dispatcher fixtures, eight returning-call
failures and a mutex-image fixture compile failure. The W=1 provider build
returns zero with objtool warnings; the overall receipt fails and loads no
module. The [validation record](design/kdlock_lock_replacement_contract.md#validation-and-remaining-work)
separates those earlier results from the later partial live probe and absent
current timing acceptance. Historical reached-emitter receipts apply only to
their recorded source and backend. The first frozen `a6fe0bb2` receipt builds the provider and
passes seven component groups, but the query-image assertion and retirement
fixture compilation fail. It loads no module and reboots nothing. Its
[first result table](design/kdlock_lock_replacement_contract.md#first-frozen-runtime-checks-at-a6fe0bb2)
preserves those failures separately from the earlier receipt. Subsequent
[source-specific results](design/kdlock_lock_replacement_contract.md#current-focused-component-results)
resolve the observed failures: query images and retirement at `da55414f`, OSQ
at `615cdb0b`, and resources at `2bfbb8dc`. The later fixture revisions have
identical production trees; these are separate runs, with no new live or timing
result. A narrow saved-state restore fixture pass does not close the deferred
general flags/SIMD or IRQ/NMI coverage.

### Selected query and retirement boundaries

The selected state-query policy keeps `kd_mmap_assert_held_write`,
`kd_mmap_assert_held` and `kd_mmap_is_locked` in the original JIT. It does not
force their entire downstream chain. The exact runtime proof at
`kd_service_write_owned` retains the selected existing `ATOMIC_ORIGIN` Native
interval; other query/Native services stay unchanged. Its context checks still
apply, and preparation rejection is fail-stop. See the
[query partition](design/admission.md#selected-rwsem-state-queries).

The approved Native read-custody path transfers the existing downgraded credit
without decrementing it; O's normal read release consumes it. E still finishes
packet acceptance, retained owner ACKs and recursive stack unwind before pooled
retirement. The selected cleanup is synchronous on E, using a hotplug-protected
home-CPU callback or serialized explicit retirement for an already-offline CPU.
No new asynchronous cleanup queue or required TCLock-style waiter reclamation
is part of this phase. The [lifetime ordering](design/lifetimes.md#selected-retained-handback-retirement)
has four positive retirement modes and nine inconsistent-state rejections at
`da55414f`, following the retained first compile failure. CPU/work/hotplug APIs
are supplied. Separate slot-reuse fixtures make storage inaccessible after its
final access; the concurrent offline pair checks serialized count/bitmap
updates. Neither these components nor the service join prove real CPU hotplug,
the actual public query bodies or a loaded-provider handback.

The pre-live identity receipt verifies installed scope5 and an unloaded scope5
provider while the guest then runs `kdlock1`. The later scope5 probe passes cold
CALL and indirect-JMP phases. Its RET handback has the actual source return IP,
SP advanced by eight and useful effects once, but its incomplete checker fails
the run. A cleanup race is subsequently resolved with normal unload and zero
references; that does not change the failed session verdict. Candidate
`bccf877c` adds untested RET-wave/shutdown-order checks. Recovery to the original
`kdlock1` is verified, and further validation is blocked. Live acceptance must
distinguish a fully returned JIT episode from a handed-back prefix and observe both handback acceptance and
terminal retirement. Later image learning may change the registry; an unchanged
registry/returned-only validator cannot establish this path. See the
[live evidence boundary](design/kdlock_lock_replacement_contract.md#partial-live-probe-and-current-stop).

## Unlock and validation

Unlock follows the exact acquisition, not current heat or an approximate counter.
Public mutex unlock routes local owners, delegation owners and borrowed native
continuations through their retained provider records and ACKs. Rwlock writer
unlock releases the writer byte before gate/spin completion, and completion must
not clear it again after a successor can own it.

A frame leaves the active stack before DONE publication. The waiter reads return
state before reusing storage or releasing its pin. NATIVE_READY permits a checked
native remainder, not root retirement. Native executors, including relays with no
remaining held lock, retain their root/ticket references until cleanup and frame
removal finish. Final native unlock waits for required owner ACKs.

To claim returned JIT execution, require actual completion evidence, correct data,
state restoration and drain. Reader/writer delegated share uses completed writes
as its denominator. `NORMAL`, an entry witness and successful local `NO_JIT` are
different evidence classes. See [validation](VALIDATION.md), [frames](design/frames.md)
and [ownership](design/locking.md).

## Heat and roles

A lock is called **hot** when sampled contention makes it eligible for delegation.
These measurements are approximate. They never decide who owns a lock or when a
request can be freed.

Spin and mutex each maintain a per-CPU table with 256 buckets and 256 records.
Records match the full lock address. Hash collisions form chains; they do not evict
existing records. If the table is full, an unknown lock stays native. A lookup does
not insert a record, increment a counter or read the clock.

Rwlocks use the existing spin table keyed by the embedded gate. Successful ungated
writers count an entry and retain an exact nondelegated reference; failed fast
attempts transfer to ordinary gate accounting. Fast readers do not touch heat
state, while slow readers acquire the native gate. There is no separate rwlock
heat policy or reader delegation.

| Sampling point | Current rule |
| --- | --- |
| Spin physical acquisition | Count once, including fast/pending/native paths; retries are not new acquisitions |
| Spin MCS publication | Count only real publications; at `>=1024`, compare `(entries >> 10) < spin_entry_ratio_limit` |
| Spin CPU gate | Default ratio limit 2; after comparison clear both counters and sample time; interval must be `<40000000000` TSC ticks |
| Spin lock gate | At `>=512` records, interval must be `<1250000000` TSC ticks |
| Mutex CPU gate | Own entry/contention counters; at `>=1024` contentions compare `(entries >> 10) < 256`, reset both, then sample time |
| Mutex lock gate | The 1025th record checks an interval `<2500000000` TSC ticks |

At 1024 MCS publications, the default ratio accepts 1024..2047 acquisitions and
rejects 2048. The first window participates. Limit 0 disables only the ratio;
it does not bypass CPU/lock heat, queue eligibility, context or JIT validation.
Supported nonzero values are powers of two of at least 2.

Mutex uses its separate fixed ratio limit 256 and the same CPU time bound;
the initially proposed limit 2 is not its current setting. Native successful
acquisitions count entries without touching delegation/task/translation state.

When sampling, a hot native MCS queue head also saves the current tail and checks
up to six linked successors before waiting for or acquiring the word. A missing
tail, zero locked byte, incomplete link or fewer than six successors makes the
CPU cold. This check does not wait for missing links. It stops at the saved tail,
never reads successor frames and never changes a published request. The queue
head's position prevents those nodes from being reused during the check.

Interrupts or reentrant calls can lose or mix observations. If another comparison
is already running, a busy guard skips this one without clearing counters or
sampling time; the next MCS publication retries. A CPU sample keeps the lock
windows only if that CPU was hot and remains hot. Otherwise it clears their heat
and counts while retaining the recorded addresses. If later acquisitions never
publish an MCS node, cached heat may remain indefinitely. There is no cooldown
or rule requiring several low-contention windows.

`spin_delegate=0` counts acquisitions but skips heat-table/MCS observation and
executes natively. `hotlock_stats=1` reports approximate accumulated observations;
the ratio log's `scope=unfinished_batch` is only the remaining uncompleted window.
Neither is a peak-window execution count or lifetime/ownership proof.

## Executable image generations

Before extracting `jit.bin`, inspect the assembled object's relocation sections.
Raw `objcopy -O binary` does not apply ELF relocations. Any remaining REL/RELA
entry targeting an allocated section with stored bytes is an incomplete image,
whether its referenced symbol is defined or undefined. Stop the build and retain
the object and assembly; do not publish it or classify it as a local-only entry.
Relocations for unallocated debug sections do not affect the extracted image.
Same-section label differences and the provider's literal call-patch metadata
remain valid when the assembler resolves them without ELF relocations. Remove
old raw output before rebuilding so a failed check cannot leave an earlier
`jit.bin` looking current. This checks emitted bytes without adding semantic
source analysis or changing the wrapper ABI.

Mutex frames bind immutable generations through FULL/native continuations.
Replacement does not overwrite their code or allow an old-generation miss to
modify new metadata. Versions remain allocated until terminal session teardown.

Ordinary spin/rwlock descriptors initially refer to in-place code. Supported root
instruction-marker images make an immutable transition. Retained checked address
and historical string images have their own compatible transition too; production
does not select their analyses or named string routes. Once transitioned, later
generations remain immutable even if their requirements shrink.

Source pins, bound image descriptors, physical ownership and frame retirement
remain distinct. [Lifetimes](design/lifetimes.md) defines their limits. Synchronize
only while idle and never replace frozen inputs under live work.

The descriptor pool defaults to 64 shared slots. Each published immutable
generation consumes one slot until terminal session retirement; replacing the
current image does not free the older generation. Ordinary and optional near
code pools have separate preallocated blocks but share that descriptor limit.
Each block remains 4 MiB. A build may select `KDLOCK_JIT_IMAGES=128` for bounded
learning; supported counts are 1 through 256 and the default stays 64. This
changes preallocated capacity, not publication, frame or source lifetimes.

The read-only `jit_image_usage` parameter reports exact occupied,
published/private and free descriptor counts under the existing publication
gate, allocated/free blocks in each pool, slot size and pool metadata sizes.
It is a resource observation, not an ownership or retirement predicate. Capture
it outside application timing; it returns `-EAGAIN` during pool initialization
and teardown. Capacity 128 reserves up to 512 MiB ordinary
plus 512 MiB near code, with 10 KiB of descriptor/pointer arrays on x86-64;
allocator and page-table overhead is additional.
