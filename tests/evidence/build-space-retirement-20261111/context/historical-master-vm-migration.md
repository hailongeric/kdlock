# VM storage and Ubuntu 26.04 migration, October 27, 2026

The VM migration is complete. The active environment is **Ubuntu 26.04.1 LTS /
Linux `7.0.0-38-generic`**. Snapshot consolidation, reviewed storage cleanup and
the 100 GiB data-disk expansion are complete. Linux 7.0 is the adaptation target;
KD has not yet been ported or validated on this kernel.

The user explicitly authorized removal of the 43 old and temporary VM snapshots,
retaining only `legacy-kdclobber2-20261027`, further guest storage housekeeping,
100 GiB of additional capacity, and an upgrade to **Ubuntu 26.04 / Linux 7.0**.
This follows the [Linux 6.1 retirement](kernel-retirement-20261027.md). Linux
`6.1.159-kdclobber2` is a legacy recovery reference; no further adaptation targets
that kernel. Existing results retain their original platform identities.

The [operation report](../../bench/results/10.176.26.71/tests/vm-ubuntu2604-migration-20261027/README.md)
owns exact receipts and completion status. This record separates the requested
migration from verified results; installing or booting a new OS does not establish
KD compatibility, correctness or performance on its kernel.

## Recorded status

| Work | Status |
| --- | --- |
| Delete the exact 43 approved snapshots | Complete: 43 removed; monitor lists only `legacy-kdclobber2-20261027` |
| Remove reviewed redundant guest files/directories | Complete: 50,037 files and 153 directories removed; manifests and protected inputs retained |
| Expand the data disk from 32 to 132 GiB | Complete; device and ext4 grew online, retaining UUID and checked recovery-file hashes |
| Upgrade Ubuntu 22.04 through 24.04 to 26.04 | Complete: Ubuntu 26.04.1 LTS |
| Boot and record Linux 7.0 | Complete: `7.0.0-38-generic`, package `7.0.0-38.38`, taint zero |
| Adapt and validate KD on Linux 7.0 | Separate future development; no compatibility claim |

## Snapshot boundary

The prior automatic approval rejection remains part of the retirement history.
The user's subsequent explicit approval covers the exact 43 names in the
[authorization receipt](../../bench/results/10.176.26.71/raw/tests/vm-ubuntu2604-migration-20261027/snapshot-authorization.json).
It excludes `legacy-kdclobber2-20261027`. The deletion journal and final snapshot
inventory determine completion; a requested deletion is not itself evidence that
the tag was removed. Benchmark reports, raw results and source archive refs are
outside this snapshot purge.

The [bound snapshot receipt](../../bench/results/10.176.26.71/tests/vm-ubuntu2604-migration-20261027/snapshot-receipt.json)
records all **43 approved removals** and the final monitor inventory containing
only `legacy-kdclobber2-20261027`. Host available space increased from
84,898,578,432 to 496,913,866,752 bytes, an observed **383.719 GiB** increase.
The two image files' allocated space decreased by 383.720 GiB. Apparent image
file length, virtual disk capacity and allocated storage remain distinct;
concurrent host activity can affect the free-space observation. Subsequent
read-only per-image inspection verified exactly the retained tag in both qcow2
images, including after data-disk expansion.

The first 41 deletions completed with a fresh snapshot listing after each.
The 42nd command, for `before-mutex-kdonly-20261017T140354Z`, exceeded the
launcher's 120-second monitor timeout. The last verified listing still contained
that tag, `before-kernel-retirement-20261027`, and the retained legacy tag.
QEMU remained alive with increasing CPU and I/O counters; a later informational
monitor connection also timed out before receiving its banner. A client timeout
does not cancel or prove completion of the underlying disk operation. A
subsequent responsive monitor listing then verified the 42nd tag's removal and
both expected remaining tags. The final temporary snapshot deletion was started
only after that reconciliation and completed with a final listing containing
only the retained tag. The original helper's exit status 1 and its timeout were
not relabelled as success. Guest housekeeping, expansion and release upgrades
were deferred until the snapshot operation had completed.

Read-only process observations distinguish continuing CPU/metadata activity
from verified completion. The initial observation parser split `/proc` task
statistics on whitespace and misindexed names containing spaces; its main-thread
sample was valid, but the affected vCPU fields are not reliable. The subsequent
diagnostic records parse fields after the final `)` and distinguish aggregate
process statistics from actual per-thread statistics. A separate bounded GDB
stack inspection attached briefly and detached successfully; it confirmed
`qcow2_update_snapshot_refcount` within the pending `hmp_delvm` call. Its two
innermost frames lacked symbols. Fragmented discard-list accumulation or
refcount-cache work remain possible explanations, not confirmed causes. No
forced termination or disk repair is implied by those hypotheses.

The retained snapshot records the former Ubuntu 22.04 environment and a 32 GiB
data disk. QEMU 8.2.2 with qcow2 version 3 supports growing an image that retains
internal snapshots; its restore code restores the snapshot's saved disk size.
Restoring this legacy snapshot therefore also returns the data disk to **32 GiB**
and rolls back subsequent active disk contents. It is a recovery action, not a
way to retain new-platform files. These conclusions follow the upstream
[resize implementation](https://github.com/qemu/qemu/blob/v8.2.2/block/qcow2.c#L3999-L4006)
and [snapshot restore implementation](https://github.com/qemu/qemu/blob/v8.2.2/block/qcow2-snapshot.c#L725-L739).

## Storage scope

The selected expansion target is the existing data disk mounted at
`/mnt/kdlock-builds`, which had approximately 663 MiB available. Its host image is
`/home/eric/vm/qemu-disks/sda.qcow2`, QEMU drive `drive_data1`, and guest device
`/dev/sdb`. The device contains ext4 directly, with no partition table. Its
filesystem UUID is `7cfd7ee5-fdee-4a4b-8db3-a22fc5806da0`.

The requested increase is interpreted as **100 GiB (107,374,182,400 bytes)**,
from 34,359,738,368 to 141,733,920,768 bytes. The root filesystem already had
approximately 50 GiB free. Growing the data disk supplies space for new kernel
sources and builds without moving the retained legacy tree. Virtual capacity,
guest filesystem availability and host physical allocation are separate values;
sparse capacity is not reserved host storage.

The [expansion receipt](../../bench/results/10.176.26.71/tests/vm-ubuntu2604-migration-20261027/expansion-receipt.json)
records the completed online growth. Ext4 reported 139,179,020,288 filesystem
bytes and 102,077,005,824 available bytes afterward, approximately **95.067 GiB
available**. Its mount, UUID and checked `.config`, `vmlinux` and `bzImage`
hashes remained unchanged; the boot ID also remained unchanged.

The first resize request incorrectly supplied an unsuffixed byte value to HMP,
whose unsuffixed size is interpreted as MiB. QEMU rejected it with
`Failed to grow the L1 table: File too large`; the device remained 32 GiB and
filesystem resize was not executed. The corrected explicit `132G` request
succeeded before `resize2fs` and final verification. Both the exit-1 first
attempt and successful correction remain in the receipt.

The [guest housekeeping receipt](../../bench/results/10.176.26.71/tests/vm-ubuntu2604-migration-20261027/storage-cleanup-receipt.json)
records removal of **50,037 files and 153 directories** under an exact inventory.
The scope was three obsolete ancestor-kernel module archives, pip cache
contents, two empty scratch directories and one 50,000-empty-file scratch tree.
The old module archives were deliberately retired generated binaries, not
claimed verified duplicates; their hashes and seven metadata/manifests remain.
A fresh scan found no project jobs, project modules, process references or scan
errors before deletion. Live results, source/recovery inputs, useful
environments and `/root/host_fs` remained outside the removal scope.

Root available space changed from 53,306,802,176 to 58,726,858,752 bytes,
an observed **5.048 GiB** increase. Data available space changed from
102,077,005,824 to 102,079,242,240 bytes. These observations cover guest
housekeeping after expansion, separately from snapshot reclamation.

The [preserved guest log](../../bench/results/10.176.26.71/raw/tests/vm-ubuntu2604-migration-20261027/post-snapshot-guest-log.json)
records taint **16384** and **29 soft-lockup lines**, alongside RCU/watchdog
diagnostics, on the unchanged legacy boot. The earlier taint was zero. These
are observations in the maintenance interval; no isolated causal attribution
is established. The completed storage work is not evidence of an untainted
runtime or a performance qualification. No new KD test or benchmark pass is
claimed. This storage checkpoint preceded the release upgrades.

## Release and kernel transition

The completed LTS route was **Ubuntu 22.04 → 24.04 → 26.04**. Ubuntu's
[26.04 release notes](https://documentation.ubuntu.com/release-notes/26.04/)
require earlier LTS releases to reach 24.04 first. The
[LTS change summary](https://documentation.ubuntu.com/release-notes/26.04/summary-for-lts-users/)
identifies Linux 7.0 as the 26.04 generic kernel. Follow the official
[server upgrade procedure](https://ubuntu.com/server/docs/how-to/software/upgrade-your-release/).
At the user's request, full upgrade transcripts are not archived. Only concise
OS/kernel identity and validation outcomes are retained for this transition;
the earlier snapshot/storage evidence remains separate.

The first stage completed and the guest booted **Ubuntu 24.04.5 LTS** with
**`6.8.0-147-generic`**, Build ID
`00a89b4c4179276e34c5b676e5e455747b3deab3`. The
[intermediate boot identity](../../bench/results/10.176.26.71/raw/tests/vm-ubuntu2604-migration-20261027/noble-boot.json)
records taint zero, 64 CPUs across the expected two NUMA nodes, matching kernel
headers, working SSH/configuration checks, expected mounts and no failed
services. This is an intermediate upgrade stage, not a KD adaptation target.
The second stage completed, and the
[final platform receipt](../../bench/results/10.176.26.71/tests/vm-ubuntu2604-migration-20261027/platform-receipt.json)
binds the verification after boot and final housekeeping:

| Final identity | Value |
| --- | --- |
| OS | Ubuntu 26.04.1 LTS |
| Running kernel | `7.0.0-38-generic` |
| Image and headers package version | `7.0.0-38.38` |
| GNU Build ID | `338e542e384c46228f7a378babc0f9bb2b6a5997` |
| Boot ID | `1b0a9749-944e-48a6-93c7-518acf9e500a` |
| Installed matching headers | `/usr/src/linux-headers-7.0.0-38-generic` |
| Taint / failed services | Zero / none |

Package consistency, SSH configuration, mounts, headers, boot selection and
CPU/NUMA checks passed. The guest has 64 CPUs across two nodes and the expanded
132 GiB data device. Root/data available space was 57,117,138,944 /
102,079,242,240 bytes after housekeeping. Source and evidence directories remain
on their expected mounts; this is a presence/mount check, not a full content
rehash. The three checked legacy source/build files still match their recorded
hashes. No unchanged-old-initrd claim is made.

Final host checks confirmed all 64 policies at the requested 2.0 GHz minimum =
maximum, `performance` governor and turbo disabled. Each vCPU retains its
same-numbered host CPU; seven auxiliary threads use CPU 63. The two 12 GiB RAM
backends retain their host NUMA bindings. The monitor and both image files list
only the legacy snapshot. These are configured-state checks, not effective
frequency or strict timing qualification. The new kernel reports preemption
`full (lazy)`, differing from legacy voluntary preemption.

The first preboot checker incorrectly rejected an empty `next_entry=` GRUB
variable. Inspection confirmed there was no pending one-shot boot; a corrected
probe passed without changing GRUB state. The original failed check remains
explicit as a checker false positive. Two final journal error entries were
inspected transiently and identified as reads from the empty `fd0` floppy
device; their text was not archived. No soft-lockup or critical-kernel diagnostic
matched the final boot checks.

Final housekeeping removed `/var/log/dist-upgrade` (15 files and three
directories) without archiving its contents, confirmed the exact upgrader
temporary directories absent, and emptied 38,900,578 bytes of downloaded APT
cache. General system APT logs and journals were outside that selected cleanup.
It also removed the temporary upgrade SSH forward and ten unused intermediate
kernel/Python packages. Only the active 7.0 boot image and the legacy 6.1
recovery image remain. The legacy snapshot remains recovery-only; it is not a
snapshot of the new 7.0 environment.

New KD work must review the kernel APIs, caller contracts, hook/lifetime rules
and JIT admission against the new source/configuration. Existing Linux 6.1
results and passed tests do not transfer automatically. The
[project roadmap](../ROADMAP.md) and its open validation gates remain in force.
