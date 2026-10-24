# Actual mmap-lock kernel integration

The latest [bounded munmap extension](UNMAP.md#shared-zero-interior-target-with-native-clearing)
is `kdmm25`: remove a shared-zero middle target from a three-page anonymous
VMA (virtual memory area) crossing a 2-MiB boundary. The near survivor stays
untouched; the far survivor may be ordinary private resident, shared zero or
untouched. Locked PTE (page-table entry) revalidation, both outer-neighbor guards
and the separate two-split native retention proof remain mandatory. Native PTE
clearing and TLB (translation lookaside buffer) invalidation never own or release
the zero page. Private interior targets and populated near survivors refuse.

All 40 serial cases, two basic tests and 867 negative receipt controls passed:
six native-matched layouts, 16 new different-task removals (12 without private
holds), four native-matched split errors, four handback/ACK (acknowledgment)
pairs and two cancellations. Six smokes add 12 separate remote removals.
Recovery is restored and modules unloaded. See the
[results](../../bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/README.md)
and [commands](../../tests/kernel/mmap_lock/boundary_interior_zero/README.md).
Controlled queued zero-to-private changes hand back safely; uncontrolled
fault/reclaim/pinning races and hibernation remain untested. Three recorded
objtool linker warnings remain unresolved. No performance claim is made.

The preceding [empty-target extension](UNMAP.md#empty-interior-target-in-an-existing-table)
is `kdmm24`: remove a middle page with an empty PTE (page-table entry) in an
existing leaf table, within a three-page anonymous VMA (virtual memory area)
crossing a 2-MiB boundary. The near survivor stays untouched; the far survivor
may be private resident, shared zero or untouched. Locked revalidation, both
outer-neighbor guards and the separate two-split retention proof remain required.
On that image, populated target/near-survivor entries refuse before splitting;
kdmm25 adds only the shared-zero target subset above.

All 44 serial cases, two basic tests and 1,090 negative receipt controls passed:
six native-matched layouts, 16 new different-task removals (12 with no private
holds), four native-matched split errors, six handback/ACK (acknowledgment) pairs
and two cancellations. Six smokes add 12 separate remote removals. Recovery is
restored and modules unloaded. See the
[results](../../bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/README.md)
and [commands](../../tests/kernel/mmap_lock/boundary_interior_empty/README.md).

The preceding [missing-table extension](UNMAP.md#interior-removal-with-a-missing-target-table)
is `kdmm23`: remove the middle page of a three-page anonymous VMA (virtual
memory area) across a 2-MiB boundary when its target leaf page table is genuinely
missing. Two native splits establish the actual adjacent retention bounds;
both original outer-neighbor guards remain mandatory. The near survivor stays
untouched, the far survivor may be private resident/shared zero/untouched, and
no leaf table is allocated merely to unmap. Existing-table interior targets
were refused on that image; kdmm24 adds empty targets and kdmm25 adds shared-zero
targets within the same untouched-near subset.

All 44 serial cases, two basic tests and 1,092 negative receipt controls passed.
Six layouts matched native behavior, with 16 new different-task removals
(12 without private-page holds), four native-matched split errors, six exact
handback/ACK (acknowledgment) pairs and two cancellations. Six preservation smokes add 12 separate
remote removals. Recovery is restored and modules are unloaded. See the
[result record](../../bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/README.md)
and [runnable probe guide](../../tests/kernel/mmap_lock/boundary_interior_missing/README.md).

The [bounded munmap experiment](UNMAP.md#missing-target-table-shared-with-an-untouched-survivor)
previously added prefix/suffix removal from a three-page anonymous VMA (virtual memory
area) when its leaf page table is genuinely missing. The near survivor shares
that missing-table range and stays untouched; the far survivor lies across a
2-MiB boundary and may be private resident, shared zero or untouched. Both
outer-neighbor guards and the exact native table-retention proof remain mandatory.
No table is allocated merely to remove the target.

`kdmm22` passed 48 serial cases, two basic tests and 1,709 negative receipt
controls. Six feasible layouts matched native behavior. There were 20
different-task missing-table removals, plus two each after queued appearance of
an empty, shared-zero or private target. Twenty of these 26 removals held no
private pages. Split errors, handback/acknowledgment (ACK), cancellation, local
reader faults, target inaccessibility after survivor faults and cleanup passed.
Recovery is restored and test modules are unloaded. See the
[result record](../../bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/README.md)
and [runnable commands](../../tests/kernel/mmap_lock/boundary_shared_missing/README.md).
The [kdmm21 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/README.md)
and earlier campaigns remain separate. Eight smokes preserve existing shared
empty/zero/private and isolated missing-table paths without historical reruns.

Unsupported private pages, huge mappings, special entries and missing higher
levels remain refused. Other interior target classes, larger mappings, complex
ancestry, general table destruction and mmap creation remain outside this scope.
The [queued-neighbor follow-up](../../bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/README.md)
now validates replacement through a real native writer gate on the same kdmm22
image, without a kernel rebuild. Its 38 serial cases, two basic tests and 1,241
negative controls passed: seven remote removals of VMAs with replaced neighbors,
seven remote peers, seven retention-loss ACKs, two native-matched split errors
and two cancellations. Four preservation smokes add eight separate remote
removals and concurrent local readers. Native `mremap` retires the old neighbor
after publication; the combiner then uses the new locked bounds. See the
[probe commands](../../tests/kernel/mmap_lock/neighbor_replace/README.md).
Same-address/target-VMA replacement and uncontrolled fault/reclaim/pinning races
remain untested. No performance gain is claimed.

The separate [anonymous write-fault experiment](FAULT.md) passed focused serial
correctness on `kdmm3`: 129 real page-installation bodies completed on other
tasks, with PTE-bound receipts, concurrent local readers, exact handbacks/ACKs,
sticky refusal, cancellation and fault retry. The VM returned to recovery.
This is an explicitly enabled narrow path, not general mmap/page-fault delegation.
Its source, controls and results remain separate from the stages below.

The [minimal body experiment](BODY.md) adds an opt-in in-tree VMA flag update
under the actual KD mmap lock. Its `kdmm2` Native/KD correctness checks passed,
including actual combiner completion, origin handback, sticky refusal and queued
cancellation. The VM returned to recovery. Keep that evidence separate from the
installed local-only `kdmm1` results below.

This is an explicitly approved guest-kernel experiment on the existing
`10.176.26.71:2222` VM. The source baseline is `443baa6` and the recovery kernel
is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Historical captures under
`kernel_baseline/experiments/` remain inputs, not editable implementation trees.

The first integration uses KD physical exclusion for the actual
`mm_struct::mmap_lock`, with concurrent local readers and origin-local writers.
It does not admit complete MM critical sections into the JIT. Killable waits,
downgrade, nested old/new mm locking, fault retry, remote-mm access and deferred
read release must retain their existing semantics. No private workload lock
substitutes for the real mmap lock. Native and KD measurements, instrumentation
profiles and kernel revisions remain separate.

The main agent is the only writer. Source and static review run on `380G10`;
builds and tests run serially in the existing VM. No timing is authorized by a
partial correctness result. Keep untouched mmap/munmap and page-fault workloads
separate, and exclude TCLock from unsupported complete MM bodies.

Before installation, preserve and hash the existing boot image, initramfs,
configuration, symbol map and boot configuration. Keep its modules and source
tree intact. Install a distinct experimental release, retain the recovery entry
as the default, and use a one-shot experimental boot. Verify the real snapshot
`before-mutex-kdonly-20261017T140354Z` before live work. A timeout is not drain.

Stage evidence and remaining gaps are recorded in the
[integration report](../../bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/README.md).
The earlier [Native audit](../../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/INTEGRATION.md)
describes the starting limitations; its historical blocked status is retained.

## Basic correctness commands

The installed `6.1.159-kdmm1` image has separate Native-control (`kd_mmap=off`)
and KD-local (`kd_mmap=on`) entries. Recovery stays the default. These commands
apply only after the approved transition and identity/recovery checks; they do
not install or reboot a kernel. The current basic handoff reuses the successful
[both-mode validation](../../bench/results/10.176.26.71/tests/actual-mm-plain-20261021/README.md)
without another transition solely to repeat unchanged tests.

On the experimental KD boot, with the pinned environment and verified snapshot:

```sh
cd /root/host_fs/kdlock
KD_MM_SOURCE=/root/kdlock-kernel-work/mmap-20261021/candidate-1/linux
KD_MM_BASELINE=/root/kdlock-kernel-baselines/mmap-kdmm1-20261021
KD_MM_MODE=kd
KD_MM_OUT=/root/kdlock-evidence/10.176.26.71/tests/mm-basic-NEW
python3 tests/kernel/mmap_lock/run.py --mode "$KD_MM_MODE" \
  --kernel-source "$KD_MM_SOURCE" --kernel-baseline "$KD_MM_BASELINE" \
  --output "$KD_MM_OUT/api"
python3 tests/kernel/mmap_lock/mapping.py --mode "$KD_MM_MODE" \
  --api-result "$KD_MM_OUT/api/result.json" \
  --kernel-source "$KD_MM_SOURCE" --kernel-baseline "$KD_MM_BASELINE" \
  --output "$KD_MM_OUT/mmap"
python3 tests/kernel/mmap_lock/faults.py --mode "$KD_MM_MODE" \
  --kernel-source "$KD_MM_SOURCE" --kernel-baseline "$KD_MM_BASELINE" \
  --output "$KD_MM_OUT/page-fault"
```

Run each command only after its predecessor passed and drained. On an already
verified Native-control boot, use `KD_MM_MODE=native` and a new output root.
The mapping task does not touch the payload and requires zero fault callbacks.
The fault task separately exercises fork/COW, remote access, fault retry and
VMA changes. Readers are concurrent and local; KD MM writers also execute
locally. Neither these tests nor their receipts claim delegated MM bodies.
TCLock is excluded from these operations.

## Experimental interface and lifetime

`CONFIG_KD_MMAP_LOCK` gives the actual mm object an immutable backend choice.
Both `kd_mmap=off` (Native control) and `kd_mmap=on` (KD backend) use the same
kernel image and mm layout. `init_mm` remains Native. Dynamic mm initialization
chooses the boot mode before publication; no acquisition can switch protocols.
The builtin implementation is a namespaced copy of the maintained KD physical
mutex/rwsem code. Its preallocated node slots retain separate OSQ links and exact
object identity. The base lock API executes locally; the explicitly enabled
advice, fault and munmap entries add their separately validated built-in bodies.

Read releases transferred to BPF irq_work retain a unique `mmap_read_token` and
an mm-count reference. Completion consumes the record once, releases its actual
read share, and defers final mm destruction to process context. The record, not
an approximate observation, authorizes that release. KD read trylock refuses
IRQ-disabled calls before making a reservation; the existing BPF fallback
handles this restriction. RT and lockdep configurations are excluded explicitly.

`prepare.py` requires the pinned upstream archive, exact captured ancestor
sources and a fresh build directory. It rejects configuration drift beyond the
new release name and integration option. `capture.py` binds the inherited and
new sources, configuration, ELF and Build ID into a separate baseline.
`install.py` requires untouched recovery hashes and absent experimental
destinations, signs the freshly built runtime modules and preserves the recovery
default. It does not reboot. Experimental entries are selected only for a
one-shot boot after evidence preservation and a verified idle guest.

## Correctness tasks

Run these serially in the same VM, with the pinned Python, explicit mode and
captured experimental kernel source/baseline arguments:

- `tests/kernel/mmap_lock/run.py`: both basic programs, actual-mm API ownership,
  concurrent readers, sleeping writer, killable cancellation, nested objects,
  downgrade, IRQ refusal, unique read transfer and final asynchronous destruction.
- `tests/kernel/mmap_lock/mapping.py`: the six existing untouched mapping cases,
  including 81,000 map/unmap cycles, exact mm/TID identity and a writer call chain
  decoded from this kernel ELF. Its required `--api-result` must belong to the
  same boot and mode. Corrupted writer proofs must still be rejected.
- `tests/kernel/mmap_lock/faults.py`: fork/COW, remote access and exit, plus a
  userfault wait that permits a writer to split the unresolved fault's VMA.
- `tests/kernel/mmap_lock/page_fault_completed/run.py`: observe real file-write
  fault returns for an exact mm/task/address range, verify 64 genuine
  `VM_FAULT_COMPLETED` results, re-acquire the write lock and check persisted data.

These fault tasks are distinct from untouched mmap/munmap. A returned JIT body
is never claimed for either task. Keep preliminary boots, corrected snapshots,
matched runtime-module sets and later timing as separate run identities.
`archive.py` retains the standard archive checks and additionally verifies the
exact experimental source/config/build/live identity before archiving.

The selected correctness tasks passed in both Native-control and KD-local modes
on `6.1.159-kdmm1`, with matching runtime modules, full task teardown and preserved
recovery artifacts. The report records the failed preparations and later passes
separately. No experimental-kernel timing has been collected. This scoped result
does not validate arbitrary MM delegation, all filesystem/device callbacks,
all configured modules, RT, lockdep or whole-kernel mutex replacement.
