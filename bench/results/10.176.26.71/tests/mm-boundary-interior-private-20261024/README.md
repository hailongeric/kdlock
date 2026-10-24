# Retired kdmm30 attempt — stopped before candidate execution

This MM body extension is outside the [maintained lock-only scope](../../../../../kernel_integration/mmap_lock/README.md).
Its source and runners were removed from the active tree; commit
`806e9a855b97ded9c25a44d3e4b12e14c49b0c55` preserves the exact implementation.

The scope correction arrived while the owned build workflow was running.
Installation completed before the coordinator was safely stopped. **kdmm30 was
never booted and no live MM correctness cases ran.** Two basic tests passed;
there is no accepted private-interior-target milestone. A top-level build receipt
has `installed=false` because finalization was interrupted, while the separate
installation receipt correctly records `COMPLETE`. Neither is overwritten.

The build owner exited on `KeyboardInterrupt`, its private mount namespace drained,
and the unused overlay module was normally unloaded. The VM stayed on recovery
`6.1.159-kdclobber2`, boot `1602542f-b2ec-4f6b-b67d-db89dee83137`, with all 73
expected runtime modules, no test modules and no armed next boot. Recovery hashes,
installed candidate hashes, snapshot and placement were checked. No QEMU or
unrelated process was signalled. No kernel boot or file deletion followed the stop.

- [Verified stop](../../raw/tests/mm-boundary-interior-private-20261024/safe-stop.json)
  and [host state](../../raw/tests/mm-boundary-interior-private-20261024/safe-stop-host.json).
- [One essential build/install archive](../../raw/tests/mm-boundary-interior-private-20261024/scope-stop/essential.tar.gz):
  409,540 bytes, SHA-256 `61ba9f57de88e6ff52176e4cf298258d0ab6f8ae9060ab9310ea9eb9dc00e967`.
- Guest originals: `/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-private-20261024`.
- Build intermediates remain in `/dev/shm/kdmm30-cow`; the interrupted
  `/dev/shm/kdmm30-vmlinux.xz` is not a verified recovery copy. These are volatile.
- Installed candidate: `/boot/*-6.1.159-kdmm30`, `/lib/modules/6.1.159-kdmm30`,
  and `/etc/grub.d/42_kd_mmap_kdmm30`. The recovery default was preserved.

All non-Git artifacts remain available for exact-path cleanup review. The untracked,
unexecuted preboot helper was moved without data loss to the ignored cleanup
evidence directory. It was not run after the scope correction.
