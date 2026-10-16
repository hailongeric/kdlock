# Real kernel API contention

This runner measures actual syscalls on private kernel objects: file-lock
queries, descriptor flags, pipe metadata, file positions and UTS namespace names.
Userspace and surrounding security/result-copy paths remain in the measured
operation. A scoped ftrace module substitutes selected functions for the bound
object. Spin, mutex or reader/writer backends are selected at build time. The
`stock` arm runs the original kernel functions without a substitution module.

KD mutex cases always use bounded polling followed by blocking.
[Performance status](../../docs/PERFORMANCE.md) describes remaining throughput
gaps. The [machine index](../results/10.176.26.71/README.md) retains earlier API
reports, exploratory failures and source identities.
The [expanded mutex comparison](../results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
includes all three backends for pipebytes n16/n128, pipecap n16 and seek set/end,
with three repetitions at each requested worker count through 60.

These are API microbenchmarks with real kernel metadata, not end-to-end
application measurements or a global replacement of Linux locks. Neither loading
KD nor loading TCLock alone changes ordinary syscall locking.

## Candidate selection

The [workload guide](../../docs/BENCHMARK_WORKLOADS.md#real-api-labels-and-parameters)
explains each API's setup, protected reads and writes, kernel call path and label
parameters. In particular, `--entries` has a different unit for each API;
worker count is always selected separately with `--threads`.

| Workload | Actual critical section and cached state | Suitability |
| --- | --- | --- |
| tmpfs `fgetxattr()` | `simple_xattr_get()` holds `simple_xattrs.lock` across linked-list name comparisons and the value copy | Kernel integration exists; current translated xattr bodies are refused by pointer/context admission and are excluded from accepted performance comparisons. |
| `fcntl(F_OFD_GETLK)` | `posix_test_lock()` holds `file_lock_context.flc_lock` while checking owners, ranges and conflict type, then copying the conflict | Implemented for local, non-expiring OFD locks; models repeated byte-range conflict queries on one file. |
| `fcntl(F_SETFD)` | `set_close_on_exec()` holds `files_struct.file_lock` across the close-on-exec bitmap update | Implemented; each thread toggles its own preallocated descriptor flag in the shared table. Descriptor spacing changes the dirty bitmap footprint. |
| `ioctl(FIONREAD)` on a shared pipe | `pipe_ioctl()` holds `pipe_inode_info.mutex` while summing real buffer lengths around the ring | Native/TCLock/KD mutex case; occupied buffer count controls protected traversal, with one independent file description per worker. |
| `fcntl(F_GETPIPE_SZ)` | `pipe_fcntl()` holds the same pipe mutex while reading `max_usage` | Native/TCLock/KD short mutex control on the same real subsystem. |
| Shared-file `lseek(SEEK_SET/SEEK_END)` | `ksys_lseek()` holds `file.f_pos_lock` across size checks and `f_pos`/`f_version` updates | Native/TCLock/KD mutex case for an anonymous tmpfs file and one shared open description. |
| `uname()` with `sethostname()` / `setdomainname()` | `uts_sem` protects the real UTS structure: readers copy it, writers replace one name | Implemented bounded read/write experiment in a private UTS namespace; Native rwsem versus KD/TCLock reader/writer spinlocks, with the specialization below. |

Sources: [TCLocks evaluation, Table 1 and Figure 3](https://www.usenix.org/system/files/osdi23-gupta.pdf),
[Linux xattr implementation](https://github.com/torvalds/linux/blob/v6.1/fs/xattr.c),
[Linux file-lock implementation](https://github.com/torvalds/linux/blob/v6.1/fs/locks.c),
[file-table operations](https://github.com/torvalds/linux/blob/v6.1/fs/file.c), and
[ftrace function substitution](https://docs.kernel.org/6.1/trace/ftrace-uses.html).
The runner also saves the exact guest implementations and relevant headers with
hashes; the compiled experiment targets the captured 6.1.159 guest.

## Contract and comparison limits

For xattr/OFD, the client creates an anonymous `memfd`, fills its
`trusted.kdlock.*` attributes (root is required; this guest has no tmpfs `user.*`
handler) or establishes nonadjacent one-byte OFD write locks, and then waits for
the controller. The
module pins that file and rejects linked files and non-tmpfs objects. The OFD
variant also rejects lock-manager callbacks and non-OFD locks. Once bound,
**no participant may mutate metadata, change the OFD locks, or close their owner
until all workers have joined and the substitution module has been unloaded**.
The controlled client implements that ordering. Do not attach this experimental
module to an application with independent readers/writers or use it as a general
kernel lock adapter. Other native consumers of the same spinlock are outside
the supported experiment.

The setfd case holds a reference to the client's `files_struct` and scopes the
hook to that file table. It changes only flags of preallocated descriptors;
opening, closing or duplicating descriptors is forbidden while bound. Each
worker owns a distinct descriptor, alternates its `FD_CLOEXEC` bit, and checks
the result with `F_GETFD`. Thus one setfd operation includes **two syscalls**,
of which one takes the substituted lock. Other cases use one syscall per operation.
Each setfd descriptor has its own open file description, so the syscall's
`fdget_raw()`/`fdput()` does not contend on one shared `file.f_count` outside
the target lock. The earlier shared-description screen remains separate evidence.

The xattr search/copy body follows the guest implementation, changing its lock
calls. The OFD variant inlines the guest owner/overlap/conflict tests and conflict
field copies. Callback handling is specialized away only after the binding
check establishes that the private locks have no callbacks. Native/TCLock/KD
receive the same body and data layout, without UBSAN in the workload. The
`stock` control exposes combined substitution/compiler differences; it is not
pooled with the matched native arm. The captured kernel has UBSAN enabled, while
all timed replacement/provider modules have UBSAN disabled. Therefore only the
matched native comparison isolates the lock change within this compiled body.

Only one fixed worker runs on each selected CPU. The spin cases use the real
kernel metadata and original lock storage. Syscalls run individually, without an
ioctl loop or artificial arithmetic inside the critical section. Warmup and
setup are outside timing. User-buffer validation is inside timing and identical
across backends. Values differ by attribute key; every returned byte is checked.
The additional pre/post oracle checks all entries, size queries, `ERANGE`,
`ENODATA`, conflict fields, unoccupied ranges and same-owner non-conflicts.

The worker progress batch is 256 operations. The collector samples every 10 ms
on its own CPU; peak selection reuses the maintained full-cohort 300 ms window
validator after 300 ms of settling. `kernel_finished_ns` in its input schema is
the userspace timestamp after the last syscall returns, not a kernel probe.
All workers must make progress in the selected window. Both full-run throughput
and the highest valid peak are retained, together with CPU time and worker shares.

KD must publish an admitted translation before measurement. Xattr helper-learning
waves pause the daemon, join every caller, then resume translation; a refusal
ends that session. The daemon stops before the common warmup. Returned-body
counters distinguish actual JIT execution from
`NO_JIT`; no refusal or low JIT count is converted into a success claim.
TCLock spin delegation remains unmeasured, as in the existing comparator.
The module counts redirected calls, and the runner requires one call per
measured operation. A failed/undrained session has no accepted score.

## Mutex and reader/writer contracts

The [mutex module](../../workload_modules/real_api/mutex.c) keeps the real pipe
mutex or `f_pos_lock` for Native; TCLock and KD use separate ordinary-mutex
objects. KD uses a private 128-byte, 64-byte-aligned `struct kd_mutex`, owned outer ABI4, and
reuse allowance 32 by default. Its result wait polls up to 4,096 times before
blocking; `--owned-mutex-reuse-spins` and `--mutex-spin-limit` record alternate
policies separately. `--owned-mutex-adaptive --owned-mutex-numa` enables the
experimental queue-pressure switch and bounded local cohorts. The
[c01/pipebytes comparison](../results/10.176.26.71/bench/comparison/mutex-adaptive-20261016T075356Z/README.md)
records the full 21-count results and regressions. Both policies are off by
default; origin spin remains off. The build
checks ABI4 symbol imports and module identity, and the runner verifies provider
parameters, returned JIT bodies, object idleness and complete source retirement.
No KD object is passed to Linux mutex APIs or mixed with Linux waiters.

The client creates an unlinked FIFO, fills whole pages before binding,
and opens an independent description per worker. No pipe reads, writes or resizes
occur while bound. The seek case retains a shared description, restricts calls
to `SEEK_SET`/`SEEK_END`, and changes the real position on every worker's sequence.
Its surrounding shared `file.f_count` traffic remains part of the operation.

TCLock mutex workers register a fixed-CPU context before each phase. The client
joins every thread and retries the provider's checked drain for up to five seconds:
`pthread_join` can observe thread completion before the final kernel task exit.
No live-task or queue check is bypassed. `/dev/real_api_control` carries registration
and drain commands outside timing. KD's drain requires its private object to be
idle after every worker has joined. Close the control descriptor before unloading the source, while
retaining the benchmark object's descriptors until afterward.

The [UTS module](../../workload_modules/real_api/uts.c) binds only a private
`CLONE_NEWUTS` namespace with native x86-64 personality. Reads use `uname`; writes
set a 64-byte hostname or domain name. Every read checks for a complete allowed
name and unchanged other fields. User copies, permission checks, entropy mixing
and one proc notification remain in each syscall. The matched arms move that
notification after unlock, on the original caller. No proc-sysctl observers,
namespace changes or independent users of the bound namespace are permitted.

All three matched UTS backends use a private lock for the bound namespace: a Linux
rwsem for Native, and reader/writer spinlocks for KD and TCLock. This is a scoped
adaptation of the bounded, non-sleeping copy/update body, not a general replacement
of Linux rwsems. Stock retains global `uts_sem`, the original notification placement
and kernel instrumentation; its comparison includes all three differences. Global
proc notifications to other namespaces are retained in every arm. KD prepares the
ABI3 writer entry; readers stay native and
concurrent. JIT shares use the number of **writes**, not total mixed operations.
TCLock mutex delegation counts are recorded; spin/rwlock shares remain unmeasured.

## Run in the recovery guest

Follow [operations](../../docs/AGENTS.md), synchronize reviewed source, verify
the current kernel, NUMA placement and physical vCPU pins, and confirm a fresh
monitor snapshot of the actual CPU topology. Do not rebuild the kernel. The
guest must use exactly CPUs 0–63, with NUMA node 0 on 0–31 and node 1 on 32–63,
pinned to the same-numbered host cores. Do not add extra vCPUs or an unused
spare CPU. For up to 63 workers, collector 63 is excluded from worker cohorts.
The client supports up to 64 workers, but the current timed runner requires a
separate collector. The 64-worker point needs collector-sharing support on CPU
63 before execution; retain the resulting worker/collector/QEMU contention
with the results. See the [placement limitation](../../tools/vm/README.md#complete-164-worker-comparison).

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT
timeout --kill-after=10s 3600s python3 bench/real_api/run.py \
  --kinds ofd --queries tail --entries 16 128 \
  --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock \
  --output /root/kdlock-evidence/10.176.26.71/bench/real-api-new
python3 bench/real_api/report.py \
  /root/kdlock-evidence/10.176.26.71/bench/real-api-new --plots
```

CSV/JSON/text reports use only the standard Python library. `--plots` additionally
requires Matplotlib; use a separate analysis environment after measurement.
Pipe/file mutex workloads compare Stock, Native, TCLock and the private KD-owned
adapter. Each selected backend runs once per round. Historical reports that
excluded KD retain their original coverage and source identity; they are not
evidence for the new adapter.
The recorded figures used Matplotlib 3.9.4. Basic and directly affected checks:

```sh
make -C tests/unit run
python3 bench/real_api/test_report.py
python3 bench/real_api/test_plan.py
python3 -m unittest discover -s bench/spin_cacheline -p test_peak.py
```

`--queries front tail miss` changes lookup position; xattr also supports `size`.
Use `--kinds setfd --queries toggle` for the bitmap case; `--entries` then means
the FD-number stride between workers, starting at FD 64. Use a separate run
because query modes are API-specific.
Use separate output directories for these additional cases:

```sh
# --entries means occupied 4 KiB pipe buffers (capacity pages for pipecap).
python3 bench/real_api/run.py --kinds pipebytes pipecap --queries query \
  --entries 16 128 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock --output /root/kdlock-evidence/10.176.26.71/bench/pipe-new
# --entries means file size in 4 KiB pages.
python3 bench/real_api/run.py --kinds seek --queries set end --entries 16 \
  --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock --output /root/kdlock-evidence/10.176.26.71/bench/seek-new
# --entries means write percentage; remaining operations call uname().
python3 bench/real_api/run.py --kinds utsname --queries host domain \
  --entries 20 100 --value-size 64 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock --output /root/kdlock-evidence/10.176.26.71/bench/uts-new
```

`--value-size` defaults to 64 bytes. `--cpus` takes an ordered comma-separated
list, whose prefix defines each cohort. Use explicit interleaved NUMA placement
for a separate placement study. Do not pool different placements, payload sizes,
source versions, governors or warmup settings. `--build-from RUN` reuses saved
binaries only when all current source hashes and the previous binary hashes
match. The output retains all planned sessions, including failures and unrun
cases; the backend order rotates between rounds.

Warmup requires at least 48,000 operations **and one second per worker** by
default; measurement is two seconds. `--warmup` and `--warmup-ms` control those
minimums. Shorter warmups belong in explicitly labelled exploratory screens.
No performance advantage is assumed or forced by the runner. Select promising
real workloads using retained exploratory evidence, then run three matched
rounds; report regressions and single-thread overhead alongside gains.

Join workers → verify data and protocol drain → retire KD sources → unload
substitution module → unload provider → close query/owner files. A timeout or
kernel fault retains the processes/modules for diagnosis; do not force unload.
Archive evidence before snapshot recovery. Live output belongs outside the
guest checkout, and host archives/reports follow the existing machine-specific
[result layout](../results/README.md).

## Expanded mutex grid

The [expanded comparison](../results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
uses five API variants: pipebytes at n16/n128, pipecap at n16, and seek set/end
at n16. After the guest checks and environment setup above, the commands below
select 945 sessions: five variants, 21 worker counts, three backends and three
repetitions. Each command needs a fresh output directory. Collector CPU 63 is
separate from the default worker CPU prefixes throughout this grid.

```sh
timeout --kill-after=10s 7200s python3 bench/real_api/run.py \
  --kinds pipebytes --queries query --entries 16 128 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 \
  --collector-cpu 63 --backends native tclock kdlock --repeats 3 \
  --mutex-spin-limit 4096 --owned-mutex-reuse-spins 32 \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-pipebytes-NEW
timeout --kill-after=10s 7200s python3 bench/real_api/run.py \
  --kinds pipecap --queries query --entries 16 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 \
  --collector-cpu 63 --backends native tclock kdlock --repeats 3 \
  --mutex-spin-limit 4096 --owned-mutex-reuse-spins 32 \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-pipecap-NEW
timeout --kill-after=10s 7200s python3 bench/real_api/run.py \
  --kinds seek --queries set end --entries 16 \
  --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 \
  --collector-cpu 63 --backends native tclock kdlock --repeats 3 \
  --mutex-spin-limit 4096 --owned-mutex-reuse-spins 32 \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-seek-NEW
```

These select the adapter's explicit ABI4 policy with origin/NUMA options off.
The [synthetic commands](../tclock_compare/README.md#expanded-owned-mutex-comparison)
add 1,134 sessions for c01/c02/c04/c08/c16 and RCUHT. The archived
[matrix plan](../results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/matrix-plan.json)
preserves the exact per-group commands used for the published round. Keep
single-worker local KD results distinct from returned-JIT sessions, and retain
the private-versus-embedded lock placement difference in every API comparison.
