# Approved duplicate guest archive cleanup, October 25

The user approved permanent deletion of exactly three guest archives at
**19:31 (Asia/Shanghai)**. All three were removed at **19:43:34**, after fresh
identity, hash, dependency and reference checks. Parent directories and
source-host restoration copies remain intact. No other cleanup, secure wipe,
TRIM, snapshot purge, disk resizing, boot or benchmark restart was performed.

| Deleted guest regular file | Recorded allocation | Retained source-host copy |
|---|---:|---|
| `/mnt/kdlock-builds/evidence/archives/mutex-kdonly-20261017T140354Z.tar.gz` | 684,572,672 bytes | [Archive](../../raw/bench/mutex-kdonly-20261017T140354Z/mutex-kdonly-20261017T140354Z.tar.gz) |
| `/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022-archives-1/metadata.tar.gz` | 248,127,488 bytes | [Archive](../../raw/tests/mm-unmap-body-20261022/seal-1/guest-archives-1/metadata.tar.gz) |
| `/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022-archives-1/metadata.tar.gz` | 304,594,944 bytes | [Archive](../../raw/tests/mm-populated-unmap-20261022/seal-1/guest-archives-1/metadata.tar.gz) |

The [exact plan](../../raw/tests/approved-archive-cleanup-20261025/plan.json)
retains absolute guest/backup paths, full SHA-256 values, apparent sizes,
allocations and expected device/inode identities: `2064/2017005`,
`2049/111490` and `2049/116269`, respectively. Each guest path resolved exactly,
was a regular single-link file and matched its expected bytes and hash.
The source-host copies were freshly hashed before deletion, held open and
unchanged during the operation, and hashed again afterward.

The 604-process guest scan found no conflicting benchmark, build, scanner or
module operation, no external open/mapped reference, and no access error.
Reference and identity checks were repeated immediately before each unlink.
The operation opened parent directories without following symlinks, retained
verified file descriptors and unlinked only the three exact basenames through
their checked parent descriptors. Current protected dependency roots were
excluded; all 13 build-3 source/binary bindings matched before and after.
The [execution record](../../raw/tests/approved-archive-cleanup-20261025/execution.json)
binds the exact [operation source](../../raw/tests/approved-archive-cleanup-20261025/guest-unlink.py);
the [incremental journal](../../raw/tests/approved-archive-cleanup-20261025/unlink-journal.jsonl)
records each successful unlink and confirmed completion.

## Measured filesystem change

| Guest filesystem | Available bytes before | Available bytes after | Increase | Free inodes before → after |
|---|---:|---:|---:|---:|
| Root | 3,620,941,824 | 4,173,664,256 | 552,722,432 | 10,392,699 → 10,392,701 |
| `/mnt/kdlock-builds` | 10,031,104 | 694,603,776 | 684,572,672 | 1,499,205 → 1,499,206 |
| `/dev/shm` | 5,740,777,472 | 5,740,777,472 | 0 | 2,976,510 → 2,976,510 |

Total removed allocation was **1,237,295,104 bytes**, matching the immediate
guest free-space increase. The [summary](../../raw/tests/approved-archive-cleanup-20261025/summary.json)
also records `f_bfree` separately from available space. The data disk's reserved
blocks are not included in the available-space budget. An earlier unrelated
root-space/inode increase was already visible before this operation and is not
counted as cleanup savings. No host qcow2 shrink is claimed or measured.

## Preserved state and scope

At **19:45:22 (Asia/Shanghai)**, the [post-cleanup check](../../raw/tests/approved-archive-cleanup-20261025/guest-after.json)
confirmed exact absence of the three files and presence of their parent
directories. Recovery remains `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, with the exact 73 modules, taint **12288**,
the recovery default, empty `next_entry`, no kernel fault matches and no residual
cleanup/build/workload process. Recovery boot/configuration and loaded-module
hashes, all four installed candidate boot files and 73 candidate modules,
recovery/candidate source/build identities and BTF, 13 prepared bindings,
22 runner bindings and three original qualification-environment receipts passed.
`/mnt/kdlock-builds/linux-6.1.159-kdclobber2` remains the recovery source target.

All three [retained backup hashes](../../raw/tests/approved-archive-cleanup-20261025/backup-after.json)
still match. The 14 raw files from the [failed benchmark admission](../../bench/mmap-kdmm31-paired-20261025/README.md)
also match their sealed manifest. This cleanup adds no correctness or
performance result: the campaign remains stopped at **0 boots, 0 payload
checks, 1 capture and 24 unrun measured sessions**. Qualified current timing
remains zero. No additional capture or quiet retry followed.

The [raw manifest](../../raw/tests/approved-archive-cleanup-20261025/manifest.json)
binds the plan, backup checks, guest preflight/activity/post-checks, exact
operation, journal and summary. The unrelated empty
`tests/vm-disk-cleanup-20261022/README.md` was preserved byte-for-byte and excluded
from the commit. This exact deletion approval covers no additional archive,
replay directory or snapshot.
