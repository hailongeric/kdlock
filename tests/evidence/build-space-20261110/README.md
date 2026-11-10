# Build space recovery, November 10, 2026

The user authorized deletion of unused kernel outputs, then explicitly approved
live discard forwarding and guest filesystem trim. This is storage evidence,
not a kernel build or execution result. UTC timestamps are in the raw receipts.

Only regular single-link `.o`, `.a` and `.cmd` files from the inactive
`/mnt/kdlock-builds2/linux-7.0.0-38-kdscope{2,3}/build` trees were selected.
149,828 exact paths freed 41,121,030,144 allocated bytes in the guest. All 106
protected artifacts passed before/after identity and SHA256 checks. Final kernels,
modules, source, configurations, boot files, other builds and recovery snapshots
were retained. All 90,638 command files were archived and member hashes verified
before deletion.

The complete inventory, command archive, protected-file maps and unlink journal
remain in the guest at
`/mnt/kdlock-builds/kdlock-main-work/cleanup-scope23-01a1bc4f`.
The selection manifest SHA256 is
`821e71492b1b769f177a38c0315d7c68fdf230138e06cbb79188a705bb72c8e9`.
The compressed command archive SHA256 is
`9bfc6ae2e336d87255d7edd5fb985c0092ddfae0362cff467622368db571e06a`.

The host initially had 7,550,410,752 bytes free. QEMU monitor reopen changed only
the approved `drive_kdlock_builds2` discard options, then guest `fstrim` targeted
only `/mnt/kdlock-builds2` and returned zero. Actual host file allocation fell by
45,365,444,608 bytes; host available space reached 52,915,732,480 bytes. Guest
available space was 48,796,282,880 bytes. The host allocation measurement, rather
than the filesystem's reported trim count, establishes recovered host space.

The same active qcow2 device/inode remained attached. The monitor listing retained
the complete `kdlock-builddisk-clean-20261031` recovery snapshot. No snapshot was
deleted. The guest stayed on `7.0.0-38-kdlock1`, boot
`3d32656f-6162-4a0a-9304-bf383d34298d`.

`execution-summary.json` records the deletion phase before the separately approved
trim; its `trim_performed: false` is not the final trim status.
[The trim receipt](trim-builds2-01a1bc4f.json) and
[host allocation receipt](host-discard.json) record the later completed phase.
