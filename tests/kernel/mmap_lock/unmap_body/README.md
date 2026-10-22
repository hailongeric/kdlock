# Actual whole-VMA munmap correctness

Run only in the approved MM guest on the separately captured `kdmm4` kernel
with `kd_mmap=on`, the verified recovery snapshot and no other test running.
The module supplies queue/read-admission controls, never a body callback.
Userspace calls real `munmap`; cancellation workers call real `vm_munmap`.
See the [supported scope](../../../../kernel_integration/mmap_lock/UNMAP.md).

```sh
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z
cd /root/host_fs/kdlock
KD_UNMAP_SOURCE=/root/kdlock-kernel-work/mm-unmap-body-20261022/candidate-1/linux
KD_UNMAP_BASELINE=/root/kdlock-kernel-baselines/mmap-kdmm4-20261022
KD_UNMAP_OUT=/root/kdlock-evidence/10.176.26.71/tests/NEW-unmap
python3 tests/kernel/mmap_lock/unmap_body/test_receipts.py
python3 tests/kernel/mmap_lock/unmap_body/run.py \
  --kernel-source "$KD_UNMAP_SOURCE" --kernel-baseline "$KD_UNMAP_BASELINE" \
  --output "$KD_UNMAP_OUT/body"
python3 tests/kernel/mmap_lock/unmap_body/run.py --cancellation \
  --kernel-source "$KD_UNMAP_SOURCE" --kernel-baseline "$KD_UNMAP_BASELINE" \
  --output "$KD_UNMAP_OUT/cancellation"
python3 tests/kernel/mmap_lock/unmap_body/run.py --read-first \
  --kernel-source "$KD_UNMAP_SOURCE" --kernel-baseline "$KD_UNMAP_BASELINE" \
  --output "$KD_UNMAP_OUT/read-first"
```

Run each command only after its predecessor passes and drains. All output
directories must be new; do not reuse the recorded stage outputs. A snapshot
environment variable alone is not confirmation.
The commands require actual snapshot verification described in
[VM operations](../../../../docs/operations/VM.md). The `b787a90` probe passed all
three live cases on `kdmm4`; the initial
`50412ff` observer failure is retained in the
[stage record](../../../../bench/results/10.176.26.71/tests/mm-unmap-body-20261022/README.md).

Before closing writer admission, the probe opens and exercises its proc stack
observer, writes every output-buffer page, and prepares the late thread's
signal-jump/read machinery. This prevents first-use faults in the observer from
waiting behind the writer it is trying to observe. The later target access
still must produce the real blocked-fault stack and expected mapping fault.

The main probe places each target VMA (virtual memory area) in a distinct absent
PGD (top-level page-directory entry), with separately mapped neighbors. It queues
16 real whole-range calls behind two concurrent local mmap readers. A later
hardware read fault must wait at writer admission, then observe the removed
mapping as `SEGV_MAPERR`. Remote completion records must name the exact mm,
request, origin, different executor and original address interval. All target
pages must be absent and neighbors must survive.

Next, 16 populated partial removals must return to their original callers with
matching handback and acknowledgement (ACK) identities. Remaining page contents
and neighbors are checked byte by byte. Sticky refusal must route 16 later
whole-range calls locally. Cleanup removes every remaining mapping and checks
exact queue/slot retirement before unloading.

The read-first case installs a real zero-page translation before the queued
whole-range removal. This must refuse remote execution even without a private
anonymous reverse map. A repeated access on the original reader CPU must fault,
showing that local teardown invalidated the old translation. Cancellation sends
an ordinary signal and then a fatal signal to a queued origin: it must remain
linked until consumed, return `-EINTR`, and leave its mapping intact until cleanup.

Five receipt controls reject missing bodies, same-task execution, wrong ranges,
unmatched ACKs, missing readers/fault ordering, incomplete cleanup and escaped
sticky refusal. They do not replace live mapping and memory checks. A timeout
does not establish drain; preserve loaded state and investigate before any retry.
