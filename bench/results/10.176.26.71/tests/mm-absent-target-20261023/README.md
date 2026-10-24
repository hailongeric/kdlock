> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Absent-target removal with retained page tables

Passed on `6.1.159-kdmm13`: **51 serial cases, two basic tests and 966 negative
receipt controls**. Eighteen representative layouts matched native behavior.
**38 absent-target removals executed on different tasks**, including 20 with no
private-page holds. Controlled absent-to-zero/private transitions each added one
remote removal through the existing corresponding path. Recovery is restored,
test modules unloaded, and no build or live case failed. Expected injected errors
and refusals are preserved as passing correctness controls, not removals.

Implementation and frozen inputs: `453d7d0bd6f2289e54800641989bc26c1d348a34`.
The [kdmm12 baseline](../mm-zero-only-20261023/README.md) remains separate evidence;
its full campaign was not repeated. This required one kernel-source change,
not validation alone.

## Mechanism and scope

An absent target is an address **inside** a three-page anonymous VMA (virtual
memory area) with `pte_none()` in an **existing** leaf page table. It is neither
an address outside a VMA nor a swap, migration or other special non-present
entry. One page may be removed at prefix, interior or suffix. Every page-table
level must exist, and the existing same-PMD neighboring VMAs must retain the
table. A PMD describes the 2-MiB interval containing these entries. The old
untouched path instead requires absent top-level page-directory entries (PGDs).

The previous eligibility walk accepted empty survivors but refused an empty
target. The new path distinguishes admission from physical-page ownership,
records an absent-target outcome, and runs the real native split/detach/unmap
body even when no physical page needs clearing. It allocates no table and does
not add general table destruction. Caller-prepared VMA/index/reverse-map reserves
are unchanged. A reverse map connects private pages to VMAs; consistently absent
metadata consumes no prepared link. Shared zero pages never enter ordinary
ownership/release handling. Current VMA, table and entry states are revalidated
under mmap writer ownership and the PTE lock. Unsupported states hand back
before effects; after splitting begins, errors return without local replay.

The new table-query ioctl records leaf versus missing-upper state and the exact
table PFN (physical page number) without touching data. A separate neighbor read
establishes the table for UUU; no target/survivor is populated to evade admission.
Existing ioctl layouts, owner/ACK routing, cancellation and sticky fallback remain
unchanged. Readers stay concurrent and local. See the
[execution flow](../../../../../kernel_integration/mmap_lock/UNMAP.md#absent-targets-with-retained-leaf-tables).

## Validation and actual execution

R denotes private resident, Z verified shared zero, U empty leaf. Survivor letters
are ordered by address excluding the U target.

| Cases | Coverage and result |
| --- | --- |
| 36 matrix cases | Native/KD pairs for RR, RZ, RU, ZZ, ZU, UU at each of prefix/interior/suffix; 36 remote absent removals |
| 4 transition cases | Native/KD U-to-Z and U-to-private; 2 additional unchanged absent removals, 1 changed-zero and 1 changed-private remote removal |
| 4 split-error cases | Both interior post-split points, native/KD; matched `ENOMEM`, harmless layouts, no destructive replay |
| 2 refusal cases | Busy final survivor releases the earlier hold; missing table owns no page; both match exact handback/ACK and sticky continuation |
| 1 cancellation | Queued fatal cancellation retains the victim mapping and retires prepared resources |
| 4 preservation smokes | Zero target with R/Z and U/U survivors; resident target with Z/Z and R/R survivors; 4 remote zero and 4 remote private removals |

The matrix is representative: reversed mixed pairs ZR, UR, UZ (nine cases) were
not rerun. Survivor classification is unchanged, previous zero-target matrices
cover both orders, and RR checks private holds on both sides. This is not a new
27-layout validation claim. There are **20 native success comparisons** including
both transitions, plus **two native error comparisons**. Native uses the ordinary
body on the same KD backend, not a separate Native-off boot.

Example `target-prefix-uu`: mm `ff11000348a5ecc0`, request 2, origin **1901**,
executor **1899**, table PFN `0x34b758`. The actual body receipt records all three
slots empty, `held=0 released=0`, `target_owned=0`, absent target PTE and retained
table; matching queue completion and post-body VMA absence prove real removal.
`target-middle-rr` separately records two exact private-survivor holds/releases.

For U-to-Z, actor **2036** records pending=3/readers=2/admission=-1 and the same
table PFN `0x34782f` before/after a native read fault, with no page reference or
reverse-map metadata. Origin **2032**, executor **2031**, then removes the verified
zero target. For U-to-private, actor **2045** creates private PFN `0x35bbdc` and
simple metadata while retaining table `0x355b25`; origin **2041**, executor **2040**,
removes that exact page with one hold/release. These controlled changes precede
execution; they do not establish uncontrolled concurrent-fault race coverage.

Pre-access checks distinguish U/Z/R and verify VMA bounds, offsets, flags, mapped
page counts, exact table identity/bytes, reverse-map lifetimes, private references
and per-VMA RSS (resident set size)/anonymous bytes. U/Z contributes no private
RSS. Removed addresses fault instead of allocating a new anonymous page. Resident
survivor contents remain intact. One recorded competing local read fault waits at
writer admission; other U slots stay empty until explicit access. Later zero reads
and isolated private writes preserve other survivors and an independent zero
mapping. An empty target has no positive TLB (cached translation) entry to warm;
its fault proves mapping removal. The zero/private smokes retain positive-target
invalidation checks. The 47 absent-family cases completed 135 isolated writes,
282 cleanup calls and 906 negative controls; all 51 cases total 150 writes,
318 cleanup calls and 966 controls. Local heads/fallback never count as remote.

## Reproduction and essential evidence

On source host `380G10`, with this VM idle and capacity checked, reuse the installed
candidate and frozen probes. Attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-absent-target-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-absent-target-20261023/workflow.py recovery --attempt 2
```

This run used `prepare`, `build`, `kd`, one `collect`, then `recovery`, attempt 1.
Never reboot an undrained run. The [probe guide](../../../../../tests/kernel/mmap_lock/absent_target/README.md)
gives modes and the direct command for an already verified candidate boot.
Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-absent-target-20261023`,
run `focused-1`. Essential source-host evidence is under
`bench/results/10.176.26.71/raw/tests/mm-absent-target-20261023/`.

| Identity/artifact | Value |
| --- | --- |
| Candidate Build ID | `c895abcc96ad5451f13c9c88049c13cb92386dfc` |
| Candidate manifest SHA-256 | `61746d7451386a8d8a84319d67e10f4f80fd6ddfa26c09b8a269e8d427d5a680` |
| Candidate boot | `e7cf2396-af72-4828-892e-bc9da892cf9e` |
| New client SHA-256 | `e4c2dcf1ce62c8dc820652fd411a4d472cd9b641a68dc6687ab073f78544620e` |
| Focused result SHA-256 | `d9721abd72e570f1464f8073988ad6da379bed79832297e0c9c7cc120ad4211c` |
| `collect-1/essential.tar.gz` | 560,803 bytes; SHA-256 `4a88bc3e219a8801bc5ecaa555d665d2c311b8078299dfb8cc6a19928ff7d84b` |
| Recovery boot | `1d971ef7-fd60-47b0-98a2-75970e5c582f` |

One offline pass verified all 51 client/log pairs. `evidence-check.json` retains
selected receipts; `recovery-1/result.json` and `final-health.json` retain final
restoration. No old archive was copied or rescanned.

## Storage, recovery and remaining limits

Only the two approved inactive `.tmp_vmlinux.kallsyms1/2` files under
`/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux/` were
deleted, after hash-verified recoverable copies were saved under the source-host
raw directory's `cleanup/recoverable/`. This reclaimed 188,010,496 bytes.
`cleanup/result.json` records exact paths and capacity; no other historical files,
snapshots, disks, VM placement or recovery configuration were changed.

The RAM overlay reused the retained build tree. A distinct release required
3,155 compilation steps and 73 runtime modules. One captured kernel source,
one client and one test module changed; four clients were reused. Build/install
persistent growth was 221,216,768 bytes; subsequent boot/test/health growth was
12,529,664 bytes. New volatile build intermediates expired at the approved boot.
Three objtool warnings also appear in kdmm12; installation additionally logged
a locale fallback warning. Neither caused a failed command.

Recovery is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with all 73 expected runtime modules,
5,686 recovery module files preserved, no test modules/new faults, cleared
one-shot entry, idle VM and empty temporary RAM. Root and `/boot` share only
**27,774,976 bytes (26.49 MiB) free**. Another build lacks headroom; no further
deletion is authorized by this result. Existing-image reruns still need a fresh
capacity check against their actual boot/log needs.

Absent upper tables on this opt-in, special non-present entries, larger ranges,
complex ancestry and general table destruction remain refused. The nine reversed
mixed absent layouts, inherited-but-empty metadata with absent targets, forced
VMA replacement, special-entry injection, uncontrolled fault/reclaim/pinning races,
pressure, non-root memory cgroups and post-admission cancellation were not tested.
Advice, first-write and whole-unmap campaigns were not repeated because their
production paths were unchanged. Performance/p95, seven mutex regressions and
nano reruns remain deferred.

The next small useful extension is an empty target whose leaf table is missing
but upper levels already exist, still within the three-page scope. It needs a
separate validated no-table state and proof that native traversal neither
allocates nor frees tables; it must not allocate a table merely to pass admission.
The current missing-table case retains safe handback until that proof exists.
