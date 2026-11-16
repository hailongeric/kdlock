# Page faults on one shared mapping, with the mmap lock contended

The user asked on 2026-11-16 for a page fault test that is sure to contend
for the lock, for example threads faulting on one shared mapping.
`page_fault1` (TCLocks' will-it-scale) hardly does: each thread maps its own
region, and in Linux 7.0 a user-mode fault takes the per-VMA lock
(`lock_vma_under_rcu()`, `arch/x86/mm/fault.c`), not `mmap_lock`. The
shared-mapping tests are `bench/wis/tests/page_fault_shared{1,2,3}.c` (one
anonymous private mapping, a 64-page slice per thread, every page's tag
checked):

| test | faults | other operations per pass | `mmap_lock` |
|---|---|---|---|
| `page_fault_shared1` | user stores | `MADV_DONTNEED` | not taken (per-VMA lock); the control |
| `page_fault_shared2` | user stores | `MADV_DONTNEED`, then `mprotect` of one page to read-only and back, which splits and merges the shared VMA | the `mprotect` pair takes it for writing and write-locks the VMA; faults that find the VMA write-locked fall back to it for reading |
| `page_fault_shared3` | `read()` from `/dev/zero` into the slice (faults from kernel mode) | as 2 | every fault takes it for reading (`lock_mm_and_find_vma`), plus the writers of 2 |

| | |
|---|---|
| kernel | `7.0.0-38-kdclaude1` `#84 SMP PREEMPT_DYNAMIC Mon Nov 16 16:31:32 UTC 2026` (the clobber build, clobber entries on; the mmap lock does not use them) |
| host | 64 vCPUs as 2 nodes of 32, fixed at 2.7 GHz |
| runner | `bench/run_mmap1.py --rounds 2 --samples 3`, `kd_mm` alternating per point, workers on CPUs 0..N-1 |
| files | `pfs84.jsonl` (`page_fault_shared1`, `page_fault_shared2`, `page_fault1`), `pfs84b.jsonl` (`page_fault_shared3`), `pfev84*.jsonl` (`--events`), `pfrs84.jsonl` (reader spin A/B), the `.log` files |

All points ok, no kernel complaint. `pfs84.jsonl` also holds a first
`page_fault_shared3` series made with a binary that treated a short `read()`
from `/dev/zero` (a pending signal) as a failed check. Its threads points
are close to `pfs84b`. Its processes points have rate 0: the aborted tasks
stopped counting, and the harness did not notice. The test now finishes
short reads, and the runner counts a rate of 0 as a failure. `pfs84b` is
the series reported here.

## Is the lock contended? (`--events`, 16 threads, per second)

| test | Native rate | `mmap_lock` read | `mmap_lock` write | Native rwsem waits read / write |
|---|---|---|---|---|
| `page_fault1` | 3.04 M | 935 | 594 | 354 / 60 |
| `page_fault_shared1` | 2.91 M | 224 | 420 | 3 / 1 |
| `page_fault_shared2` | 1.62 M | 444 000 | 51 000 | **222 000 / 13 000** |
| `page_fault_shared3` | 1.55 M | 1 789 000 | 48 000 | **200 000 / 19 000** |

The two acquisition columns come from tracepoint `mmap_lock_start_locking`,
which fires for both backends. The waits are `lock:contention_begin` of a
native `rw_semaphore`, any object. In `page_fault_shared2` about a quarter of
all faults go to `mmap_lock`, and Native puts a reader to sleep for one in
two of those.

## Results (threads; kd/Native, median of 2 rounds, the rounds' own ratios in brackets)

| workers | `page_fault1` | `shared1` | `shared2` | `shared3` |
|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | 0.91 | 0.99 | 1.02 (1.02 1.03) | 1.05 (1.04 1.05) |
| 4 | 0.90 | 1.00 | 1.04 (1.04 1.04) | 1.08 (1.08 1.08) |
| 8 | 0.84 | 1.04 | 1.06 (1.05 1.07) | 1.10 (1.12 1.08) |
| 16 | 0.82 | 1.00 | **1.13** (1.14 1.13) | 1.02 (1.04 1.00) |
| 32 | 1.03 | 1.00 | 1.03 (1.03 1.03) | **0.78** (0.78 0.78) |
| 48 | 1.02 | 1.00 | 0.99 (0.98 0.99) | **0.82** (0.83 0.80) |
| 64 | 1.05 | 1.01 | **0.86** (0.87 0.86) | 0.97 (0.97 0.97) |

Native M faults/s at 16 threads: 3.04, 3.06, 1.67, 1.59. Processes model
(every task its own mm): 0.99-1.03 for all four tests at 16 and 64 tasks.

* **Nothing is delegated.** In every kd run of `shared2` and `shared3`,
  handbacks equal sessions, all `hb_frontier`, at most a few hundred per run
  (the counters are global; `pfs84*.jsonl` `kd_delta`). A split or merge of
  an anonymous VMA with pages takes `anon_vma->root->rwsem` for writing in
  `vma_prepare()`, a frontier (MMAP_LOCKS 2, row 2). What differs is the
  rwsem's waiting, not delegation.
* **Where kd wins it is reader spinning** (`pfrs84.jsonl`, same boot,
  2 rounds):

  | point | kd/Native, `kd_rwsem_rspin_ns` 50000 (default) | kd/Native, 0 |
  |---|---|---|
  | `shared2` 16 | 1.14 | 0.93 |
  | `shared2` 64 | 0.87 | **0.48** |
  | `shared3` 16 | 1.03 | 1.12 |
  | `shared3` 32 | 0.78 | 0.78 |
  | `shared3` 48 | 0.83 | **1.05** |

  A fault reader that waits for an `mprotect` writer spins instead of
  sleeping. The writer's section is short (the page is not present, so
  there is no TLB flush), so the spin usually succeeds. In `shared3`, where
  every fault is a reader, the same spin is what costs at 48 threads.
* **Open:** `shared3` at 32 threads (0.78, not reader spinning) and `shared2`
  at 64 threads (0.86, across the node boundary). `page_fault1` repeats the
  known loss at 2-16 threads (MMAP_LOCKS 5).
