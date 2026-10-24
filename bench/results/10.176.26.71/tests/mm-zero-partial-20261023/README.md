> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Shared-zero survivors in bounded partial munmap

Passed on `6.1.159-kdmm10`: **44 serial cases, two basic programs and 576
negative receipt controls**. The 15 new layouts produced **30 different-task
removals**; a separate final-release case added one, for **31**. Two delegated
split errors matched native behavior. Recovery is restored and all test modules
unloaded normally. This required a kernel extension, not validation alone.
No performance, p95, mutex-regression or nano work ran.

Implementation and frozen inputs: `1beb49ea38b630373d3a45609d77b2bd8dc26b23`.
Only `mm/kd_mmap_unmap.inc` changed relative to the captured kdmm9 kernel.
The [completed mixed baseline](../mm-mixed-matrix-20261023/README.md) and
[resident/split-error baseline](../mm-resident-partial-20261023/README.md) remain
separate, unchanged evidence; their complete campaigns were not repeated.

## Mechanism and boundary

One ordinary private resident anonymous page is removed from an exactly
three-page VMA (virtual memory area). A retained slot may be R (private resident),
U (untouched, absent PTE), or Z (read-faulted shared zero page). A PTE is the leaf
page-table entry; a zero read alone does not prove a Z mapping. The existing
read-only probe classifies the actual present PTE using `is_zero_pfn()`.

The owner additionally requires a read-only, special, present, non-device zero
PTE, without protection-none state. It records that entry separately from the
owned private pages. Native `vm_normal_page()` deliberately excludes the
permanent zero page; it must never enter ordinary page locking, reference
release or private resident accounting. No new allocation is needed. Caller
preparation still supplies the VMA descriptors, reverse-map links (connections
between pages and mappings) and mapping-index reserves. Locked revalidation,
ancestry restrictions and table-retaining neighbors are unchanged.

After native split/unmap, zero survivor entries must match their saved identity
and protection on success and admitted errors. Only the hardware accessed bit
is ignored, because a concurrent reader can set it. The target still passes
all private-page checks. Its native removal, TLB (cached translation) flush,
page unlock/reference release and completion execute on the combiner.
Pre-effect refusal releases exact holds, hands back to the waiter and matches
its ACK (acknowledgement), then makes later calls local. After a split can take
effect, errors return directly with native-compatible harmless splits; the
operation is never replayed locally. Readers remain concurrent and local.
See the [maintained scope](../../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-page-survivors).

## Focused results

Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-zero-partial-20261023`,
run `focused-1`. Each shape runs a native control and three KD callers, two of
which complete remotely. Native uses the ordinary body with delegation disabled
on the same KD lock backend, not a separate Native-off boot. No symmetry is
assumed: all 15 combinations run separately.

| Removed position | Initial slots for `zu`, `uz`, `zr`, `rz`, `zz` | Remote removals |
| --- | --- | --- |
| Prefix, slot 0 | RZU, RUZ, RZR, RRZ, RZZ | 10 |
| Interior, slot 1 (`middle`) | ZRU, URZ, ZRR, RRZ, ZRZ | 10 |
| Suffix, slot 2 | ZUR, UZR, ZRR, RZR, ZZR | 10 |

Read-only PTE and per-VMA `smaps` observations precede controller survivor reads.
RSS (resident set size) and anonymous bytes count only private resident pages:
Z and U contribute zero. Native/KD VMA bounds, offsets, flags and these counters
match before removal, after completion and after explicit survivor writes.
The target faults on its originating CPU after its cached translation was
warmed; resident survivors retain their physical pages and full-page contents.
Untouched slots stay absent until explicitly accessed, except the separately
recorded competing read fault. That fault blocks at reader admission, then
resolves locally to Z; if both survivors already have PTEs, it uses an untouched
neighbor. Two local readers overlap before writer admission.

After pre-access checks, full reads verify zero fill. Each subsequent write
converts exactly one survivor to a distinct private page; another zero survivor
and an independent zero mapping remain zero and unchanged. The 38 new cases
record **120 isolated private-write steps, 107 exact test-reference releases and
228 cleanup calls**. No test reference is taken on Z or U. The free case drops
all test references before execution and proves one real remote final release.

Example `zero-middle-zz`: mm `ff1100010c1e7400`, request 2, origin **1941**,
executor **1942**, target PFN (physical page number) `0x34dac6`. Paired completion
records report resident mask 2, zero mask 5, untouched mask 0, one hold/release,
removed PTE absent, mapcount zero, tables retained and zero PTEs preserved.
Both surviving VMAs have zero private RSS after removal and 4 KiB each after
private writes. Local heads, fallback, cleanup and errors are excluded from the
31 remote-success count.

Controls passed: native/KD `ENOMEM` after interior split 1 and split 2 (two
remote errors, same surviving layout); busy final resident page and zero-page
**target** refusal (two exact one-hold rollbacks and matched handback/ACK pairs,
then sticky fallback); queued fatal cancellation (mapping retained); final
release without test pins. No destructive replay or stranded ownership remained.

Six preservation smokes passed: mixed partial (2 remote removals), fully resident
partial (2), untouched partial (15), four-page whole removal (15, 60 physical-page
receipts, 144 origin translation checks), advice (1,721 returned remote bodies)
and separate first-write faults (151 real remote page installations). The
negative controls reject corrupt copies of real records; they are not live
executions. Of 576 controls, 556 belong to the new zero-page cases.

## Headroom, build and recovery

Read-only host/guest free-space, inode, image-allocation and artifact-size checks
preceded mutation. The constrained filesystems were guest root (3,489,792 bytes
available immediately before approved cleanup) and guest data (10,031,104 bytes).
Host checkout/image filesystems and inodes were adequate. With explicit approval,
only `/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux/.tmp_vmlinux.btf`
was removed: a regenerable, unreferenced link intermediate, **776,753,152 bytes
(740.77 MiB)**. Its hash and deletion receipt are retained; no other historical
artifact, result, cache, image or snapshot was deleted or modified.

The measured budget was 225,280,844 persistent bytes plus 8,908,800 bytes of prior
boot-cycle growth. Packaging's 108,368,896 temporary bytes and the conservative
7,739,283,276-byte build-file model fit RAM storage. The new build used a private
RAM overlay on the existing kdmm5 tree; native split/rmap patches and unchanged
kdmm9 integration inputs were reused. A distinct release changes dependencies:
Kbuild recorded 3,161 compile steps because the changed release affects dependencies.
Seven unchanged clients were reused. Four unchanged probe sources and the 73
runtime modules were rebuilt for the new release. Only the new userspace probe
was compiled. No full source-tree copy or new data-disk artifact was made.

Observed root usage grew 224,804,864 bytes across build/install/identity storage,
within the persistent estimate. Final recovery has **550,801,408 root bytes**,
10,031,104 data bytes, ample inodes and empty RAM storage. Recovery boot files,
5,686 module files and default boot selection remain preserved. Same VM,
64 vCPUs, 24 GiB, two NUMA nodes, pins, QEMU PID 257489 and real recovery snapshot
`before-mutex-kdonly-20261017T140354Z` were checked. No run was interrupted.

| Identity | Value |
| --- | --- |
| Candidate Build ID | `cc732abe659b1093c82b06c637ff8bb36948c672` |
| Candidate manifest | `c03f93aa306534ca60df511ab46ae11e09fdc211d6e69553f0632ce832da607a` |
| Candidate boot | `75f59004-fa2f-4733-81d2-1546d651d20e` |
| New client SHA-256 | `30a68a4958883b75e6bf5c825db63ded842feef4bf1c5c5177979117b99bc584` |
| Focused result SHA-256 | `6af36487138e9c4f9f99be103d4826432707788b8bda3bd8f63fca92c5ea874d` |
| Recovery Build ID | `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Recovery boot | `6b257c2a-073b-4c6c-bf3e-39528f538a88` |

No build or live case failed. A final read-only health checker initially rejected
GRUB's empty `next_entry=` field. Inspection proved no armed selection; the
corrected check requires an absent or empty value. Both receipts remain. Final
health passed with the exact 73 runtime modules, no project modules or temporary
build files, no new kernel faults and recovery idle. Existing `fd0` floppy I/O
messages remain recorded; they are not new MM faults.

## Evidence, commands and limits

One new essential archive, **625,155 bytes**:
`bench/results/10.176.26.71/raw/tests/mm-zero-partial-20261023/collect-1/essential.tar.gz`,
SHA-256 `28e5d3fa2bd6409ecbd1ce5904e2ddaa2f13c0482aa359b98891f35897cf2afb`.
It holds the new inputs, build/transition receipts and all client/kernel-log
pairs. One offline pass verified all 44 pairs against recorded hashes.
The same raw directory retains `headroom/`, `final-health-2.json`, the initial
health-check failure and `evidence-check.json`. Previous archives and unchanged
binaries were referenced, not copied or rescanned.

[Runnable commands](../../../../../tests/kernel/mmap_lock/zero_partial/README.md)
reuse this installed image and frozen probes. This milestone executed
`workflow.py prepare`, `build`, `kd`, `recovery`, and one `collect`, each at
attempt 1. Source edits and offline inspection stayed on `380G10`; builds and
all tests ran only in the existing VM. Unrelated cleanup-document work remains
unmodified by this stage.

Zero/nonresident targets, complex ancestry, shared/huge/swapped pages, larger
mappings, general page-table destruction and mmap creation remain unsupported.
Forced mapping/residency changes between preparation and execution, concurrent
zero-page write faults during the body, fast-pinning/reclaim races, allocation
pressure, post-admission cancellation and Native-off controls were not exercised.
The busy-page control proves locked page-state revalidation, not a forced VMA
replacement. Post-split failures occur before destruction; no recoverable error
is replayed after destruction begins. No general MM support is claimed.

The next small candidate is a zero-page **target** in the same three-page VMA
with at least one private resident survivor and retained tables. It would need
separate target identity/absence receipts and zero-page accounting, without any
ordinary zero-page release. It is not implemented here. Broader mapping support
and all performance work remain deferred.
