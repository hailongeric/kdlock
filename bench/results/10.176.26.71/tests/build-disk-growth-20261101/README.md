# Second build-disk expansion

On November 1 the user approved expanding the second build disk so the existing
MM preparation workflow could retain its 50 GiB free-space requirement without
removing older builds or results. The VM was idle before the operation.

QEMU drive `drive_kdlock_builds2`, backed by
`/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2`, grew from 96 GiB
to 160 GiB with `block_resize drive_kdlock_builds2 160G`. The guest rescanned
`/dev/sdc`, verified 171,798,691,840 device bytes, and ran `resize2fs /dev/sdc`
on its existing whole-device ext4 filesystem at `/mnt/kdlock-builds2`.
No partition or filesystem was recreated, and no old build or result was removed.

The completed guest receipt reports 41,943,040 4-KiB filesystem blocks and free
space increasing from 25,286,492,160 to 92,928,032,768 bytes. This is capacity
at that observation, not a promise of free space for later operations.
The first build disk and normal kernel boot were unchanged.

[The exact receipt](guest.json), [monitor transcript](monitor.txt),
[initial inspection](before.txt) and [design](plan.md) retain their original
bytes; [the manifest](manifest.json) records their hashes. Kernel preparation,
compilation and mmap1 performance are separate steps and are not validated by
this expansion.
