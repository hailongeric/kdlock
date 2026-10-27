# Legacy kernel retirement, October 27, 2026

Completed the authorized Linux 6.1 kernel/file cleanup. The guest retains one complete
project kernel, **`6.1.159-kdclobber2`**, its source/build tree, captured bundle, matching
boot files and modules. The new recovery snapshot, **`legacy-kdclobber2-20261027`**, is verified;
**all 43 existing snapshots remain, for 44 snapshots total**. Their proposed
deletion is pending explicit approval, so historical disk states still exist.
All benchmark/test results remain evidence. Ubuntu 26.04 / Linux 7.0 is the next
adaptation target; this operation establishes no support or performance on it.

The deletion used **219 exact roots and 980,109 frozen filesystem records**
after independent source-host preservation review, followed by **32 separately
backed-up obsolete GRUB menu files**. The retained kernel's
Build ID is `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Its boot ID remains
`fd1db5e3-e2af-410f-a9f3-567ae2d07841`; all 73 loaded modules, zero taint and idle state were
verified after cleanup. No kernel build, installation or reboot occurred.

| Removed scope | Roots |
| --- | ---: |
| Historical ancestor source/build tree | 4 |
| Retired MM experiment work root | 1 |
| Superseded captured bundle | 36 |
| Retired installed project module version | 35 |
| Retired project boot file | 143 |

The 35 removed versions were project Linux 6.1 variants. Distro-managed Linux
5.15 packages, the operating system and the retained recovery version were
excluded. [Exact roots](deleted-roots.csv) and [bound receipts](retirement.json)
record the original scope; [supplementary menu files](deleted-menu-files.csv)
record the later exact boot-configuration cleanup. Live result roots and
`/root/host_fs` were not deletion targets.

## Recorded stop and completion

The first apply stopped with exit status 1 after journaling **106 of 219 roots**.
Removing the MM work root also removed one hardlink alias of each
`System.map-6.1.159-kdmm7` and `System.map-6.1.159-kdmm8`; their expected link
counts consequently changed from two to one. Their remaining recorded metadata
matched. The retained guest stayed on the same boot with zero taint.

The [hardlink proof](../../raw/tests/kernel-retirement-20261027/hardlink-accounting.json) checked all 980,109
original inventory records and the completed journal prefix, derived the exact
remaining counts, and established distinct inodes for the 113 remaining boot
files. Resume revalidated the preservation bindings, all remaining content
hashes and exact metadata with those derived counts before deletion. No
link-count check was waived.

All 113 remaining files were deleted and the retained kernel reverified, but
resume also exited 1: its boot postcondition found manually configured GRUB
entries for removed kernels. A separate exact backup and review identified
31 `42_kd_mmap_kdmm*` scripts and `/boot/grub/custom.cfg` with three obsolete
stanzas. Finalization removed those 32 files, preserved 15 other boot
configuration files, regenerated GRUB, passed `grub-script-check`, and verified
that retired entries were absent and the selected recovery default remained
valid. The finalization command exited 0. Both failed guards, both deletion
journals, preserved menu contents and the successful final checks remain bound
in the report; neither failure was relabelled a pass.

## Preservation

The retained [source/metadata archive](../../raw/tests/kernel-retirement-20261027/retired-source-and-metadata-v3.tar.gz)
is **2,930,628,726 bytes** (2.729 GiB):

```text
SHA256 9ea2769b87e2ea20f5cf7a4d670b056e2fbb747a40ac50f2a5847f4ac6179fcc
```

The [independent audit](../../raw/tests/kernel-retirement-20261027/independent-preservation-audit-v3.json)
verified **242,275 archive members** and exact coverage of **930,368
non-directory leaves**. It streamed the archive without extraction, checking
names, file bytes/hashes, types, modes and symlink targets. Six additional boot
metadata leaves and 11,982 directories are included in the member total.

| Frozen leaf disposition | Records |
| --- | ---: |
| `archived` | 230,287 |
| `deliberately-omitted` | 42,667 |
| `upstream-identical` | 657,414 |

Unchanged upstream leaves were verified against the official Linux 6.1.159
archive with SHA256
`1f207ebe93980829ecc0a18b694816f22b715e9893767731651969a168342b9e`.
Missing members, content/type differences and modes were recomputed for all nine
retired source inventories. One historical MM tree was already incomplete;
its 53,528 missing upstream members remain explicit. The archive is source and
metadata evidence, not a promise to reproduce every old built image.

Generated objects, retired installed binaries, an incomplete download and known
signing/key files were omitted by explicit recorded classes, with path, size
and SHA256 observations retained. Original omitted-byte hashes remain guest
observations because those bytes were not copied. The refinement removed exactly
four previously audited temporary vmlinux images (3,096,520,080
uncompressed bytes); every other selected member and omission remained unchanged.
Opaque historical archives remain private raw evidence and were not recursively
extracted or inspected for embedded keys. No raw archive is added to Git.

Only the final archive remains as the source-host preservation copy. The larger
intermediate archive and both temporary guest archive copies were removed after
verification; their metadata and audit receipts remain.

## Recovery and space

The new snapshot was saved and listed. Automatic approval review rejected the
proposed deletion of 42 old snapshots and one temporary pre-cleanup snapshot
before the consolidation helper executed: deletion is irreversible and its
scope was not explicit in the kernel-archive cleanup request. No snapshot was
deleted. All 43 existing snapshots and the new `legacy-kdclobber2-20261027` remain.
The [43-name removal proposal](snapshot-plan.csv) is ready for separate approval;
the new final snapshot is excluded from that proposal. Snapshot purging is
**PENDING_APPROVAL**, separate from completed kernel/file cleanup.

The guest has no pending one-shot boot, and its configured default retains
`6.1.159-kdclobber2`. All 64 host policies remain at the requested **2.0 GHz** minimum =
maximum, performance governor, with turbo disabled. Frequency readbacks do not
change the prior benchmark's failed strict timing qualification.

Guest filesystem observations from initial inventory through completed cleanup:

| Filesystem | Free bytes at inventory | Free bytes after cleanup | Observed increase (GiB) |
| --- | ---: | ---: | ---: |
| `/` | 4,365,357,056 | 53,332,357,120 | 45.604 |
| `/mnt/kdlock-builds` | 694,603,776 | 694,603,776 | 0.000 |

The frozen inventory counted 49,225,084,928 unique-inode
allocated bytes. QEMU image allocation changed from 552,722,673,664 to
577,889,820,672 bytes while saving the final snapshot; no snapshot purge
or snapshot-related space reclamation is claimed. These observations
are distinct from logical image size and guest free space; concurrent activity
can affect free-space differences. The guest interval includes preservation and
the stopped/resumed deletion and final boot-menu cleanup. The immediate
pre-deletion space observations from the first apply and resume were not
persisted and are not reconstructed as measured values.

The separate [source-host cleanup](../../../380G10/tests/kernel-retirement-20261027/README.md)
removed 24 clean historical worktrees after verifying archive refs and retained
23 worktrees containing WIP or raw evidence. That operation and this guest
cleanup preserve result histories and rejected-experiment identities.

Validation was exact inventory, preservation, retained-identity, process/drain,
boot/snapshot and final-state checking. No new builds, unit tests or benchmarks
ran for this housekeeping. See the [canonical retirement record](../../../../../docs/history/kernel-retirement-20261027.md)
for the future-kernel boundary.
