# VM storage and Ubuntu 26.04 migration

Operation date: October 27, 2026. **Storage and OS migration complete.** The VM
now runs **Ubuntu 26.04.1 LTS / Linux `7.0.0-38-generic`**. The user authorized
deletion of the exact 43 old/temporary VM snapshots while retaining
`legacy-kdclobber2-20261027`, further reviewed guest housekeeping, 100 GiB of
additional disk capacity, and a staged upgrade to Ubuntu 26.04 with Linux 7.0.
Final OS/kernel and health checks passed; KD adaptation remains unvalidated.
The approved snapshot cleanup is complete: **43 removed, one retained**.
The data device and ext4 filesystem have also grown online from **32 to 132 GiB**.
Reviewed guest housekeeping removed **50,037 files and 153 directories**.

The [canonical migration record](../../../../../docs/history/vm-ubuntu2604-migration-20261027.md)
defines the platform and recovery boundary. The earlier
[kernel retirement report](../kernel-retirement-20261027/README.md) retains its
original cleanup, preservation and stopped-guard evidence. The new explicit
snapshot approval supersedes that operation's pending-approval state without
rewriting its history.

## Snapshot cleanup

The [authorization receipt](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-authorization.json)
binds the prior snapshot-state hash, the 43 exact removal names and the one
retained name. The [deletion journal](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-removals.jsonl)
records each completed monitor command and verified resulting inventory.
The first **41 removals** completed and were verified by a new snapshot listing.
The 42nd command, for `before-mutex-kdonly-20261017T140354Z`, exceeded the
launcher's 120-second monitor timeout. A subsequent responsive monitor listing
[reconciled its removal](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-reconciled-inspect.json):
only `before-kernel-retirement-20261027` and `legacy-kdclobber2-20261027` remained.
The final temporary snapshot deletion was started after reconciliation and
[completed](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-completed.json).
The final monitor listing contains only **`legacy-kdclobber2-20261027`**.
The compact [snapshot receipt](snapshot-receipt.json) preserves all 43 exact
removals, space observations and source-receipt hash bindings. Subsequent
[per-image verification](../../raw/tests/vm-ubuntu2604-migration-20261027/per-image-snapshots.json)
passed for both qcow2 images after expansion: each contains exactly the retained
tag, and the system image retains its saved VM state.

QEMU remained alive with increasing CPU and I/O counters. A subsequent
informational monitor connection timed out before receiving its banner. The
client timeout neither cancels the deletion nor proves that it completed.
The timed-out deletion was not repeated and QEMU was not forcibly terminated.
Its original helper exit status 1 remains recorded; later reconciliation
established the result without relabelling the timed-out call. Other guest
storage work, expansion and the OS upgrade were deferred until snapshot work
completed. No snapshot restore was performed.

The [initial process observations](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-timeout-process-observations.json)
preserve a parser limitation: whitespace splitting misindexed task-stat fields
for vCPU names containing spaces. Their main-thread fields were valid. The
subsequent [diagnostic collector](../../raw/tests/vm-ubuntu2604-migration-20261027/collect-snapshot-processing-diagnostics.py)
parses after the closing `)` and separates aggregate process and per-thread
statistics. CPU and metadata activity support continued processing, not a
completion claim. Fragmented discard-list traversal and refcount-cache work
are source-based hypotheses, not confirmed causes. The
[diagnostic receipt](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-processing-diagnostics.md)
links its precise capture and interpretation limits; the later 10-second sample
showed 99.74% main-thread CPU with only 64 KiB of physical reads and writes.
A separate [bounded stack inspection](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-main-stack.stdout)
briefly attached and detached with exit status 0. It confirmed
`qcow2_update_snapshot_refcount` inside the pending deletion; the innermost two
frames lacked symbols, so the exact costly mechanism remains unproven. The
[command receipt](../../raw/tests/vm-ubuntu2604-migration-20261027/snapshot-main-stack-command.json)
records no memory/register writes or inferior function calls.

This snapshot operation does not delete benchmark reports, raw results or Git
archive refs. The retained `legacy-kdclobber2-20261027` snapshot remains a legacy
Ubuntu 22.04 / Linux 6.1 recovery point, not the new development environment.

| Host storage observation | Before snapshot deletion | After snapshot deletion |
| --- | ---: | ---: |
| Available filesystem bytes | 84,898,578,432 | 496,913,866,752 |
| System-image allocated bytes | 534,678,401,024 | 132,166,782,976 |
| Data-image allocated bytes | 43,422,904,320 | 33,918,676,992 |

Available host space increased by **383.719 GiB** over the operation, while
image allocation decreased by **383.720 GiB**. These are separate observations;
other host activity can affect filesystem availability. Allocated bytes are
physical filesystem blocks; apparent image length and virtual disk capacity
are different quantities. No guest filesystem free-space gain is inferred from
snapshot removal.

## Capacity and housekeeping

The chosen target is QEMU `drive_data1`, host
`/home/eric/vm/qemu-disks/sda.qcow2`, guest `/dev/sdb`, mounted as ext4 at
`/mnt/kdlock-builds`. It has no partition table. The observed filesystem UUID is
`7cfd7ee5-fdee-4a4b-8db3-a22fc5806da0`.

| Capacity | Bytes | GiB |
| --- | ---: | ---: |
| Observed starting data device | 34,359,738,368 | 32 |
| Requested increase | 107,374,182,400 | 100 |
| Verified final data device | 141,733,920,768 | 132 |

The [expansion receipt](expansion-receipt.json) records completion, checked
recovery-file hashes, the unchanged UUID/mount/boot identity, and raw receipt
bindings. Ext4 reported 139,179,020,288 filesystem bytes with **102,077,005,824
bytes available (95.067 GiB)** afterward, up from 694,603,776 available bytes.
Device capacity, filesystem reporting and host physical allocation are separate
values. Subsequent reviewed guest housekeeping completed under the exact scope
below; retained results, source/recovery inputs, useful environments and
`/root/host_fs` remained outside that scope.

The first helper exited 1 after HMP rejected
`block_resize drive_data1 141733920768` with
`Failed to grow the L1 table: File too large`. HMP treats an unsuffixed size as
MiB, so that byte-count form was incorrect. The recorded device still measured
32 GiB after rejection, and no filesystem resize had run. The corrected
explicit **`block_resize drive_data1 132G`** succeeded, followed by online
`resize2fs` and final checks. The failed attempt remains explicit in the bound
[rejection receipt](../../raw/tests/vm-ubuntu2604-migration-20261027/expansion-first-rejection.json).

QEMU is version 8.2.2 and the data image is qcow2 compat 1.1, corresponding to
version 3. Upstream supports resizing such images with internal snapshots.
Restoring the legacy snapshot also restores its saved **32 GiB** device size
and prior disk contents; subsequent active changes are rolled back. See the
[QEMU resize source](https://github.com/qemu/qemu/blob/v8.2.2/block/qcow2.c#L3999-L4006)
and [restore source](https://github.com/qemu/qemu/blob/v8.2.2/block/qcow2-snapshot.c#L725-L739).

The [housekeeping receipt](storage-cleanup-receipt.json) records the exact
**50,037-file / 153-directory** removal and preserved metadata bindings:

| Selected scope | Removal |
| --- | --- |
| `/root/kdlock-maintenance/kernel-module-archives-20261022/` | Only the three `linux-6.1.159-{kdstatic1,kdstatic2,kdclobber1}.tar.gz` files |
| `/root/.cache/pip/` | 34 cache files and 150 child directories; root retained |
| `/mnt/kdlock-builds/src_empty` | Empty scratch directory |
| `/mnt/kdlock-builds/dst_empty` | Empty scratch directory |
| `/mnt/kdlock-builds/dst_50000_files` | 50,000 zero-byte scratch files and their directory |

The module archives were deliberately retired generated binaries for removed
ancestor kernels; they were not claimed to be verified duplicates. Their exact
hashes, manifests and removal metadata remain, including seven protected
metadata files. The guarded cleanup revalidated its plan and checked process
references; the fresh scan found no project jobs, project modules, references
or scan errors. The full per-file plan and intent/completion journal remain in
raw evidence, with compact bindings in the public receipt.

| Guest available bytes | Before housekeeping | After housekeeping |
| --- | ---: | ---: |
| `/` | 53,306,802,176 | 58,726,858,752 |
| `/mnt/kdlock-builds` | 102,077,005,824 | 102,079,242,240 |

Root availability increased by **5.048 GiB** over this interval. This is
separate from the earlier 100 GiB capacity growth and host snapshot-space
reclamation; concurrent filesystem activity can affect available-space deltas.

The [preserved guest log](../../raw/tests/vm-ubuntu2604-migration-20261027/post-snapshot-guest-log.json)
contains **29 soft-lockup lines**, RCU/watchdog diagnostics and taint **16384**
on the unchanged legacy boot. The earlier state had taint zero. These records
belong to the maintenance interval; the cause has not been isolated. This
checkpoint does not establish an untainted guest or timing qualification.

## Release transition and validation

The completed supported path was Ubuntu **22.04 → 24.04 → 26.04**, followed by
verification of the running **Linux 7.0** package and build. The official
[26.04 release notes](https://documentation.ubuntu.com/release-notes/26.04/)
and [LTS summary](https://documentation.ubuntu.com/release-notes/26.04/summary-for-lts-users/)
define that upgrade route and kernel family. Per the user's instruction, full
upgrade transcripts are not archived; concise boot identities and validation
outcomes are retained. The earlier snapshot/storage diagnostic evidence remains
separate from the OS upgrade.

The first stage completed and
[boot verification](../../raw/tests/vm-ubuntu2604-migration-20261027/noble-boot.json)
passed on **Ubuntu 24.04.5 LTS / `6.8.0-147-generic`**, Build ID
`00a89b4c4179276e34c5b676e5e455747b3deab3`. The new boot had taint zero,
64 online CPUs, the expected NUMA topology, matching installed headers, expected
mounts, successful package/SSH checks and no failed services. The data device
still measured 132 GiB. This was an intermediate platform, and its unused
kernel packages were removed after the final upgrade.

The compact [platform receipt](platform-receipt.json) binds the final
verification after the second upgrade, reboot and housekeeping:

| Verified final identity | Value |
| --- | --- |
| OS | Ubuntu 26.04.1 LTS |
| Kernel | `7.0.0-38-generic` |
| Image and headers version | `7.0.0-38.38` |
| GNU Build ID | `338e542e384c46228f7a378babc0f9bb2b6a5997` |
| Boot ID | `1b0a9749-944e-48a6-93c7-518acf9e500a` |
| Header build tree | `/usr/src/linux-headers-7.0.0-38-generic` |
| Kernel taint / failed services | Zero / none |
| Root available | 57,117,138,944 bytes (53.194 GiB) |
| Data available | 102,079,242,240 bytes (95.069 GiB) |

All recorded final guest gates passed: package consistency, SSH configuration,
boot selection, expected mounts and UUIDs, matching headers, CPU/NUMA topology,
132 GiB data capacity and absence of loaded project modules. Source/evidence
checks establish directory presence and expected mounts, not complete content
verification. The retained legacy `.config`, `vmlinux` and `bzImage` hashes
matched; no unchanged legacy initrd claim is made.

Final host gates also passed: 64 vCPUs retain matching host CPU pins, seven
auxiliary threads use CPU 63, and two 12 GiB memory backends retain their NUMA
bindings. All 64 host frequency policies remain fixed at 2.0 GHz with the
`performance` governor and turbo disabled. Monitor and per-image snapshot lists
still contain only `legacy-kdclobber2-20261027`. This checks configured state;
it does not measure effective frequency or establish strict benchmark timing.
The new kernel's preemption mode is **`full (lazy)`**, unlike the legacy
voluntary mode, so old measurements do not describe an equivalent environment.

The original preboot probe falsely rejected an empty GRUB `next_entry=`.
Read-only inspection confirmed the empty value; the corrected probe passed
without changing GRUB state. Both concise check outcomes remain bound in the
platform receipt. Two final journal error entries were inspected transiently
and identified as empty `fd0` floppy-device read errors. Their text was not
archived; final checks found zero soft-lockup and critical-kernel matches.

Final housekeeping removed 15 upgrade-log files and three directories under
`/var/log/dist-upgrade` (3,339,208 bytes) without preserving their contents.
The two exact upgrader temporary directories were already absent after boot.
Downloaded APT cache decreased from 38,900,578 bytes to zero; general system
APT logs and journals were outside this selected cleanup. The temporary
`127.0.0.1:2223 → guest:1022` upgrade forward was removed, retaining ports
2222, 9090 and 9091. Seven intermediate 6.8 kernel packages and three unused
Python 3.12 libraries were removed after an exact simulation. The only boot
images are active 7.0 and legacy 6.1 recovery; the sole retained VM snapshot
still represents the legacy environment.

No new KD build, unit-test or benchmark pass is claimed. OS installation and a
successful kernel boot will not establish KD support. Linux `6.1.159` receives
no further adaptation; its retained inputs and results remain recovery and
historical evidence. Linux 7.0 adaptation needs its own API/ABI, admission,
lifetime, correctness and performance validation.
