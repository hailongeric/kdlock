# Linux 7 mmap lock adapter

[mmap-lock.patch](mmap-lock.patch) adapts only the existing local lock backend,
API routing and acquired-read lifetime transfer to Ubuntu source
`linux=7.0.0-38.38`. It is separate from [kernel.patch](kernel.patch) and the
retired Linux 6.1 patch chain. `CONFIG_KDLOCK_MMAP` defaults to **disabled**.
Preparation or compilation does not validate actual-MM execution or performance.
The separate enabled-MM `kdmm1` build and its explicit Native/KD boot bundles
are specified in the [identity procedure](IDENTITY.md#separate-enabled-mm-identities).
That procedure leaves the MM option disabled in the ordinary `kdlock1` kernel. The
[enabled-MM checkpoint](../../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
now records the separate build, verified installation, clean Native/KD boots
and actual clean Native recovery snapshot. Fresh API, mapping, fault and
completed-fault prerequisites passed in both modes, followed by all 42 shared-MM
timing points with normal drain. The matched one-round comparison is exploratory;
Native was faster at all 21 worker counts. The original `contention_ok` failure,
later cleanup and separate diagnostic pass remain preserved. These scoped
results do not establish whole-kernel performance or live BPF/IRQ/NMI coverage.

The adapter reuses the maintained KD mutex/rwsem implementations with namespaced
symbols. Readers stay concurrent and writers execute on their originating task.
Each dynamic mm selects Native or KD once before publication; `kd_mmap=on` selects
KD only when the option is compiled in. Static mms, including `init_mm`, stay
Native. No body delegation, prepared teardown or mapping algorithm is added.

The [per-critical-section semantic map](../../docs/design/kernel_cs_semantics.md)
separates this local backend from future writer delegation, exact `mmap1` from
page-fault workloads, and mmap rwsem from split page-table, per-VMA and folio
protocols. Killable mmap writers and munmap's downgrade remain local; the map is
static feasibility analysis, not newly enabled MM delegation or a hotspot profile.

The revision 2 patch changes exactly ten files: `include/linux/mm_types.h`,
`include/linux/mmap_lock.h`, `include/linux/sched/mm.h`,
`kernel/bpf/mmap_unlock_work.h`, `kernel/bpf/task_iter.c`,
`kernel/bpf/stackmap.c`, `kernel/fork.c`,
`kernel/locking/Makefile`, `mm/Kconfig` and `mm/mmap_lock.c`.
[mmap-base-sha256.json](mmap-base-sha256.json) authenticates their original bytes
and seven unchanged native MM source files against the acquired Ubuntu tree.

Linux 7's writer sequence-count begin remains after successful acquisition.
`vma_end_write_all` remains before write release or downgrade. All other per-VMA
locking, tracing and native fault/mapping bodies remain unchanged. The added
const-qualified assertions preserve native rwsem assertions for the Native
backend and check exact physical writer ownership for KD. Linux 7's removed
public `mmap_write_trylock` interface is not reintroduced.

With the option enabled, BPF reserves its per-CPU deferred-release slot before
acquisition or callbacks. A nested claimant returns the existing busy/fallback
result without owning that slot. Every unsuccessful acquisition or stack-map
fallback releases its own empty reservation. A successful asynchronous release
transfers the acquired share through a single-use token, with `mmgrab` before
publication and `mmdrop_async` after release. The reservation remains held until
completion consumes the token and releases the share. A duplicate completion
cannot release another caller's share. With the option disabled, BPF retains
the original native raw-mm, lockdep and IRQ-work completion path. Both
final mm destruction and failed initialization check that the KD lock is idle.
Other direct mmap-lock references are static initializers, maple lockdep
metadata or lockdep-only assertions; the Kconfig gate excludes LOCKDEP,
DEBUG_LOCK_ALLOC, DEBUG_MUTEXES and PREEMPT_RT.

## Preparation and affected-object checks

Run preparation and all checks only in the designated Linux 7 VM. The helper
creates a new overlay directory and receipt; it leaves the supplied source and
configuration untouched:

```sh
python3 kernel_integration/linux70/prepare_mmap.py \
  --source /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --output /mnt/kdlock-builds/linux70-mmap-prepared-r2
```

`prepare.json` binds the exact patch, original wrapper files, shared generator
inputs, `reserved-deferred-read-v2` policy and every output. Apply its `overlay/` only to the independent development
source tree after checking those identities. The ordinary development kernel
keeps `CONFIG_KDLOCK_MMAP` unset. Use a separate build output for an explicitly
enabled compile check; preserve the complete selected configuration and its
differences. No installation or boot is performed by these helpers.

The affected-object checker accepts separate source/build roots:

```sh
python3 tests/kernel/mmap_lock/linux70_scope.py \
  --pristine /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --tree /mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source \
  --build-output /mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build \
  --preparation /mnt/kdlock-builds/linux70-mmap-prepared-r2/prepare.json \
  --mode disabled --make-arg KERNELRELEASE=7.0.0-38-kdlock1 \
  --output /root/kdlock-evidence/10.176.26.71/tests/linux70-mmap-disabled-rev2
```

The enabled invocation requires `--mode enabled` and a separate preconfigured
build output. Both modes compile five affected native interface objects; enabled
mode additionally compiles the five KD local adapter objects. Source checks
compare all native per-VMA/header bodies after only the reviewed lock-name
substitution, and preserve the original `mm/mmap_lock.c` implementation verbatim.
`--source-check-only` records source checks without claiming object compilation.
Both source-only and compile checks run in the VM. Use the distro-style
`KERNELRELEASE` override consistently; keep the source's upstream 7.0.14 version
and `LINUX_VERSION_CODE=458766` unchanged. Do not override `SUBLEVEL`.

The first preparation and full-build receipts remain revision 1 evidence.
Static review then found that its late token transfer could collide when a BPF
callback nested another mmap lookup before IRQ work was queued. Compilation did
not cover that ownership window, and revision 1 was not installed or booted.
Revision 2 adds the early reservation and disabled-mode separation described
above. Its [extracted-helper ownership fixture](../../tests/unit/infrastructure/test_linux70_mmap_unlock.py)
passed in the VM with native controls and seven rejected ownership/reference
mutations. Both revision 2 affected-object modes passed without compiler
warnings: five disabled objects and ten enabled objects. These checks cover
the reviewed wrappers and ownership model; live BPF/IRQ/NMI and actual-MM
validation remain separate. The revision 2 full kernel rebuild passed and the
custom `7.0.0-38-kdlock1` kernel booted with `CONFIG_KDLOCK_MMAP` disabled;
that boot does not exercise this adapter. The [port record](../../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
binds the build and boot identities.

The separate `7.0.0-38-kdmm1` image has now booted with the adapter compiled in.
Its source/build pair is `/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/{source,build}`;
preparation is `/mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json`.
Native and KD actual-mm API, mapping, fault and completed-fault checks passed on
the recorded fresh boots. Native API passed 137 checks and KD passed 161, with
zero errors. The original mapping
attempt failed its contention predicate and retains its separate cleanup record.
A new diagnostic source generation then passed all six mapping/lifetime cases
and nine negative witness checks, including an exact sleeping writer chain and
normal drain. Its first four sampled observations had unstable sleep brackets;
the original attempt did not retain those values. The subsequent shared-only
campaign completed both 21-point timing grids with identical prepared binaries;
its [tables and charts](../../bench/results/10.176.26.71/bench/catalog-linux70-mm-shared-20261028/shared-mm/README.md)
retain the one-round limits. Live BPF/IRQ/NMI coverage remains unvalidated. Earlier
Linux 6.1 receipts retain their historical
identities in the [mmap integration guide](../mmap_lock/README.md).

## Correctness payload boundaries

The Linux 7 source/object checker and extracted BPF ownership fixture have
executed validation. The API, mapping, fault and completed-fault runners now
have source ports for the explicit `kdmm1-native` and `kdmm1-kd` identities.
Affected runner fixtures and all four live prerequisites in both modes passed.
The new shared campaign used fresh same-boot correctness receipts before each
timing grid and completed all 42 points. The original mapping failure, subsequent
cleanup and diagnostic pass remain separate; future source generations still
need a separate campaign and fresh same-boot prerequisites. The
[MM execution plan](../../bench/mmap_fault/LINUX70_PLAN.md) binds their required
fresh boot, kernel, host and writer-site evidence. Other retained experiment
runners remain historical where listed below.

| Payload or runner | Linux 7 scope |
| --- | --- |
| `tests/kernel/mmap_lock/payload` and `phase/payload` | Native API (137 checks) and KD API (161 checks), six mapping cases with nine negative witness checks, and eighteen fault cases passed in both modes on the recorded fresh boots. The original `contention_ok` failure, later cleanup and separate diagnostic remain retained. The shared test-only `probe_backend_write_trylock` retains try/exclusion assertions and native writer sequence/tracing. Linux 7's removed public `mmap_write_trylock` is not restored. |
| `workload_modules/mmap_phase_observer` and `phase_controls/payload` | Compile only. Both refuse module initialization with `-EOPNOTSUPP` because their retained kdmm1 instruction sites have no Linux 7 binding. |
| `page_fault_completed/payload` | Native and KD live checks each passed 64 entries, completions and returns with zero errors/misses. The current `handle_mm_fault` arguments and exact task/mm lifetime are retained. |
| `irq/payload` | Private-adapter object check only; no live IRQ/NMI result is implied. |
| `disabled/run.py` and `disabled/payload/wrappers.c` | Historical 6.1 equivalence fixture, including its removed public writer-try API. It is not a Linux 7 test or a passing skipped case. Linux 7 disabled-mode evidence is the current source/object check plus native BPF fixture controls. |

Compilation never enables a retired experiment, validates unbound probe sites
or substitutes for an executed correctness test.
