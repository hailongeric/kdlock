# One populated anonymous page: correctness probe

Prepared for serial execution in the original approved MM VM. No live pass is
claimed yet. The module only coordinates existing readers/queues and retains
explicit test references to original pages; real userspace `munmap` and the
in-tree kernel body perform all removals. Cancellation uses real `vm_munmap`.
The separate populated opt-in preserves the old unpopulated admission.

The main case queues 16 one-page removals, then 16 unsupported partial removals,
then 16 sticky local calls. It checks original PFNs (physical page numbers),
every retained page byte, exact mapcounts and references, unchanged page-charge
ownership, neighboring data, originating-CPU cached-translation invalidation,
a real neighbor fault waiting on mmap reader admission, exact handback/ACK
(acknowledgement) records and final cleanup. Two existing readers stay concurrent
and local until the writer drains them. The same warmed stack-observer setup as
the validated unpopulated probe is required before retaining those readers.

Separate cases exercise fatal queued cancellation, local handback when absent
neighbors require page-table freeing, and the actual body without any extra
test page reference. The latter verifies initial physical identity and mapping
removal without dereferencing freed objects. Cleanup waits for native deferred
page-table callbacks and releases every exact owned test reference.

Run only on the already approved `kdmm5` KD boot after actual recovery snapshot
and idle checks in [VM operations](../../../../docs/operations/VM.md):

```sh
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z
cd /root/host_fs/kdlock
KD_POP_SOURCE=/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux
KD_POP_BASELINE=/root/kdlock-kernel-baselines/mmap-kdmm5-20261022
KD_POP_OUT=/root/kdlock-evidence/10.176.26.71/tests/NEW-populated-unmap
python3 tests/kernel/mmap_lock/populated_unmap/test_receipts.py
python3 tests/kernel/mmap_lock/populated_unmap/run.py \
  --kernel-source "$KD_POP_SOURCE" --kernel-baseline "$KD_POP_BASELINE" --output "$KD_POP_OUT/body"
python3 tests/kernel/mmap_lock/populated_unmap/run.py --cancellation \
  --kernel-source "$KD_POP_SOURCE" --kernel-baseline "$KD_POP_BASELINE" --output "$KD_POP_OUT/cancellation"
python3 tests/kernel/mmap_lock/populated_unmap/run.py --no-neighbor \
  --kernel-source "$KD_POP_SOURCE" --kernel-baseline "$KD_POP_BASELINE" --output "$KD_POP_OUT/no-neighbor"
python3 tests/kernel/mmap_lock/populated_unmap/run.py --free \
  --kernel-source "$KD_POP_SOURCE" --kernel-baseline "$KD_POP_BASELINE" --output "$KD_POP_OUT/free"
```

Each predecessor must pass and drain before starting the next command; output
paths must be new. A timeout is not drain. Preserve failure state and never force
unload. [Scope review and stage results](../../../../bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/README.md)
remain separate from older kernels and probes. Performance and broad support are
deferred.
