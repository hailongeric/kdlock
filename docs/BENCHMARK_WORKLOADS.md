# Benchmark workloads and critical sections

The active catalog targets Ubuntu 26.04.1 / Linux `7.0.0-38-kdlock1`.
[Current plan](../bench/catalog_single/current_plan.py) selects **52 lock/API
configurations**: ten nano and 42 micro/API cases. The three implemented MM
suites have separate kernel plans. Use [benchmark commands](../bench/README.md)
for execution, [performance](PERFORMANCE.md) for outcomes and
[VM operations](operations/VM.md) for environment and recovery.

## Grid and evidence

The selected grid is workers `1..8,12..60`, stepping by four above eight:
21 counts, Native/TCLock/KD where supported, one two-second round per point.
Workers use CPUs `0..N-1`; collector CPU 63 is separate. Rwlock/rwsem micro
mixes use 1% and 20% writes. Pass the grid explicitly: historical runner defaults
and `--full-matrix` do not necessarily select it.

Synthetic workers perform many bodies within an ioctl phase. API workers issue
syscalls individually. Their call shells and post-work are part of each workload
identity. Do not pool different shells, source generations or instrumentation.
Exact data, worker progress, returned-body observations and drain are required.
A `NORMAL` publication does not prove execution; successful local `NO_JIT` points
retain that class. A failed or partial body has no accepted rate.

The [completed Linux 7 index](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
selects 3,276 lock/API and 126 MM points, across separate frozen generations.
All timing is exploratory, with failed strict qualification and no repeat
variance estimate. Earlier failed/partial attempts remain outside those totals.

## KD API use and delegation

| Family | Selected interface | Delegation boundary |
| --- | --- | --- |
| Spin | `KD_SPIN_DIRECT_LOCK/UNLOCK` | Eligible exclusive body, ABI1 |
| Mutex nano and selected public API cases | Direct public `kd_mutex_lock/unlock` | Unified ABI2; callable/signal/try/I/O forms remain local |
| Rwlock | Local read pair and `KD_RWLOCK_DIRECT_WRITE_LOCK/UNLOCK` | Writers only, ABI3 after native writer admission |
| Rwsem | Local read pair and `KD_RWSEM_OUTER_WRITE_LOCK/UNLOCK` | Explicit writers only, ABI2 after reader drain |

Current translation trusts kernel and module source, including loops. It skips
semantic safety/context/value/input proofs. Complete leased text, faithful
lowering, actual CALL/RET words and exact runtime ownership remain required.
Strings use ordinary decoded callees without helper-specific models or services.
See [translation policy](design/admission.md) and [lock APIs](LOCKS.md).

## Active nano profiles

All profiles use one or sixteen directly addressed, 64-byte-aligned counters and
**256 register-only post-unlock rounds**. Writers increment every selected counter.
Shared readers compare values, including a repeated first-counter load in the
one-counter case. There is no allocation or container traversal in the body.

Use concrete payload names: `c01` means one cacheline, `c08` means eight
cachelines, and `c16` means sixteen cachelines. Each cacheline contains one
updated counter. State the lock family, write percentage and post-work count
alongside the payload name; the name alone does not identify a comparison.

| Workload | Lock and writes | Cachelines |
| --- | --- | ---: |
| `c01` | Mutex, 100% writes | 1 |
| `c16` | Mutex, 100% writes | 16 |
| `c01` | Rwsem, 1% / 20% writes | 1 |
| `c16` | Rwsem, 1% / 20% writes | 16 |
| `c01` | Rwlock, 1% / 20% writes | 1 |
| `c16` | Rwlock, 1% / 20% writes | 16 |

The ten configurations account for 630 points. Existing runner identifiers and
archived paths remain unchanged; this guide names the actual payloads.
[best_case.py](../bench/nano/best_case.py) defines their parameters;
[rwlock_bench/payload.h](../workload_modules/rwlock_bench/payload.h) supplies the
current cacheline body. Mutex defaults are cap 1024, locality boundary 768,
deferred handoff threshold eight and scan budget 64. These favorable profiles
were selected from exploratory evidence, not a proof of universal optimality.

Mutex uses public ABI2 calls; rwsem uses explicit outer writers; rwlock uses
exclusive writer pairs. Readers remain local. `--delegate off` is a separately
labelled local control. See the [nano guide](../bench/nano/README.md).

## Synthetic cacheline updates

Spin selects `spin-c01` and `spin-c08`: increment one or eight aligned counters
under one exclusive pair, followed by 64 register-only post-work rounds.
Rwlock/rwsem select c01/c08 at 1% and 20% writes, with four post-work rounds.
Their readers check equal counter values; writers increment every selected value.
These are different profiles from the post256 nano cases.

The old mutex micro selections are removed. Current mutex synthetic comparisons
use the two nano profiles above. Keeping an implementation available for focused
checks does not select it for the maintained catalog.

## Synthetic hash updates (`rcuht`)

Spin and rwlock/rwsem retain a preallocated table with 1,024 buckets,
4,096 entries and key range 8,192. Exclusive work searches and updates/moves
entries; shared readers search without mutation. The full structural and exact
outcome oracle remains required. This benchmark uses its selected global lock;
its name does not mean per-operation RCU reclamation. Hash-chain traversal here
is a separate maintained workload.

## Extracted proc snapshots

| Names | Body and mutation |
| --- | --- |
| `argbounds-w00`, `argbounds-w20` | Copy four related argument/environment bounds; optional writer changes the consistent record |
| `taskname-w00`, `taskname-w20` | Copy a protected name with `strscpy_pad(..., 64)` and check every result/padding byte; optional writer alternates valid short/long names |

These are extracted records, not live process/mm mutation or an end-to-end `ps`
benchmark. They use the spin snapshot shell. Reference acquisition, procfs I/O
and output checks remain outside the protected body. Taskname's ordinary Linux 7
callee graph includes `strnlen` and `sized_strscpy`.

Both taskname mixes use the existing maximum-eight-wave preparation before the
daemon stops and timing begins. The earlier zero-wave mixed attempt and its
failure remain preserved; the separately prepared cohort does not overwrite it.
Positive preparation or an unchanged image does not guarantee measured JIT use.

## Real API labels and parameters

| Catalog family | Queries | Parameter | Configurations |
| --- | --- | --- | ---: |
| `ofd` | `front`, `tail`, `miss` | 16 / 128 fixed locks | 6 |
| `setfd` | `toggle` | 16 / 512 descriptors | 2 |
| `pipebytes` | `query` | 16 / 128 prepared entries | 2 |
| `pipecap` | `query` | 16 prepared entries | 1 |
| `seek` | `set`, `end` | 16 prepared entries | 2 |
| `utsname` | `host`, `domain` | 20% writes, 64-byte names; label `n20` is the write percentage | 2 |
| `xattr` | `front`, `tail`, `miss`, `size` | 16 / 128 attributes; 64-byte values | 8 |

Together these are 23 configurations. Spin micro cases contribute three,
rwlock/rwsem micro cases twelve, and proc snapshots four: 42 micro/API cases total.
[plan.py](../bench/catalog_single/plan.py) defines exact runner arguments.

## Real-world API critical sections

### Permanent testing constraint

Invoke each real-world API from userspace through its actual system call path.
Measure the complete declared syscall operation, including its normal validation,
security checks and result copies. Direct calls to extracted kernel bodies or a
test ioctl that runs those bodies are mechanism tests, not substitutes for
real-world API measurements.

Inside the kernel, restrict experimental changes to the lock API calls protecting
the relevant critical sections. Preserve the native critical-section bodies,
surrounding control flow, data structures and observable API behavior. Prefer
integration that leaves the kernel source unchanged. Any necessary lock-object
binding, routing or lifetime glue must be minimal, documented separately, and
must ensure that every user of an object follows the same lock protocol. Do not
rewrite the operation, precompute its result or move work out of the measured
path to improve a benchmark.

This is a permanent project constraint. The existing scoped function-substitution
adapters below remain evidence of their recorded implementation; syscall entry
alone does not prove that an adapter satisfies the minimal-change constraint.
Review its source differences against the bound kernel before making that claim.

| Kind | Protected work | Execution boundary |
| --- | --- | --- |
| OFD | Search prepared lock records and copy the conflict result | Spin; file lifetime and bound query scope fixed before workers |
| Setfd | Update the close-on-exec bitmap bit | Spin; caller file-table lookup outside the body, no concurrent table resizing |
| Pipebytes | Sum prepared ring-buffer lengths | Mutex; user copy occurs after unlock |
| Pipecap | Read ring capacity | Mutex; no concurrent pipe mutation/resizing while bound |
| Seek | Validate and update `f_pos` for set/end | Mutex; references outside the body; Linux 7 has no retired `f_version` store |
| UTS names | Copy/update the selected fixed-size name | Local rwlock readers and eligible writers; permission checks, user copies and notifications stay on the caller |
| Xattr | Read the Linux 7 rb-tree, compare names and copy/query the value | Concurrent local rwlock readers; no prepared image, helper learning or JIT-eligible operation |

These scoped adapters bind private/frozen objects and correctly typed locks.
They do not reinterpret an existing Linux lock or convert all subsystem users.
Source is in [real_api](../workload_modules/real_api); runner/oracle details are
in its [guide](../bench/real_api/README.md).

Linux 7 xattr uses `xattr-rbtree-read-v1`. Its `front`/`tail` labels identify keys,
not positions in a former linear container. All 168 KD xattr points are successful
local `NO_JIT`; any image or generated entry is rejected for this workload.
Historical xattr results used a different kernel structure and spin protocol.

## Separate mmap and page-fault suites

| Suite | Timed operation and topology | Backends / points |
| --- | --- | --- |
| Independent-mm mmap | Untouched 4 KiB read-only shared device mmap/munmap in independent processes; no backing-lock work or faults | Native, 21 |
| Private-backing fault cycle | Independent mms share a backing object; `MADV_DONTNEED`, read and check a preallocated page | Native/TCLock/KD private backing readers, 63 |
| Actual shared-mm mmap | Threads in one mm map/unmap untouched 4 KiB device ranges; actual kernel mmap-lock backend changes | Same `kdmm1` image in Native/KD modes, 42 |

The private 84 points run on normal `kdlock1`, with the real mmap lock Native.
The shared 42 require the separate enabled-MM image and explicit mode-specific
schema-2 identities. There is no TCLock actual-MM arm. MM bodies retain their
native algorithms and execute on the original task; none of these rates measures
operation-specific MM-body delegation.

The [mapping contract](design/mmap_fault.md), [Linux 7 MM guide](../kernel_integration/linux70/MMAP.md)
and [MM controller plan](../bench/catalog_single/LINUX70_MM.md) define prerequisites,
exact ownership/witness checks, cancellation and cleanup. An operation includes
the declared mapping pair or reset-plus-read cycle; it is not isolated fault or
lock latency.

## Scope and evidence

The catalog covers implemented benchmarks, not the full unit suite. Exact
will-it-scale `mmap1` (128 MiB untouched anonymous private mappings) and a generic
actual-backend minor-fault throughput driver remain [roadmap work](ROADMAP.md).
Do not rename the device/backing experiments as those targets.

Old kernel excerpts, earlier profile selections and proposed proc/MM delegation
plans have been removed from this maintained definition. Their source-specific
records remain in [history](history/README.md) and frozen results. Use the current
command plan rather than copying a dated campaign's output paths or kernel recipe.
