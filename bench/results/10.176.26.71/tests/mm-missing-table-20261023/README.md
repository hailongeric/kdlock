> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Missing-leaf-table anonymous removal

Completed on **6.1.159-kdmm14**: the final run passed **42 serial cases, two basic
tests and 956 negative receipt controls**. All three feasible missing-table
layouts matched the native body. **11 removals executed on different tasks with
no leaf table or private-page ownership**. Three controlled table appearances
each completed one further remote removal through the existing empty, zero or
private path. Recovery is restored and test modules are unloaded.

Kernel/module implementation: `6948999d83e1f91d9afaf44b5baa9a4a8fe008e9`.
Probe accounting correction: `450cb15bb1db725f0e260e521c45b1874093c268`.
This required implementation, not validation alone. The
[kdmm13 baseline](../mm-absent-target-20261023/README.md) remains separate;
its completed campaign was not repeated.

## Mechanism and feasible geometry

A PTE is a leaf page-table entry. `pte_none()` in an existing table differs from
`pmd_none()`, which means the entire 2-MiB leaf-table interval is missing. The new
path requires valid upper directories, including the PUD (page-upper-directory)
entry pointing to the PMD (page-middle-directory) table. It refuses missing
higher levels, huge/device mappings, bad entries and special non-present states.
The actual five-level x86-64 boot reports 4-KiB pages, 2-MiB PMD intervals,
1-GiB PUD intervals and a 256-TiB top-level interval.

The range remains one page within exactly three anonymous pages, with both
retaining neighbors and all three slots inside the same PMD. A missing leaf
therefore permits only untouched survivors: any private or shared-zero survivor
would create that very table. Prefix, interior and suffix **UU** are all feasible;
R/Z survivors while that table remains missing are impossible in this geometry.
An independent anchor read in the adjacent PMD constructs the upper levels
without allocating the target table. Read-only walks prove the state and parent
physical identity; neither inference from zero contents nor an enlarged VMA is used.

The caller retains existing preparation of VMA (virtual memory area), mapping
index and reverse-map resources. A reverse map connects private pages to VMAs;
absent metadata consumes no prepared link. Under actual mmap writer ownership
and the native PMD installation lock, the combiner records the missing-table
state separately from owned pages. The real native split/detach/unmap body
changes VMA boundaries and accounting. Native zap skips the missing leaf, and
the retained-neighbor bounds prevent table freeing. No PTE pointer, allocation,
data-page release or general table-destruction path is added. Completion checks
the unchanged parent identity, missing entry, table bytes and zero holds.
Ownership, waiter handback/ACK (acknowledgement), sticky fallback and retirement
are unchanged. Errors after splitting return directly without destructive replay.
The [maintained execution flow](../../../../../kernel_integration/mmap_lock/UNMAP.md#missing-leaf-tables-with-existing-upper-levels)
describes the shared constraints.

## Results and execution evidence

| Group | Result |
| --- | --- |
| 6 missing-table layout cases | Native/KD prefix, interior and suffix; 6 remote missing-table removals |
| 6 controlled appearance cases | Native/KD empty, zero and private target after table installation; 3 unchanged missing-table plus 3 changed-target remote removals |
| 2 local-fault cases | Native/KD comparison; 2 remote missing-table removals, then one local blocked survivor fault creates a table |
| 4 split-error cases | Both interior split points; two remote `ENOMEM` returns match native harmless splits without removal or replay |
| 2 controls | Missing PUD handback/ACK and sticky continuation; queued cancellation preserves its mapping |
| 18 kdmm13 coverage cases | Nine reversed ZR/UR/UZ pairs at all three positions, native/KD; 18 remote empty-leaf removals using the unchanged kdmm13 client |
| 4 preservation smokes | Zero target with UU survivors, resident partial removal, empty target with RR survivors, and busy-survivor refusal/ACK |

R is ordinary private resident, Z verified shared zero and U untouched; survivor
letters are ordered by address excluding the target. The nine coverage gaps are
closed on kdmm14, not retroactively added to kdmm13's results. In total the final
run records **16 native success comparisons and two native error comparisons**,
38 remote successful removals across all paths, two matched pre-effect ACKs,
one cancellation, 300 cleanup calls and 133 isolated writes. Native controls use
the ordinary body on the same KD backend, not a separate Native-off boot.

For `missing-target-prefix-uu`, mm `ff1100010bc9ab80`, request 2, origin **2447**
and executor **2446** bind the actual body to queue completion. Its receipt reports
parent table PFN (physical page number) `0x346a54`, `pmd_none=1`,
`held=0 released=0 target_owned=0`. Independent before/after walks show no leaf
table, the same parent, and unchanged **81,920** page-table bytes. Removed access
faults; after explicit survivor reads/writes, complete local cleanup observes
missing upper entries. Local heads and fallback are excluded from remote counts.

Controlled appearance runs use an existing local reader after three requests
publish, with two reader shares still held and new-reader admission closed.
Modes empty/zero/private create leaf PFNs `0x353d4d`, `0x34fd9b`, `0x34e83a`;
the corresponding bodies execute as origins/executors **2485/2484**,
**2493/2492**, **2501/2500**. The private target is exactly PFN `0x3518f3` with
one hold/release; the zero target acquires none. These are deterministic
pre-execution changes, not uncontrolled fault-race coverage.

Checks include exact VMA layout/offsets/flags, mapped-page and private-residency
accounting, absent metadata, reference/resource lifetimes, survivor state before
access, subsequent zero reads and isolated writes, independent zero mapping,
table identity and cleanup. Readers remain concurrent/local. Missing targets have
no positive TLB (cached translation) entry to warm; removed-address faults prove
VMA removal. Zero/private smokes retain positive-target invalidation coverage.

## Failed attempt, builds and storage

`focused-1` passed its first native case, then the delegated prefix probe failed
its final cleanup-counter assertion. The last independent anchor lies outside
the KD-enabled interval: all 12 cleanup calls succeed, but only 11 enter KD
counters. The correction checks both exact totals and adds a negative routing
control. Admission and kernel behavior did not change. The failed inputs/logs
and its two diagnostic remote bodies are retained and **excluded** from accepted
counts. `focused-2` uses a new frozen probe revision on the same candidate boot.

One incremental kernel build and one test-module build were needed. The build
reused the captured lower tree, compiled dependency-selected targets, and retained
73 runtime modules; its log reports 3,155 compilation actions. Four unchanged
clients were reused. After the probe correction only its userspace executable
was recompiled; no second kernel/module build or candidate reboot occurred.
The two basic C tests passed once; expected negative-fixture diagnostics are
retained in `build-1/basic.log`.

Storage cleanup removed **only** the separately approved guest
`/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux/vmlinux.o`
after checking idle state, no open references and its host recovery copy.
SHA-256: `c8e1463428faa0ff458953ff96c301871e8e57d4643389bcb78919c3f64bfd53`.
It reclaimed **863,367,168 bytes**, taking free space from 27,754,496 to
891,121,664 bytes against the measured **260,000,000-byte** cycle budget.
The prior two approved deletions were not repeated. Build/link/package scratch
used RAM and the approved boot cleared it. No other permanent file, snapshot,
disk, source, recovery artifact or historical evidence was deleted.

## Reproduction and retained evidence

On source host `380G10`, after confirming this same VM is idle and current
capacity is sufficient, reuse the installed candidate and frozen probes:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-missing-table-20261023/workflow.py kd --attempt 3
python3 bench/results/10.176.26.71/tests/mm-missing-table-20261023/workflow.py recovery --attempt 3
```

For an already verified kdmm14 boot, `run --attempt 3` avoids another boot.
Use a new attempt number; never interrupt an active run. The
[probe guide](../../../../../tests/kernel/mmap_lock/missing_table/README.md)
gives direct commands and modes. Completed sequence: `prepare/build/kd` attempt 1,
`probe/run` attempt 2, one `collect` attempt 1, then `recovery` attempt 1.
Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-missing-table-20261023`.
Source-host raw root: `bench/results/10.176.26.71/raw/tests/mm-missing-table-20261023/`.

| Identity/artifact | Value |
| --- | --- |
| Candidate Build ID | `feb90ddfacd73a49317e01d8d137e0ffd998dfff` |
| Candidate manifest SHA-256 | `df0fa39efe8bafdd3d4e2b08e6e69789d49e2ccc04e9ce7a355f8f5899c06239` |
| Candidate boot | `a2d6ad52-d5c3-4d76-a96f-d985aa6d1aac` |
| Corrected client SHA-256 | `0f73b63cb14958612a4b3c9b27bff7d08fd812478548257cf94d758573966742` |
| `run-2/result.json` SHA-256 | `48f9957191d5096721e3b734369314c928ec7ece27c21e13271d6080d7faa537` |
| `collect-1/essential.tar.gz` | 595,718 bytes; SHA-256 `70ca5047ed8847e880a2787b9f70d40c5d58f3344a7d9e9f5289f9e0861d0b60` |
| Recovery boot | `8a60bc00-ae86-4922-9f10-c28a407792ee` |

One offline pass verified all 42 client/log pairs and eight corrected input hashes;
[evidence-check.json](evidence-check.json) keeps new work, preservation and failed
evidence distinct. The single archive retains both focused attempts and probe
revisions. Recovery/final-health receipts are separate small files, not another
archive. The hash-verified removed intermediate remains at the raw root's
`cleanup/recoverable/vmlinux.o` for recovery.

Recovery is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`; 5,686 recovery module files and the
exact 73 loaded runtime modules were preserved. No test modules or workers remain,
and the one-shot boot selection is empty. The first final-health observation
incorrectly required the `next_entry` key to disappear; GRUB keeps it with an
empty value. `final-health-2.json` verifies no selected entry without changing it;
both observations are retained. Recovery logged six `fd0` read-error lines and
no kernel-fault matches; the raw transition retains them. Final free root space
is **664,825,856 bytes (634.03 MiB)** with 10,188,814 free inodes. Check the actual
needs of any future cycle; no additional cleanup is authorized by this record.

## Remaining scope and next step

Cross-PMD layouts, missing higher levels, special non-present entries, huge pages,
complex ancestry and general delegated table destruction remain refused. Forced
VMA replacement, table disappearance after publication, uncontrolled fault/
reclaim/pinning races, pressure, non-root memory cgroups, post-admission cancellation
and boundary-load behavior remain untested. Advice, first-write fault and whole-VMA
campaigns were not repeated; their production paths were unchanged. No skipped
case is counted as a pass, and this is not general mmap support or a performance
claim.

The new missing-table fixtures start with absent reverse-map metadata. A simple
inherited chain with a missing leaf table was not separately exercised. The PUD
refusal is live; other higher-level/huge/special-state guards were inspected, not
forced through new injection fixtures.

The next useful small candidate is a three-page VMA crossing one PMD boundary,
starting with an edge target whose missing table is distinct from a populated
survivor's table. It needs an explicit per-table retention proof and split-geometry
checks before changing the current guard. Larger mappings, general teardown,
performance/p95, the seven mutex regressions and nano reruns remain deferred.
