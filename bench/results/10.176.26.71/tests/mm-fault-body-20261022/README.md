# Anonymous write-fault body stage

Status: prepared, not yet compiled or live-validated. The selected scope and
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
