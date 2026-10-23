# Actual mmap-lock kernel integration

The [bounded munmap experiment](UNMAP.md) now permits untouched survivors around
a resident one-page target in a three-page anonymous VMA (virtual memory area).
The `kdmm9` run passed all 22 serial cases, including 11 different-task mixed-page
removals. Exact page-slot ownership, untouched PTEs (leaf page-table entries),
retained contents, post-split errors, handback/ACK (acknowledgement), sticky
fallback and cancellation passed. A real fault into an untouched survivor waited
for writer release and resolved locally. Existing resident/untouched unmap,
advice and first-write fault paths passed preservation smokes. Recovery is
restored. The [result record](../../bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/README.md)
keeps the storage-check failure and completion without rebuilding distinct from
the successful live run. [Runnable commands](../../tests/kernel/mmap_lock/mixed_partial/README.md)
reuse the installed image and probes. Zero-page survivors, nonresident targets,
complex reverse-map ancestry, general table destruction and mapping creation
remain unsupported. This is not general MM support or performance evidence.

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
