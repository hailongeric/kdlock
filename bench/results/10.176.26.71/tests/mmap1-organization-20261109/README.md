# Mmap1 documentation organization and recoverable cleanup

The mmap1 implementation and evidence were already committed on
`codex/release-unit-boundaries`: discovery fix `d421e7d5`, normal-run evidence
`53889930`, and static munmap review `32bda7fa`. No duplicate code change,
merge, push, source redesign, test or workload rerun was made.

Documentation commit `c315d688` updates `docs/JIT_EXECUTION.md`,
`docs/ROADMAP.md`, `docs/design/reached_path_execution.md`,
`docs/design/compiled_mm_continuations.md` and the VM result index. It preserves
strict any-unlock emission and historical failed/stopped attempts. Mmap retained
returns were restored in one stable instrumented eight-process point; quiet
performance remains unaccepted. Munmap still completes through native handback,
and its exact taken exit remains dynamically unidentified.

## Exact completed cleanup

Twelve source-host roots, comprising 202 regular files, were removed only after
every file matched an independent retained copy and a fresh full-host activity
check found no active user. All components and nested mounts were checked;
the targets contained no symlinks or hardlinked files. Removal used enumerated
file unlinks and empty-directory removal, without wildcard deletion or recursive
source/worktree removal.

| Exact source-host target | Content bytes | Purpose |
| --- | ---: | --- |
| `/tmp/kdlock-normal-d421-collected` | 448,180,028 | Redundant collected archive/index/transfer receipts |
| `/tmp/kdlock-munmap-g7-static-53889930` | 30,860,670 | Redundant extracted image/log copies and static-analysis intermediates |
| `/tmp/kdlock-normal-d421-run-gvfl_nb8` | 1,406,313 | Redundant launcher and host/identity captures |
| `/tmp/kdlock-normal-d421e7d5da83-v1-once` | 221,034 | Redundant outer-controller outputs and frozen helper copies |
| `/tmp/kdlock-normal-d421-focused-manifest.json` | 68,735 | Copied focused-test source manifest |
| `/tmp/kdlock-normal-d421-prepare.py` | 59,878 | Retained normal preparation helper copy |
| `/tmp/kdlock-normal-d421-run.py` | 16,447 | Retained normal campaign helper copy |
| `/tmp/kdlock-normal-d421-collect.py` | 12,499 | Completed read-only evidence collector copy |
| `/tmp/kdlock-normal-d421-once.py` | 9,730 | Completed outer controller copy |
| `/tmp/kdlock-normal-d421-boot.py` | 6,486 | Retained boot/recovery helper copy |
| `/tmp/kdlock-discovery-batching-final-d350b172` | 888 | Copied passing focused-test output |
| `/tmp/kdlock-normal-d421-focused-result.json` | 589 | Copied passing focused-test receipt |

Four exact archive leaves from the current and previous VM preparations were
also removed. Both parent source/build/output trees remain. Immediately before
unlink, all four files again matched their retained source-host bytes and
original stat identities, had one link, and had no active user or symlink/mount
component. The guest was idle on its verified normal kernel. Only these four
guest leaf unlinks were performed:

| Exact guest target | Content bytes |
| --- | ---: |
| `/mnt/kdlock-builds2/kdlock-batch-checks-y6sf31br/inputs.tar` | 12,953,600 |
| `/mnt/kdlock-builds2/kdlock-batch-checks-y6sf31br/checks.tar.gz` | 44,742,043 |
| `/mnt/kdlock-builds2/kdlock-batch-checks-u1dw9xwz/inputs.tar` | 12,943,360 |
| `/mnt/kdlock-builds2/kdlock-batch-checks-u1dw9xwz/checks.tar.gz` | 44,655,772 |

The original VM/source-host evidence trees were not deleted. No provider/device
query, module load/unload, workload, tracing, targeted capture or reboot was
performed during this task. No permission denial occurred.

## Space accounting

| Device | Logical content removed | Allocated target blocks released | Immediate available-space increase |
| --- | ---: | ---: | ---: |
| Source host, filesystem containing `/tmp` and the repository | 480,843,297 | 481,570,816 | 481,546,240 |
| Guest `/mnt/kdlock-builds2` | 115,294,775 | 115,302,400 | 115,302,400 |

These are separate device counters, not a combined disk-space claim. The
source-host cleanup baseline was 92,530,454,528 available bytes; immediately
after its unlink operation it was 93,012,000,768. Its final available-space
snapshot is taken **after all recovery retention and commits**, and retained
at the raw receipt path `final-space.json` below. The final user report gives
that value and net change from the baseline. Net device space can also reflect
other filesystem activity and the retained receipts/Git objects; it differs
from the allocated blocks released by the exact targets.

Guest available space increased from 11,319,418,880 to 11,434,721,280 bytes.
The guest archive recovery names are hardlinks to existing independent
source-host copies: they preserve the bytes outside the guest without allocating
another archive payload on the source host. The older historical evidence
aliases below also receive no space-recovery credit. No trash/quarantine move
was used to claim free space.

## Retention and restoration

[recovery-map.csv](recovery-map.csv) enumerates all **206 removed files** with
their exact original/retained paths, SHA-256, size, mode, UID/GID and mtime.
[local-inventory.json](local-inventory.json) includes original root metadata,
directories, resolved paths, mounts, purpose and preserved candidates.
[guest-recovery.json](guest-recovery.json) records the four guest mappings.
Restoration is an ordinary copy from the retained path back to its listed
original path, recreating only the listed directories and restoring recorded
mode/ownership/time. Verify SHA-256 before reusing any restored file. Guest
copies use the existing `eric@10.176.26.71 -> vm_ssh.sh` route; restoration is
not needed for normal work and no restoration was executed.

The current canonical evidence remains at:

```text
/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/mmap1-normal-d421e7d5-v1/
```

The archive, complete static source/image/log copies, copied original control
receipts and tracked result records remain intact. The historical `/tmp`
locations embedded in old receipts are restored through the recovery map;
those original receipts were not rewritten.

Cleanup inventory, reviewed scripts, command receipts, per-file removal log,
the guest recovery archives and final space snapshot remain at:

```text
/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/mmap1-organization-20261109/
```

Six immediately preceding mmap1 roots totaling 1,148,922,378 content bytes
remain preserved; [prior-preserve-inventory.json](prior-preserve-inventory.json)
records exact paths and sizes. Their required historical archives were hash
verified and given durable raw aliases without removing the original paths;
see [previous-evidence-retention.json](previous-evidence-retention.json).
The failed collection's zero-byte partial archive and failed receipt also remain.

Eight other local roots remain protected: parsed finalization/controller JSON,
initial-state/helper files, both boot receipts, the earlier failed discovery
check, and the batch preparation source snapshot. In particular, the parsed
finalization JSON differs byte-for-byte from the canonical guest receipt; it
was refused as a duplicate. All source worktrees, source snapshots, documents,
needed results, reusable provider/daemon builds, pinned dependencies, workload
inputs, matching kernel ELF/source/baselines and recovery material remain.
No irreversible deletion candidate is currently proposed or awaiting approval.

## Verification and final state

Whitespace and new documentation links were checked; independent review found
no evidence overclaim. Static comparison confirms the existing strict release
contract is unchanged. Every removed file's content and recovery copy were
rehashed; host/guest path, mount, link and active-user checks passed immediately
before removal. The sandbox's two-process view was explicitly insufficient;
the actual source-host inspection saw 634 processes with no unreadable gaps
or active target references. No test suite or live validation campaign ran.

The guest remains `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`e36f9aec-0ae6-46a5-ac96-c8de74bf7b62`, with no project modules/tasks.
The mmap1 branch remains separate from `master`; unrelated master changes are
untouched. [summary.json](summary.json), [local-cleanup-result.json](local-cleanup-result.json)
and [guest-cleanup-result.json](guest-cleanup-result.json) retain the exact
checks, actions, accounting and final workload state.
