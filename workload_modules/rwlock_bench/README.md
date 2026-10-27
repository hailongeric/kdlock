# Mutex, reader/writer and proc snapshot benchmark workload

Current translation trusts kernel and module source and skips semantic safety
admission, including loop/value and entry-input proofs. The compiler's clobber
entry contract is assumed. Ordinary instruction lowering, leased text, exact
CALL/RET routing and runtime lock/frame ownership remain required. String
functions follow this same path, with no helper-specific summaries or services.
The checked analyzer remains available as an explicit regression utility.

`rwlock_bench.ko` exposes `/dev/kd_rwlock_bench` for the
[comparison runner](../../bench/rwlock_compare/README.md). Build variants select
Linux native, TCLock or KD through `RB_BACKEND` and the locking shell through
`RB_LOCK_KIND=rwlock|spin|rwsem|mutex`. All use the same timed worker loop, operation
mix and payload. TCLock rwsem uses its original semaphore plus AQS reader gate. Workers register before their operation loop and drain after the client cohort exits.
The runner defaults to RCUHT at 1% and 20% writes on its historical fifteen-count
grid ending at 36 workers. Current standard comparisons must explicitly select
workers 1–8 and 12–60 by four, with CPU 63 reserved for the collector; the default
is not that 21-count grid. Rwlock readers execute locally; only KD writer bodies can contribute
to the complete-body JIT count. TCLock uses the actual upstream rwlock algorithm,
with its delegation share reported as unmeasured.

Cacheline variants compile a fixed `RB_LINES` body. Hash variants use
`RB_WORKLOAD=rcuht RB_LINES=0` and share the existing spin benchmark's preallocated
hash move body and structural snapshot oracle, adding concurrent read lookups.
KD rwlock writers use ABI3: native or delegated writer admission precedes the JIT
payload. Hash pointer traversal therefore retains the original strict admission
checks without including reader-drain counter stores in its translated body.
`RB_SHARED` points to that hash payload header. Register-only post-work follows
the earlier cacheline benchmark's multiply/add pattern;
`RB_POST_WORK_ROUNDS` is always explicit in the runner and layout response.
Its default is four rounds, independent of the shared spin/mutex post-work
setting. RCUHT here is a globally locked hash workload, with no per-body
allocation or RCU services; the name does not imply lock-free reader execution.
Ordinary reader/writer cacheline selections use `RB_LINES=1` or `RB_LINES=8`.

The ten stage 1 [nano profiles](../../bench/nano/README.md) use
`RB_WORKLOAD=cacheline`, `RB_LINES=1` or `16` and 256 post-unlock rounds for
mutex, rwlock and rwsem. Each selected counter is padded separately. The mutex
arm also accepts sizes 2, 4 and 8 for explicit controlled comparisons, outside
the current nano catalog. `RB_WORKLOAD=nano RB_LINES=2` retains the older
two-word, one-cacheline body for historical controls; it is no longer selected
by the nano launcher. `RB_MUTEX_DELEGATE=1` selects public ABI2 calls;
zero selects the callable local control. All arms retain exact data and drain
checks. The [project roadmap](../../docs/ROADMAP.md) keeps these module-object
comparisons separate from actual-MM and final kernel replacement.

`RB_LOCK_KIND=spin RB_WORKLOAD=argbounds|taskname RB_LINES=0` selects extracted
Linux 6.1.159 proc snapshots. Argument bounds copy four related address fields;
task names call `strscpy_pad()` and verify the complete padded destination after
unlock. Both retain exclusive spin semantics. Snapshot reads are the KD delegated
entry; optional mutations use the same physical KD lock locally. The mutation
counter and per-reader checks detect lost updates and inconsistent snapshots.
These tests exclude task/MM lifetime management and procfs I/O. Task-name helper
learning still passes strict instruction admission; a published NORMAL image
or an entry witness alone does not establish complete delegation.

Taskname reads one module-owned 16-byte name into a caller-local 64-byte result
using the original `strscpy_pad(result, name, 64)` call. The read-only case starts
with 15 equal letters followed by a zero byte. Optional mutations alternate
three-letter and fifteen-letter names, changing their letter with each update;
the reader checks every character and every zero-padding byte after unlock.
The 20% mutation case is a separate correctness workload, not part of the
read-only performance score. Reads and mutations both take the same exclusive
lock; a snapshot "read" does not use a shared reader lock. Post-work remains
four arithmetic rounds by default and is recorded separately from the payload.

The current KD shell uses ordinary `KD_SPIN_DIRECT_LOCK`, without helper-specific
register setup. Its string callees now use ordinary leased-text decoding,
instruction/context admission, sequential memory tracking and generated CALL/RET.
Helper prologues and actual return words receive the same checks as other code;
no string-service summary, direct bridge or helper quota is selected. The source
still supplies valid buffers and checks all result bytes after unlocking.

The following service descriptions and results are historical compatibility and
source-specific evidence, not validation of the current Linux 7 translation.
The API contract introduced in version 10 invoked the original kernel helper without checking
helper code, scanning the source string or checking destination bounds at
runtime. The original caller supplies valid, stable source storage and a live,
disjoint local destination. Translation still requires count 64 and a known
local output span to model the original CALL-stack write and all 64 destination
writes. Ordinary instruction/address admission and common owner/frame/return
checks remain active. See the
[writing-service contract](../../docs/design/admission.md#original-strscpy_pad-writing-service).
Version 11 optionally uses a
[direct-call route](../../docs/design/admission.md#direct-original-helper-calls)
inside one generated invocation. It preserves this payload, its 64-byte output
effect and actual CALL return word; it adds no helper or argument checks.
The two-word wrapper ABI and selected KD mutex protocol remain unchanged.
The runner records uploaded code and relocated loaded bytes outside timing.
Focused validation is tracked [centrally](../../docs/VALIDATION.md#taskname-and-xattr-helper-validation);
the [separate historical direct-route comparison](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
records that implementation's completed grid. Its results do not transfer to the
ordinary helper translation path.

Version 10 candidate 6 passed read-only taskname correctness on Linux Native,
TCLock and KD; KD recorded matching generated-body entries and completions.
A separate 20% mutation check with `--helper-waves 0` passed correctness on all
three backends but recorded zero KD generated bodies. It validates the resulting
names and padding, not mutation-case delegation, and does not supersede earlier
strict delegation failures. The
[version 10 development record](../../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md)
records the focused checks. The separate
[`88bb5a4` standard-grid comparison](../../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
is complete for read-only taskname; mutation-case delegation remains unaccepted.

In the preceding implementation frozen in `c79d84f`, the ordinary shell passed its 16-worker
read-only check with 3,200,000 operations and 3,194,222 matching generated
entries and completed bodies. Native and TCLock controls also passed. All three
20% mutation cases produced correct results and drained, including 640,000
writes and 2,560,000 reads per case. KD completed nine delegated snapshots during
preparation but zero during measurement, so the strict measured-delegation
requirement failed (`NO_JIT`). Preparation completions are not a measured score.
The [development record](../../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
preserves those source-specific checks, historical refusals and intermediate
results. Keep those measurements separate from the revised implementation.
`--delegate off` remains an explicitly local KD control.

After the recovery and observer checks, this focused guest-only run checks both
read-only snapshots and concurrent mutations with Native, TCLock and KD. It
produces correctness records without performance scores:

```sh
timeout --kill-after=10s 1800s python3 bench/rwlock_compare/run.py \
  --lock-kind spin --workloads taskname --write-percent 0 20 \
  --backends native tclock kdlock --threads 8 --collector-cpu 63 \
  --helper-workers 8 --functional --iterations 50000 --repeats 1 --require-jit \
  --output /root/kdlock-evidence/10.176.26.71/tests/taskname-functional-NEW
```

`RB_LOCK_KIND=rwsem` selects Native or KD sleeping reader/writer operations for
the cacheline/hash payloads. `RB_RWSEM_DELEGATE=1` selects the explicit KD writer
shell: reserve a reader-free epoch, enter the existing mutex ABI2 wrapper and
release the reservation on the original caller after the matching unlock.
Reader-drain waiting happens before queue publication. Ordinary writers reserve
an exclusive admission state, so downgrade cannot create readers inside an
existing delegated epoch. Readers remain local. The runner selects this shell
for its default KD comparison and binds completion observation to the embedded
physical KD mutex. `RB_RWSEM_DELEGATE=0` is the build default and ordinary local
control; the runner requests it with `--delegate off` and names it `-local`.
No owned-mutex protocol or ABI4 is restored. Default-KD runs require a stable ABI2
publication across measurement, and their returned writer completions remain
separate from entry-only or zero-entry runs.
This extracted benchmark does not replace a live kernel `mmap_lock`.

The versioned [ABI](api.h) configures each phase while no workers are active. Each
worker claims its slot once and executes its whole batch in one ioctl. It publishes
progress every 256 completed operations in a separate 128-byte slot. A control gate
protects configuration, snapshots and KD preparation, outside the lock being
measured. Choosing read versus write and generating random keys also happen outside
the critical section.

Readers update only their own result counters. Writers update the protected data.
Hash outcome totals are combined once per returned ioctl. After all callers finish,
snapshots and the Python checker verify the resulting data. Use the separate
[rwlock test workload](../../tests/kernel/rwlock/payload/README.md) for instrumented reader/writer overlap
checks. These benchmarks support pinned task-context callers with IRQs enabled,
one global lock and no recursive reads, upgrades or nested/IRQ/BH locking.
