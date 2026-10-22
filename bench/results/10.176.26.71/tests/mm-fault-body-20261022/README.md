# Anonymous write-fault body stage

Status: kernel compilation passed; live correctness is pending. The selected scope and
reader/ownership rationale are in [the fault guide](../../../../../kernel_integration/mmap_lock/FAULT.md).
All performance work, p95 and the seven mutex regressions remain deferred.

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
Builds, tests, transitions and final recovery will be recorded here as they
complete. No correctness or delegation completion is claimed from prepared code.

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
cohorts and reader assertions. No fault-body live pass is claimed yet.
