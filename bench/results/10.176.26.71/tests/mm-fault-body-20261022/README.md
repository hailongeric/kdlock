# Anonymous write-fault body stage

Status: the narrow functional milestone passed all 13 serial correctness sessions;
the VM is back on recovery. The selected scope and
reader/ownership rationale are in [the fault guide](../../../../../kernel_integration/mmap_lock/FAULT.md).
All performance work, p95 and the seven mutex regressions remain deferred.

The real `do_anonymous_page_install()` body completed 129 times on a different
task. Sixteen logged completions matched both the original thread and the
physical page installed in its real PTE (page-table entry). All 400 user-written
pages passed content checks. Readers stayed concurrent and local. These are
execution and correctness counts, not performance or variance measurements.

The original MM VM is `root@10.176.26.71:2222`, with 64 vCPUs and 24 GiB RAM.
Initial inspection confirmed recovery boot
`d4980f92-14c5-4bed-9749-beac916e76d3`, release `6.1.159-kdclobber2`, exactly
73 loaded modules, idle state, original host placement and the real recovery
snapshot `before-mutex-kdonly-20261017T140354Z`. The unrelated source-host nano
campaign's files remain excluded from this work.

The new candidate is `/root/kdlock-kernel-work/mm-fault-body-20261022/candidate-1/linux`,
release `6.1.159-kdmm3`, with a distinct captured baseline. The installed `kdmm1`,
validated advice `kdmm2` and recovery trees remain unchanged. Old unused
`kdstatic1/2` and `kdclobber1` module build outputs were byte-verified into
compressed archives under `/root/kdlock-maintenance/kernel-module-archives-20261022/`
before removing those build copies. Their installed modules and captured kernel
artifacts were retained. This recovered approximately 10.3 GiB of additional
root space for the independent candidate; the archive inventories preserve all
17,019 module files.

Raw inspection and subsequent results belong in
`bench/results/10.176.26.71/raw/tests/mm-fault-body-20261022/`; the guest stage is
`/root/kdlock-evidence/10.176.26.71/tests/mm-fault-body-20261022/`.
The [machine-readable summary](correctness-result.json) binds results to the
archives, exact source revisions and final recovery health. The old
[kdmm2 advice baseline](../mm-body-20261022/README.md) remains distinguishable;
its original 1,690 remote completions are not pooled with this run.

## Build stage

Kernel source commit `1e2ddb2` built successfully as `6.1.159-kdmm3`, Build ID
`51312746083c9b4ba76d668a46eabb7c4942866a`. Its captured manifest SHA-256 is
`7190c36fb1a0ccd43757e5ac11b32814b150971f951290dc74eda52b4112ad45`.
The basic C checks, prior advice receipt checks, image and all 73 runtime modules
completed in `build-control-1`; recovery and prior MM boot artifacts remained
byte-identical. The new tree stays on root ext4, with about 16 GiB still free.

Probe preparation `test-preparation-1` at test commit `82d04f1` failed module
linking: its read-only cancellation observer indirectly referenced unexported
`pmd_clear_bad`. No module loaded and no reboot or fault workload began. The
observer now refuses bad/huge/device PMD entries directly, without attempting
page-table repair. The failed frozen source and log remain under `test-build-1`.

`test-preparation-2` linked the corrected module, then failed the userspace
client's warnings-as-errors build: a printed counter needed an explicit type
conversion, and a checked allocation pointer needed initialization for the
compiler's control-flow analysis. Both are test-only fixes; no admission or
correctness check changed. That frozen attempt remains under `test-build-2`.

`test-preparation-3` compiled both probes and passed all five new receipt checks;
installation preserved recovery and the previous MM images. Native control run
`native-1`, boot `9770cece-5391-4796-a35d-08809111a0f3`, passed basic/API,
separate untouched-mmap, page-fault and completed-file-fault checks and ended idle
with 73 modules. Boot logs retain the existing empty `fd0` floppy I/O diagnostics.
Before KD execution, static review moved pthread creation before the test holds
two mmap readers: creating user stacks can require mmap write ownership. This
avoids a test-generated lock conflict while preserving the required queued
cohorts and reader assertions. `test-preparation-4` at `5a9a9ba` recompiled the
probes and passed all five receipt checks before any live fault-body run.

## Completed serial correctness

The kernel remained at source commit `1e2ddb2` throughout. Native controls used
the `ce2c5ae` test snapshot; the corrected fault-cohort ordering and every live
KD fault probe used `5a9a9ba`. The advice body source and its earlier test stayed
unchanged. Final evidence includes each frozen source and binary hash.

| Run / task | Result |
| --- | --- |
| `native-1/api`, `kd-1/api` | Both basic C programs passed in each mode; 121 Native and 139 KD API checks; zero errors and exact idle. |
| `kd-1/body` | Preserved advice implementation: 2,048 supported calls, 1,736 actual remote completions, 15 handbacks/ACKs, 512 sticky local calls; two local readers; cleanup passed. |
| `kd-1/body-cancellation` | One queued cancellation before VMA effects; healthy leader completed; both requests retired. |
| `kd-1/fault-body` | 256 supported first-write installations, including 129 remote; 16 PTE-bound completion records; all 400 pages verified, 3,277,095 content/control checks, zero errors. Two extra readers remained held through all 129 remote installations. |
| `kd-1/fault-body` refusal phases | 16 locked-mapping writes completed through the original local path, with 15 matched remote handback/ACK identities. One sticky refusal; 128 subsequent ordinary writes stayed local with no new remote bodies or ACKs. |
| `kd-1/fault-cancellation` | One healthy real kernel write and one fatal cancellation before PTE installation. Healthy PTE present, victim PTE absent; returns `0` and `-EFAULT`; original read acquisition released and both workers joined. Nonfatal signal did not retire the queued request. |
| `kd-1/fault-retry` | One exact userfaultfd refusal/ACK; another mmap writer completed while the fault was unresolved. The original store completed after resolution, contents matched, and one later ordinary fault remained local. No remote body was counted for the refused fault. |
| `native-1/mmap`, `kd-1/mmap` | Six cases each, including 81,000 untouched mapping cycles and separate 1/16-worker lifetime cases; zero payload faults. |
| `native-1/page-fault`, `kd-1/page-fault` | 18 cases each, final 596 checks; 16 remote/fork/COW and 16 retry workers joined. These are separate from the new body probe and from mmap. |
| `native-1/completed-fault`, `kd-1/completed-fault` | 64 real file-fault entries/returns/completions per mode, no missed/error/retry counts, writer reacquisition verified. These bodies remain local. |

Native boot: `9770cece-5391-4796-a35d-08809111a0f3`.
KD boot: `bdd22a66-c7f6-4394-92d5-155310660837`.
Final recovery boot: `11968a2a-23e4-4474-95b8-a636a9858fbd`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Final health confirmed all 73 modules,
no remaining fault workers or project modules, idle evidence, no new kernel
fault, all recovery hashes and all 90 prior advice installation files preserved.
The real recovery snapshot and original host placement were rechecked before
transitions. No in-flight run was interrupted and no nano campaign file was edited.

## Commands and artifacts

From `380G10`, the completed commands were:

```sh
python3 bench/results/10.176.26.71/tests/mm-fault-body-20261022/validate.py --mode native --run native-1
python3 bench/results/10.176.26.71/tests/mm-fault-body-20261022/validate.py --mode kd --run kd-1
python3 bench/results/10.176.26.71/tests/mm-fault-body-20261022/validate.py --mode recovery --run recovery-1
python3 bench/results/10.176.26.71/tests/mm-fault-body-20261022/seal.py
python3 bench/results/10.176.26.71/tests/mm-fault-body-20261022/audit.py
```

Each command followed successful completion and drain of its predecessor. Run
IDs and archive destinations cannot be reused. For a later approved repeat,
use the fresh run names in the [fault guide](../../../../../kernel_integration/mmap_lock/FAULT.md)
and the [individual guest commands](../../../../../tests/kernel/mmap_lock/fault_body/README.md).
The archiver used the maintained recovery checks without changing admission.

Five archives reside in
`../../raw/tests/mm-fault-body-20261022/seal-1/guest-archives-1/` relative to this
report directory, and at
`/root/kdlock-evidence/10.176.26.71/tests/mm-fault-body-20261022-archives-1/`
in the VM. The source-host paths are linked below:

| Archive | Contents | SHA-256 |
| --- | --- | --- |
| [native.tar.gz](../../raw/tests/mm-fault-body-20261022/seal-1/guest-archives-1/native.tar.gz) | Four Native sessions | `fb0a6dbdb3fa52a65db45735a8da08ff63827cf2dc1dbf83fb265d11b19734d6` |
| [kd.tar.gz](../../raw/tests/mm-fault-body-20261022/seal-1/guest-archives-1/kd.tar.gz) | Nine KD sessions | `798360e3875b9304b5f69321d865820f3ab5148c5ca8b6a2fb942a926b22a1aa` |
| [build.tar.gz](../../raw/tests/mm-fault-body-20261022/seal-1/guest-archives-1/build.tar.gz) | Kernel source, configuration, capture and build evidence | `e3124bc9243edb3823ae6cc36b67f11adfe20280cfe4587bf505280d56225383` |
| [preparation.tar.gz](../../raw/tests/mm-fault-body-20261022/seal-1/guest-archives-1/preparation.tar.gz) | Both failed and both successful probe preparations | `1d55b048d451a0ad651d05e677de7769b84353fd5ab3c2214d9171a464ec9c76` |
| [metadata.tar.gz](../../raw/tests/mm-fault-body-20261022/seal-1/guest-archives-1/metadata.tar.gz) | Recovery, installation, controls and archived-old-module inventories | `2e2f64856b454c43a5e67328d9573c2a953b976eb38331df039a2d871f18d4e5` |

The [offline audit](../../raw/tests/mm-fault-body-20261022/audit.json) passed
11,087 checks with zero mismatches: 1,577 files, 600 source bindings, exact
physical-page/ACK receipts, retained failures, all 13 session results and final
recovery. Archive manifest SHA-256:
`36cfccfe6a9a570852f245eedef0cf325080fff9d5a0a6ed851805123c6193ef`.
No archived code was executed during that source-host audit.

## Limits and next extension

This validates only explicitly enabled private anonymous first-write installation
on this x86-64 configuration. Allocation/charging, task fault accounting and
retry remain on the caller; read faults stay local. Existing COW/file/remote-mm
tests preserve local behavior and do not establish their body delegation.
The two preparation failures were fixed; there were no failed live correctness
sessions. Slot exhaustion, a forced 256-request batch boundary, PTE-installation
races, cancellation after admission, swap pressure, huge pages, alternate memory
policies, multi-generation LRU, RT/lockdep, and oversubscribed progress remain
untested or deliberately outside admission. No full suite was requested or run.

Timing, variance, p95 and the seven mutex regressions remain deferred/unresolved;
this milestone does not accept performance. The next smallest useful candidate
is actual whole-VMA munmap of one isolated, never-faulted anonymous mapping under
the advice writer queue. Its allocator, architecture, notifier and teardown
dependencies still need review and implementation, as detailed in the
[extension rationale](../../../../../kernel_integration/mmap_lock/FAULT.md#next-useful-mmapmunmap-extension).
General mmap/munmap and page-fault delegation are not established.
