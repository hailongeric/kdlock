# Disk headroom and scoped duplicate-log cleanup

Inspection and cleanup used source `9e5e4ef31f2dff05aa21c40cc2046246e68c7336`
on `codex/mmap-reached-jit`. No lock/JIT/source implementation changed. No kernel
build, installation, reboot or live workload ran. The normal guest stayed on
`7.0.0-38-kdlock1`, boot `4ff57d48-bc4c-43bd-9946-b16e0db3d4da`, with no KD
module or workload/build process observed. Master and unrelated work are unchanged.

## Completed cleanup

The user authorized previous-run logs/archive cleanup while preserving unique
records, current failure evidence, source, installed kernels and recovery disks.
Every selected file was regular, had one link, resolved to its exact inventoried
path, was unchanged during hashing, and had no open process reference. No broad
delete pattern was used. `cleanup-plan.json` and
`guest-duplicate-verification.json` give every removed and retained path/hash.

| Action | Selected allocation | Measured available-space increase |
| --- | ---: | ---: |
| Eight old host mirror archive duplicates; identical copies retained on 380G10 | 3,124,178,944 bytes | 3,124,166,656 bytes on Super-Server |
| Five November 3/4 guest launcher log duplicates; identical lifecycle logs retained in guest | 1,271,111,680 bytes | 1,271,103,488 bytes on build disk 2 |
| Host effect of those guest deletions | — | **0 bytes**; qcow2 allocation unchanged |

Initial host file-use inspection rejected an unsupported command separator;
the corrected invocation completed with no matching processes. The first host
unlink was denied by directory permissions and removed no archive. The same
eight-path action then used the tool approval mechanism for administrative
execution and completed. Both attempts and their exact scope remain recorded.
Two other host candidates were retained: one had no local alternate and the
other differed in size. Nothing was removed merely because it was old.

Host action manifest:
`/home/eric/vm/migration/duplicate-run-archive-cleanup-20261106-r2.jsonl`.
Guest action manifest:
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/log-duplicate-cleanup-20261106.jsonl`.
The current `e57ae29d` failure console/records and restore-investigation records
were outside the selected paths and retained. No snapshot/image, source tree,
Git/session history, module staging tree or unique record was deleted.

## Capacity and disk identity

Bytes below are sampled available space, not rounded advertised disk sizes.

| Filesystem | Available after cleanup |
| --- | ---: |
| Super-Server `/dev/nvme0n1p2`, holding all active qcow2 files | 7,247,515,648 |
| Guest `/dev/sda1`, root and `/boot` | 3,230,511,104 |
| Guest `/dev/sdb`, `/mnt/kdlock-builds` | 15,129,886,720 |
| Guest `/dev/sdc`, `/mnt/kdlock-builds2` | 7,785,558,016 |

The host has 57,247,592,448 physically free bytes after cleanup; exactly
50,000,076,800 bytes are reserved/unavailable to ordinary allocation. QEMU's
real/effective/saved/filesystem UID is 0, but that reserve is not counted as
normal build headroom and its setting was not changed. Source host 380G10 has
its own filesystem (about 113.4 GB available during inspection); it is not the
active VM host and its free space cannot be added to these figures.

| Active host image | Virtual bytes | File apparent bytes | Host allocated bytes |
| --- | ---: | ---: | ---: |
| `/home/eric/vm/qemu-disks/ubuntu22.04.img` | 109,735,575,552 | 534,681,157,632 | 321,947,844,608 |
| `/home/eric/vm/qemu-disks/sda.qcow2` | 141,733,920,768 | 160,010,272,768 | 158,281,793,536 |
| `/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2` | 180,388,626,432 | 175,854,256,128 | 175,858,724,864 |

These are live read-only metadata samples, not a consistent block-refcount
inventory. Each image is standalone in the backing-chain listing, with 64 KiB
clusters, 16-bit refcounts and internal snapshots. Snapshot-owned clusters and
sparse file extents prevent deriving reclaimable host bytes from apparent size
or guest `df`. Recorded attachment/mount settings do not enable discard
explicitly; no trim, compact, discard or reserve adjustment was attempted.
The measured zero host gain from guest unlinking confirms the immediate limit.

## Why snapshots and kernel rebuilding are different

`info snapshots` reports one complete checkpoint covering all three disks:
`kdlock-builddisk-clean-20261031`, with 25,250,880,753 bytes of saved VM state.
The four older tags (`legacy-kdclobber2-20261027`,
`linux70-kdlock1-clean-20261027`, `linux70-kdmm1-native-clean-20261027`,
`kdlock-roleswap-failure-20261029`) are partial/non-loadable with the current
three-disk set. Preserve their recovery dependencies; none was changed.
A complete restore would roll back the guest's code and later disk contents.
It does not deploy a new builtin function. A new full memory checkpoint of the
previous measured size alone exceeds current ordinary host headroom.

The comparison kernel retained Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1` through many provider/daemon/JIT
iterations. Those operations were not repeated full kernel builds. This change
is different: `kd_rwsem_provider_resume()` and its instruction continuation are
builtin in `provider.c`; a new module cannot apply `b1884ccb` to them. A kernel
relink is required. A full fresh output-tree copy is a workflow choice, not an
inherent requirement of this one C/assembly edit.

## Measured build footprint and next workflow

Current scope5 source occupies 1,824,202,752 allocated bytes; its build occupies
33,527,439,360 allocated bytes. Config SHA256 remains
`7dffb540209d34287f7ece75a6b3635b87dd751179fb7953f92aa2eff9b714aa`.
Current root link-related files total 4,382,278,191 logical / 4,345,204,736
allocated bytes. These are retained output sizes, **not measured peak additional
space**. Prior unstripped modules totaled 9,328,599,064 bytes; the staged module
package was about 0.7 GB. Link/BTF regeneration, module staging, initrd scratch,
old-generation retention and installed files need separate allowances.

Preserve scope5's MM/API/generated-text composition and kernel component
`1ab7124abb6140752c1f0bb6e862144d426a3875`, adding the narrow reviewed builtin
change. Do not regenerate unrelated kernel components from the entire newer
module checkout. Retain the selected configuration/toolchain, Native bodies,
original JIT and active capture. A new identity requires preparation/composition
receipts, matching source/build/KDIR and Native/KD schema-2 capture.

Three choices remain:

1. Preserve the complete current v3 generation in a verified archive, then amend
   its existing workspace and reuse cached objects at identical paths. The prior
   v2-to-v3 procedure demonstrates this approach, but it modifies the canonical
   workspace after preservation and needs a deliberate workflow decision. The
   older v2 archive cannot substitute for preserving v3. Its 7,492,842,002-byte
   compressed size is historical, not a measured v3 archive size.
2. Develop a private copy-up view of both source and build at their original
   absolute paths. This could reuse objects while preserving underlying trees,
   but candidate persistence/KDIR/identity and all write destinations remain
   unvalidated. It must not be introduced silently. Hardlinks cannot substitute:
   compiler writes could alter the original inode.
3. Create an ordinary independent source/output tree. This retains the old tree
   directly but needs approximately its full footprint plus transient reserve.

Fresh command records show 545 occurrences of the absolute source path in
`.provider.o.cmd`; the generated Makefile and final link records also bind
paths. Relocating a cache may change commands and trigger regeneration. Same
release/configuration does not by itself prove bounded reuse.

Keep existing gates: **50 GiB** before fresh preparation, **34 GiB** before its
build; or **16 GiB** for the established incremental workflow. Exact sources are
`/tmp/kdlock-mm-scope5-controller-20261103.py:191–196` (fresh) and
`/tmp/kdlock-mm-scope5-generated-text-amend-r2-20261103.py:284–294`
(incremental: `max(16 * GIB, 4 * largest_intermediate)`).
[Retained excerpts](../../raw/tests/headroom-cleanup-20261106/build-gate-source.txt)
bind those lines to full-file hashes. Both helpers check guest
`/mnt/kdlock-builds2` and require guest root free space greater than 2 GiB;
neither checks host capacity. The incremental helper repeats its guard before
source amendment and final linking (lines 311 and 342).
The gates use strict greater-than checks;
shortfalls here measure distance to the threshold, not sufficient final margin.
Disk 2 remains
**9,394,311,168 bytes short** of 16 GiB; disk 1 is **2,049,982,464 bytes short**.
Filesystems cannot be summed. Ordinary host capacity is also
**9,932,353,536 bytes below 16 GiB**. Applying that same conservative new-write
budget to the host is a planning allowance, not a claim that the old guest
controller checked host space. A complete current-generation archive needs its
own capacity; the physical additional allocation and build peak remain unknown.
Prior install planning additionally required
3,389,168,238 root bytes and 2.5 GiB initrd scratch; root is below that historical
install allowance. These conservative gates are not exact measured peaks and
were not reduced to fit the present filesystem.

The expected build commands, after identity/space/preparation are satisfied,
are `make -C <source> O=<build> ARCH=x86 CC=x86_64-linux-gnu-gcc
KERNELRELEASE=<selected-release> -j32 W=1 kernel/locking/kd_mmap/provider.o`,
then `bzImage modules` with the same options. Stage modules separately using
`INSTALL_MOD_PATH` and `INSTALL_MOD_STRIP=1`; place initrd temporary files on the
build filesystem. Preserve old installed files and normal recovery until a new
matching identity is captured. No command in this paragraph was run here.

The narrowest established option
for review is to preserve and verify current v3, retain its installed files and
recovery identity, then incrementally rebuild the provider object and dependent
kernel links using the same paths/configuration. That avoids a mandatory full
output clone but deliberately changes the preserved working tree; it is not an
approved in-place update of immutable inputs. The private copy-up alternative
would preserve them in place but requires its own implementation and validation.
Neither starts below the existing reserve. The original mmap failure's cause
also remains unproved; passing the restore fixture is not live MM validation.

## Additional candidates not removed

The exact tree
`/mnt/kdlock-builds2/kdscope5-generated-text-modules-stage-20261103/lib/modules/7.0.0-38-kdscope5/kernel`
has 6,901 regular files, no shared inode links, and 688,386,048 allocated bytes.
Every file hash matches its installed alternate under
`/usr/lib/modules/7.0.0-38-kdscope5/kernel`; the path/hash manifest digest is
`51d5c50be108e2518011548b9feae41946e3427a6b220231f2e2747cf613b593`.
It is a referenced installation artifact outside the log/archive cleanup scope,
so it remains intact. Even removing it would not meet the incremental reserve,
and host reclamation would remain unproved.

On 380G10 only, `/tmp/kdlock-mm-scope5-v3-elf-20261103/vmlinux` occupies
511,832,064 allocated bytes and can be reconstructed byte-for-byte from its
verified retained gzip. It is still referenced by the failure report, was not
removed, and deleting it would free zero bytes on Super-Server or the guest.
Current/recovery disks, snapshots, historical source/build trees and unique
archives remain preserved. No sufficient minimal cleanup plan for the next
kernel build is established by the inspected scope.

`summary.json` separates the measured changes and remaining deficits.
`retained-files.json` indexes the compact inspection/action receipts under
`../../raw/tests/headroom-cleanup-20261106/`. The eight host retained copies and
five guest retained lifecycle logs remain at the exact paths in those receipts.
