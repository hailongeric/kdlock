# Real anonymous write-fault body correctness

This guest-only probe exercises the real x86 page-fault route in the separate
`6.1.159-kdmm3` experiment. Ordinary stores to fresh anonymous pages trigger the
fault. The test module supplies queue coordination and observations, not a fault
body callback. See the [protocol and scope](../../../../kernel_integration/mmap_lock/FAULT.md).

The supported operation installs an already allocated and charged page into its
real PTE (page-table entry). The original thread retains a local mmap read lock.
A different task can execute the installation using explicit mm (address-space)
and caller context. Two additional readers retain concurrent local acquisitions.

Run serially only after the approved KD boot, exact kernel verification and a
real recovery-snapshot check. The source-side [coordinator](../../../../bench/results/10.176.26.71/tests/mm-fault-body-20261022/validate.py)
performs those checks and also runs Native controls and advice preservation.
The individual guest commands are:

```sh
cd /root/host_fs/kdlock
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z
KD_FAULT_SOURCE=/root/kdlock-kernel-work/mm-fault-body-20261022/candidate-1/linux
KD_FAULT_BASELINE=/root/kdlock-kernel-baselines/mmap-kdmm3-20261022
KD_FAULT_OUT=/root/kdlock-evidence/10.176.26.71/tests/fault-body-NEW

python3 tests/kernel/mmap_lock/fault_body/test_receipts.py
python3 tests/kernel/mmap_lock/fault_body/run.py \
  --kernel-source "$KD_FAULT_SOURCE" --kernel-baseline "$KD_FAULT_BASELINE" \
  --output "$KD_FAULT_OUT/body"
python3 tests/kernel/mmap_lock/fault_body/run.py --cancellation \
  --kernel-source "$KD_FAULT_SOURCE" --kernel-baseline "$KD_FAULT_BASELINE" \
  --output "$KD_FAULT_OUT/cancellation"
python3 tests/kernel/mmap_lock/fault_body/run.py --retry \
  --kernel-source "$KD_FAULT_SOURCE" --kernel-baseline "$KD_FAULT_BASELINE" \
  --output "$KD_FAULT_OUT/retry"
```

The environment flags record a verified recovery check; setting them does not
create a snapshot. Use a new output root. Stop dependent work after a failure;
a deadline does not prove drain. Unknown workers retain the module and context
for diagnosis. Never force unload.

The main case uses 16 pre-created origins on CPUs 0–15, a gate controller on 62
and collector on 63. The module's readers use 60–61. Creating pthreads precedes
retaining the readers because creating their stacks can need mmap write access.
Only the immutable test interval participates; incidental stack/runtime faults
do not enter the experimental queue.

| Separate case | Required evidence |
| --- | --- |
| Body | 256 supported initial writes; different-task completion records matched to actual `/proc/self/pagemap` PFNs (physical frame numbers); 256 distinct private physical pages; initial zeros and every final byte verified. |
| Refusal | 16 locked anonymous first writes complete locally; 15 exact remote handback/ACK identity pairs; one permanent refusal transition. |
| Sticky continuation | 128 later ordinary writes remain local; remote body and ACK totals do not increase; all contents match. |
| Queued cancellation | A real kernel `put_user` write faults while queued. A nonfatal signal does not retire it; a fatal signal cancels before installation. The healthy leader's PTE exists, the victim's PTE remains absent, the original read lock is released, and both workers join. |
| Retry | A userfaultfd missing-page write is refused remotely and ACKed. The origin drops its read lock through the native retry path; another mmap writer succeeds while that fault is unresolved. Userfaultfd resolves the page, the original store completes, contents match and a subsequent ordinary fault stays local. |
| Cleanup | Exact fault-gate/node idle, all workers joined, arena unmapped, device closed, module unloaded and no new kernel fault. |

Read faults are checked to leave delegation counters unchanged. The PTE lock
protects the actual installation; queue counters never replace exact ownership
or slot retirement. Refusal ACKs acknowledge the borrowed request and ownership
retirement, not completion of the later native fault. The completed request is
detached before its origin can enter a blocking userfaultfd continuation.

The recorded `kd-1` run passed: 129 remote installations, 16 PTE-bound receipts,
400 verified user-written pages, 15 handbacks/ACKs and 128 post-refusal local
calls. Cancellation and retry passed separately, including one additional
matched userfaultfd refusal/ACK. There are no JIT bodies or timing measurements.
Untouched mmap and the existing COW, remote-mm, lifetime and completed-file-fault
checks remain separate tasks. See the [stage record](../../../../bench/results/10.176.26.71/tests/mm-fault-body-20261022/README.md)
for retained compilation failures and the complete evidence inventory.
