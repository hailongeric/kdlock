# Real kernel API contention

This runner measures actual `fgetxattr()`, `fcntl(F_OFD_GETLK)` and
`fcntl(F_SETFD)` syscalls using private tmpfs files. Userspace and the
VFS/security/result-copy paths remain in the measured operation. A scoped ftrace
module substitutes the selected kernel function only for the private file or
file table. Its critical section uses Native, TCLock or KD spinlocks, selected
at build time. An optional `stock` arm runs the original kernel function without
a substitution module.

The [2026-10-11 comparison](../results/10.176.26.71/bench/real_api/20261011/README.md)
contains 288 accepted, drained OFD/setfd sessions: four backends, three rounds,
two metadata layouts and six worker counts per API. It reports the useful KD
regimes, regressions, single-thread cost, xattr refusal and exploratory failures.

These are API microbenchmarks with real kernel metadata, not end-to-end
application measurements or a global replacement of Linux locks. Neither loading
KD nor loading TCLock alone changes ordinary syscall locking.

## Candidate selection

| Workload | Actual critical section and cached state | Suitability |
| --- | --- | --- |
| tmpfs `fgetxattr()` | `simple_xattr_get()` holds `simple_xattrs.lock` across linked-list name comparisons and the value copy | Implemented; many callers query one metadata-rich file. Attribute count and hit position control real search work. |
| `fcntl(F_OFD_GETLK)` | `posix_test_lock()` holds `file_lock_context.flc_lock` while checking owners, ranges and conflict type, then copying the conflict | Implemented for local, non-expiring OFD locks; models repeated byte-range conflict queries on one file. |
| `fcntl(F_SETFD)` | `set_close_on_exec()` holds `files_struct.file_lock` across the close-on-exec bitmap update | Implemented; each thread toggles its own preallocated descriptor flag in the shared table. Descriptor spacing changes the dirty bitmap footprint. |
| FxMark directory enumeration / rename | Shared dentry/rename state and, for cross-directory rename, `s_vfs_rename_mutex` | Candidate for wider integration; additional lock sites and filesystem behavior must be preserved. |
| will-it-scale `lock1` | Repeated `F_SETLKW` / unlock, with a **separate file per worker** | Useful reference; it does not itself create a shared inode lock. The original paper's kernel/version bottleneck must be re-established on this kernel. |
| eventfd / epoll wakeup paths | Short queue/counter critical sections, often with IRQ exclusion | Poor initial fit for the present ordinary-task-context delegation ports. |

Sources: [TCLocks evaluation, Table 1 and Figure 3](https://www.usenix.org/system/files/osdi23-gupta.pdf),
[will-it-scale lock1](https://github.com/antonblanchard/will-it-scale/blob/master/tests/lock1.c),
[Linux xattr implementation](https://github.com/torvalds/linux/blob/v6.1/fs/xattr.c),
[Linux file-lock implementation](https://github.com/torvalds/linux/blob/v6.1/fs/locks.c),
[file-table operations](https://github.com/torvalds/linux/blob/v6.1/fs/file.c), and
[ftrace function substitution](https://docs.kernel.org/6.1/trace/ftrace-uses.html).
The runner also saves the exact guest implementations and relevant headers with
hashes; the compiled experiment targets the captured 6.1.159 guest.

## Contract and comparison limits

The client creates an anonymous `memfd`, fills its `trusted.kdlock.*` attributes
(root is required; this guest has no tmpfs `user.*` handler) or establishes
nonadjacent one-byte OFD write locks, and then waits for the controller. The
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

Only one fixed worker runs on each selected CPU. All requests use the real
kernel list and original lock storage. Syscalls run individually, without an
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

## Run in the recovery guest

Follow [operations](../../docs/AGENTS.md), synchronize reviewed source, verify
the current kernel, NUMA placement and physical vCPU pins, and confirm a fresh
monitor snapshot of the actual CPU topology. Do not rebuild the kernel. The
standard guest has 64 vCPUs; collector 63 is excluded from worker cohorts.

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
The recorded figures used Matplotlib 3.9.4. Basic and directly affected checks:

```sh
make -C tests/unit run
python3 bench/real_api/test_report.py
python3 -m unittest discover -s bench/spin_cacheline -p test_peak.py
```

`--queries front tail miss` changes lookup position; xattr also supports `size`.
Use `--kinds setfd --queries toggle` for the bitmap case; `--entries` then means
the FD-number stride between workers, starting at FD 64. Use a separate run
because query modes are API-specific.
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
