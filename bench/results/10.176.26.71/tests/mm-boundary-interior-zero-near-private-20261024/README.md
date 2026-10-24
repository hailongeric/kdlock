> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm29: shared-zero interior removal beside a private survivor

**Complete:** all 48 serial cases, two basic tests and 1,057 negative receipt
controls passed. The new path completed 12 different-task zero-target removals;
queued empty-to-zero changes added two more. Recovery is restored and modules
unloaded. The completed kdmm28 campaign was not repeated.

## Mechanism and scope

Remove one shared-zero middle page from a three-page anonymous VMA (virtual
memory area) crossing a 2-MiB boundary. The near survivor shares the target's
table and is an eligible private resident page. Far survivors remain private
resident, shared zero or untouched. Both outer-neighbor guards and the native
two-split floor=`start`, ceiling=`end` retention proof are unchanged. A populated
survivor alone cannot authorize retaining a table.

The prior near-slot refusal was an implementation restriction. Commit `cb9ae8f`
allows the already verified shared-zero target class to use kdmm28's private
survivor classifier. The current mmap writer and PTE (page-table entry) lock
establish page/table identity. Writable, exclusive, ordinary anonymous base
pages receive exact temporary references and nonblocking locks; compound,
shared/COW, pinned-indicator, swap-cache, poisoned, reserved and busy pages refuse.
Caller-prepared split descriptors, mapping-index reserves and reverse-map links
(page-to-mapping metadata) are reused and revalidated, with no new combiner allocation.

Native zap clears the shared-zero PTE and completes TLB (translation lookaside
buffer) invalidation. It does not own, modify, reverse-map-release, uncharge or
free the shared zero page. Private survivor holds persist through both splits
and native teardown, then retire exactly. Their identity/permission comparisons
ignore only hardware accessed/dirty bits. Later refusal releases earlier holds
before handback/ACK (acknowledgment). Admitted split errors return directly with
native-permitted harmless splits, never destructive local replay. Private
interior targets remain refused.

## Validation

For P=4 KiB and boundary B=2 MiB, left maps `[B-2P,B+P)` and removes `[B-P,B)`;
right maps `[B-P,B+2P)` and removes `[B,B+P)`. In address order, R=private,
Z=shared zero, U=untouched. All left RR/RZ/RU and right RR/ZR/UR layouts ran;
none was deduplicated. Read faults establish targets, and locked kernel walks
verify genuine zero PTEs without populating far-U survivors.

| Group | Cases | Different-task results |
| --- | ---: | --- |
| Six layouts × native/KD | 12 | 12 zero-target removals |
| Two split-error points × both orientations × native/KD | 8 | 4 errors matching native `-ENOMEM` and VMA layout |
| Retention loss, target-to-private, near/far busy × both orientations × native/KD | 16 | 8 exact handback/ACK pairs, sticky fallback |
| Published cancellation, both orientations | 2 | Exact retirement; victim mapping intact |
| Affected empty-to-zero transitions × both orientations × native/KD | 4 | 2 zero and 2 unchanged empty removals |
| Six preservation smokes | 6 | 12 separate removals |

There are 38 new cases, four affected transition cases and six smokes: 16 native
success/outcome comparisons and four native error comparisons. Negative controls
total 1,057 (769 new, 118 affected, 170 smoke). All 16 admitted new bodies/errors
retired their private-near hold. Left late-far refusal released its near hold;
right late-near refusal released its far hold. Early-refusal orders acquired no
earlier hold. Readers remained concurrent and local.

Example: left RR origin **1922** ran on **1921**, preserving near PFN (physical
frame number) `0x35d4d0`, with two private holds/releases and `zero_owned=0`.
Right UR origin **1962** ran on **1961**, with one private hold and a genuinely
missing far table. Both reported target zero PFN `0x3748`, cleared target PTE,
completed TLB work and unchanged tables. Right queued read-fault actor **2084**
changed an empty target before execution; origin **2081** then completed the
zero body on **2080**, with three pending requests and two local readers.

Initial VMA boundaries, survivor PTEs/content, private accounting, table bytes
and references matched native. Private near references were two before/after
and three during KD's exact hold. Zero-page references stayed outside that
ownership. Far-U remained untouched until checked, then faulted normally.
Later isolated writes preserved other survivors, neighbors and the independent
zero mapping. Removed addresses faulted before and after survivor accesses.
Full fixture cleanup retired tables/references before normal module unload.

## Build, evidence and recovery

Only captured kernel source `mm/kd_mmap_unmap.inc` changed. One incremental
candidate build required 3,157 dependent C compilations for its distinct release;
two affected clients were compiled and 17 unchanged clients reused. All 73
runtime modules and the test module regenerated split BTF (type metadata
referencing the kernel's type IDs) against the final unchanged ELF. Exact
kernel/module/install hashes and initramfs contents were checked before boot.
No kernel rebuild, candidate reboot retry or permanent deletion was needed.

Build/boot/live correctness checks passed. Three existing objtool warnings remain:
two `ibt_selftest` stack-frame warnings and a `relocate_restore_code` non-ENDBR
relocation. Probe compilation logged a Perl locale fallback warning. Hibernation
was not tested. The first offline audit assertion wrongly treated the probe's
private-only PFN array as a zero-page PFN report. The corrected audit binds the
zero classification and independently recorded native/queued zero identity;
[diagnostic record](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/collect-1/audit-correction.json).
No kernel/probe change or live rerun was required for that audit-script error.

- [Build](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/kd-1/result.json),
  [offline audit](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/collect-1/audit.json).
- [One essential archive](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/collect-1/essential.tar.gz):
  740,928 bytes, SHA-256 `3e29d14a6e29078646607ae753fc3af41d0b79b13a91539929aa62a42ff53a01`.
  Audit verifies 77 frozen inputs, 63 probe sources and 96 client/log hashes.
- [Identity receipt](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/identity/receipt.json):
  142,634,648 compressed bytes, SHA-256 `a9384acc765dbfc371723c692755b7717bd92fe89b229e32899899e39acd7ffd`.
- [Recovery](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/recovery-1/result.json),
  [health](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-boundary-interior-zero-near-private-20261024/final-host.json).

Candidate `6.1.159-kdmm29`, Build ID `f103e598e99e47a63b40d044ff8cbb0390492d50`;
manifest SHA-256 `bcb447e9d07cea07e6f215ee59131b6ee68fc143e8405cf6ab789d3a95af5945`.
Candidate boot `1cb071a1-c586-4f97-b7d6-4085ec7d1192`; recovery boot
`43d81d1f-345e-4d4d-b620-812f71c60548`. Recovery `6.1.159-kdclobber2`, all 5,686
recovery-module hashes and the exact 73 runtime modules remain verified. No test
module, armed next boot or kdmm29 RAM scratch remains. Snapshot, QEMU PID 257489,
64 vCPUs, 24 GiB, two NUMA nodes and placement are unchanged.

Budgets were 120,000,000 root bytes and 8,000,000,000 RAM bytes. Root free was
3,778,760,704 before build, 3,699,027,968 after install and **3,694,575,616** at
final recovery; final RAM free was 12,613,750,784 bytes. Old evidence, recovery
and unrelated checkout work were preserved. RAM intermediates cleared on reboot.

## Commands and limits

[Probe guide](../../../../../tests/kernel/mmap_lock/boundary_interior_zero_near_private/README.md).
Reuse installed outputs with fresh attempt directories on the idle original VM:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/audit.py
```

`run --attempt 2` uses an already verified candidate; audit is read-only offline.
Do not repeat preparation/build or overwrite completed attempts.

Private interior targets, larger VMAs, complex ancestry and general page-table
destruction remain unsupported. Queued near-page creation from zero/untouched,
interior neighbor replacement, opposite guard loss, huge/special-entry injection,
allocation exhaustion and uncontrolled write/fault/reclaim/pinning races remain
untested. Busy-survivor controls are deterministic eligibility changes, not a
race campaign. No new waiting-fault fixture, Native-off boot or historical matrix
was run. Performance/p95, mutex regressions and nano work remain deferred.

The next small coverage step is queued near-page creation under full resource
revalidation. The next useful implementation candidate is a private interior
target with an untouched near survivor, retaining exact target ownership through
native teardown. It remains refused; neither follow-up was started.
