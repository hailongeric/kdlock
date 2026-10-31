# Authorized build-disk growth

The user approved expanding the second build disk on November 1. Grow only
QEMU drive_kdlock_builds2, backed by
/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2, from 96 GiB to
160 GiB through the live monitor. The guest mounts its whole-device ext4 on
/dev/sdc at /mnt/kdlock-builds2. Rescan that device, verify 160 GiB, then grow
its existing ext4 filesystem with resize2fs. Do not recreate a filesystem,
remove data, alter another disk, or use an external writer on the live image.
Retain before/after device size, filesystem, available capacity and monitor
responses. This provides the existing 50 GiB preparation reserve without
removing any previous builds or measurements. Host free capacity was 134 GiB.
All live checks drained before this operation; no timing is active.
