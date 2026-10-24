# kdmm28: empty interior removal beside a private resident page

**Complete:** 48 serial cases, two basic tests and 1,161 negative receipt
controls passed. The new path produced 12 verified different-task removals in
six native-matched layouts. Recovery is restored and test modules unloaded.
The completed kdmm27 campaign was reused as prior evidence, not repeated.

## Scope and mechanism

Remove one empty middle page from a three-page anonymous VMA (virtual memory
area) crossing a 2-MiB boundary. Its near survivor shares the target's existing
leaf table and is an ordinary writable, exclusive private anonymous base page;
the far survivor remains private resident, shared zero or untouched. Both
original outer-neighbor guards and the separate native two-split retention
proof remain required. No target page or table is allocated or released.

The old near-slot refusal was an implementation restriction. Existing caller
preparation already supplies both VMA descriptors, maple-tree reserves (mapping
index storage) and reverse-map links (page-to-mapping metadata) for simple
ancestry. Under the mmap writer and each current PTE (page-table entry) lock,
the shared classifier obtains an exact reference and nonblocking page lock.
Busy, pinned-indicator, shared/COW, compound and special pages still refuse.
It holds eligible survivors through both splits and native teardown, then
checks their identity/PTE and releases the exact held array on success or error.
An earlier hold is also released on later eligibility refusal, before handback.

Near-PTE comparisons ignore only hardware accessed/dirty bits: user stores may
change those without mmap_lock. Before testing, source review corrected the
initial accessed-only comparison. This does not claim concurrent-store testing.
No queue, ACK (acknowledgment), cancellation or allocator protocol was changed.
Shared-zero and private target transitions in this combination hand back before
splitting; admitted split errors return directly without destructive local replay.

## Results

For P=4 KiB and boundary B=2 MiB, left maps `[B-2P,B+P)` and removes `[B-P,B)`;
right maps `[B-P,B+2P)` and removes `[B,B+P)`. R=private, Z=shared zero, U=untouched,
in survivor address order. All left RR/RZ/RU and right RR/ZR/UR cases ran; none
was deduplicated. Locked walks verify actual empty/private/zero/missing states
before the probe accesses untouched survivors.

| Coverage | Result |
| --- | --- |
| Six layouts × native/KD | 12 cases; 12 remote removals |
| Two split-error points × both orientations × native/KD | 8 cases; 4 remote errors matching native `-ENOMEM` and harmless split layouts |
| Retention loss, target-to-zero/private, near/far busy × both orientations × native/KD | 20 cases; 10 exact handback/ACK pairs and sticky local fallback |
| Published cancellation, both orientations | 2 cases, exact retirement |
| Six preservation smokes | 6 cases; 12 separate remote removals |
| Receipt corruption controls | 1,161 rejected, including 991 for new cases |

There were 16 native success/outcome comparisons and four native error
comparisons. All 16 admitted new bodies/errors retired their near-page hold.
Left late-far refusal released the near hold; right late-near refusal released
the far hold. Both early-refusal orders acquired no earlier hold.

Examples: left RR origin **1933** executed on **1932**, retaining private PFN
(physical frame number) `0x34fbb9`; right UR origin **1972** executed on **1973**,
retaining `0x346bc2`. Exact reference observations were two before/after and three
during the KD hold. Left late-far refusal released `0x346bcb` with `effects=0`
before origin **2027** received its matching handback/ACK.

Surviving VMA boundaries, resident contents, PTEs, private accounting, table
bytes/identities and reference lifetimes matched native. Far-U stayed untouched
until checked, then faulted normally; zero reads/private writes and an extra
isolated near-private write passed. Neighbors and an independent zero mapping
remained intact. Removed addresses faulted before and after survivor access.
An empty target has no old translation to invalidate; this stage does not
claim populated-target TLB (translation lookaside buffer) shootdown coverage.
Readers overlapped locally; fixture cleanup retired mappings/tables/references
before normal unload. No kernel correctness failure was detected.

## Build failure, correction and evidence

Implementation commits: `ffee1b6` and `9419959`; module refresh: `f1b8088`.
Only captured kernel source `mm/kd_mmap_unmap.inc` changed. Initial release build
compiled 3,157 dependent C files, reused 17 clients and passed both basic tests.
The PTE comparison correction used 33 incremental C compilations.

**Boot attempt `kd-1` failed before tests:** reusing initial modules after kernel
relink left split BTF (module type metadata referencing the kernel's type IDs)
incompatible, despite unchanged symbol CRCs. The guest rejected modules and
entered emergency mode. The serial log and failed reachability checks remain.
After the coordinator exited, one ineffective graceful reboot request and one
same-QEMU reset restored the default recovery kernel. No test was interrupted.

Build 3 regenerated all 73 runtime modules and the test module against the exact
corrected ELF, then regenerated initramfs; it did **not** relink the kernel or
recompile clients. Its 408 dependent C compilations and all 74 BTF passes
completed. Old candidate modules/initramfs were retained by recoverable rename
under the guest work directory's `revision-3/`. No permanent deletion occurred.
Candidate boot `kd-2`, run `focused-2`, passed all checks. Three existing objtool
warnings remain (two `ibt_selftest` stack-frame warnings and a
`relocate_restore_code` non-ENDBR relocation); the probe build also logged a
Perl locale fallback warning. Hibernation remains untested.

- [Serial results](../../raw/tests/mm-boundary-interior-near-private-20261024/kd-2/result.json),
  [module refresh](../../raw/tests/mm-boundary-interior-near-private-20261024/build-3/result.json),
  [offline audit](../../raw/tests/mm-boundary-interior-near-private-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-boundary-interior-near-private-20261024/collect-1/essential.tar.gz):
  872,007 bytes, SHA-256 `f50185dcb756cb6d5fe50c8662e63011c4a030beebc39272d0ae5e80336d0909`.
  Audit binds 78 frozen inputs, 68 source copies and 96 client/log hashes.
- [Corrected identity receipt](../../raw/tests/mm-boundary-interior-near-private-20261024/identity-r2/receipt.json):
  142,638,480 compressed bytes, SHA-256 `d0a38302ca18d7f68209623e61574cd2d988a17c54fb4982e127b369ff2b5d8a`.
  The distinct initial identity and failed-boot evidence remain separate.
- [Recovery](../../raw/tests/mm-boundary-interior-near-private-20261024/recovery-1/result.json),
  [health](../../raw/tests/mm-boundary-interior-near-private-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-boundary-interior-near-private-20261024/final-host.json).

Candidate `6.1.159-kdmm28`, Build ID `9a302f12fa3e5da7c42c0bc7ddaeaa1972e1235e`,
manifest SHA-256 `55c21b633e3358c5cfa38b91a3154636138b409be31692814f32a31d8c3da6f4`.
Successful boot `74a52060-dceb-4845-8740-31fb4c000eb1`; final recovery boot
`2dd5b978-8909-49d0-b80f-2a468f437ee8`. Recovery `6.1.159-kdclobber2`, its
5,686 module hashes and 73 runtime modules remain verified. Snapshot, QEMU PID
257489, 64 vCPUs, 24 GiB, two NUMA nodes and placement are unchanged.
No test module, armed next boot or kdmm28 RAM scratch remains.

Module-refresh budget: 120,000,000 root bytes and 8,000,000,000 RAM bytes.
Root free before/after refresh: 3,754,385,408 / 3,716,960,256 bytes; final recovery:
3,779,641,344 root bytes and 12,613,750,784 RAM bytes. These are capacity readings,
not claimed cleanup savings.

## Reproduce and remaining gaps

[Probe guide](../../../../../tests/kernel/mmap_lock/boundary_interior_near_private/README.md).
With the same idle VM and verified recovery, reuse installed outputs:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/workflow.py kd --attempt 3
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/audit.py
```

`run --attempt 3` reuses an already verified candidate boot. Audit reads completed
evidence without live testing. Do not repeat preparation/build or overwrite runs.

Private interior targets and zero targets beside a private near survivor remain
unsupported. Queued near-page creation, interior neighbor replacement, opposite
guard loss, huge/special-entry injection, missing higher levels, allocation
exhaustion and uncontrolled write/fault/reclaim/pinning races were not exercised.
No new waiting-fault fixture or Native-off boot control was run. Larger VMAs,
complex ancestry, general table destruction, performance/p95, mutex regressions
and nano reruns remain deferred. Unrelated checkout changes were preserved.

The next useful extension is a shared-zero interior target with this private
near survivor, retaining the same proof and exact survivor holds while applying
native zero-PTE clearing without zero-page ownership. It remains explicitly
refused; no further stage was started. This is not general mmap support.
