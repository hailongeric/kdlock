# Linux 7 mmap lock adapter

[mmap-lock.patch](mmap-lock.patch) adapts only the existing local lock backend,
API routing and acquired-read lifetime transfer to Ubuntu source
`linux=7.0.0-38.38`. It is separate from [kernel.patch](kernel.patch) and the
retired Linux 6.1 patch chain. `CONFIG_KDLOCK_MMAP` defaults to **disabled**.
Preparation or compilation does not validate actual-MM execution or performance.

The adapter reuses the maintained KD mutex/rwsem implementations with namespaced
symbols. Readers stay concurrent and writers execute on their originating task.
Each dynamic mm selects Native or KD once before publication; `kd_mmap=on` selects
KD only when the option is compiled in. Static mms, including `init_mm`, stay
Native. No body delegation, prepared teardown or mapping algorithm is added.

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

Actual-mm API, cancellation, asynchronous release, per-VMA fault interaction,
recovery and performance checks remain separate requirements before enabling
the adapter in a live kernel. Earlier Linux 6.1 receipts retain their historical
identities in the [mmap integration guide](../mmap_lock/README.md).

## Correctness payload boundaries

The Linux 7 source/object checker and extracted BPF ownership fixture are the
current validation entry points. The retained live experiment runners still
bind their dated 6.1 kernel identities and are historical references.

| Payload or runner | Linux 7 scope |
| --- | --- |
| `tests/kernel/mmap_lock/payload` and `phase/payload` | Compile port for real-mm APIs. The shared test-only `probe_backend_write_trylock` checks the private adapter, with native writer sequence/tracing, while retaining every try/exclusion assertion. Linux 7's removed public `mmap_write_trylock` is not restored. Live runners remain unported. |
| `workload_modules/mmap_phase_observer` and `phase_controls/payload` | Compile only. Both refuse module initialization with `-EOPNOTSUPP` because their retained kdmm1 instruction sites have no Linux 7 binding. |
| `page_fault_completed/payload` | Config/API compile port. The current `handle_mm_fault` arguments and exact task/mm lifetime are retained; completed-fault/return behavior has no new live validation. Its dated runner remains historical. |
| `irq/payload` | Private-adapter object check only; no live IRQ/NMI result is implied. |
| `disabled/run.py` and `disabled/payload/wrappers.c` | Historical 6.1 equivalence fixture, including its removed public writer-try API. It is not a Linux 7 test or a passing skipped case. Linux 7 disabled-mode evidence is the current source/object check plus native BPF fixture controls. |

Compilation never enables a retired experiment, validates unbound probe sites
or substitutes for an executed correctness test.
