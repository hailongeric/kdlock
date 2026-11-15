# mmap1 on 64 vCPUs: hang on handback, and the reader phase (builds #61-#66)

Host and VM as round 7 (10.176.26.71, 64 vCPUs as 2 x 32). Workload:
will-it-scale mmap1, threads, `run_mmap1.py`, Native and kd alternating
(`kd_mm` 0/1), 4, 16, 32 and 64 workers, 3 one-second samples per point.
The recipe below is two passes of that for `kd_rwsem_rphase_ns` 1000 and 0.

## Hang (fixed in #65)

* **Symptom:** the VM stopped answering during the recipe: #61 and #62
  (commit `3bf4bfaa`) in 3 runs, #63 (kernel source of `041653e4`) and #64
  in their first run, after 80 to 240 s. Runs with 4 and 16 threads only
  passed on #62 (9 boots, 134 points). mmap1 had not been run on this VM
  before; the defect is older than round 8.
* **State of the hung system** (all-CPU backtraces):
  * The combiner, holder of the queue mutex, on its wait stack, in
    `hrtimer_interrupt()` waiting for its own CPU's hrtimer base lock with
    interrupts off.
  * The queued writers in `kd_wait_sleepable()`, state `WAIT`.
  * Idle CPUs behind runqueue and hrtimer base locks
    (`update_curr_dl_se()` -> `start_dl_timer()` / `hrtimer_try_to_cancel()`).
  * No running context holds that hrtimer lock.
* **Cause:** a section was handed back with interrupts off while it held
  an interrupt-safe lock of the executor's CPU. A wakeup inside the copy
  takes the executor's runqueue lock and, for the fair server's timer, its
  hrtimer base lock. `kd_exec_one()` restored the executor's interrupt
  state before the session had published `KD_N_RESUME`, so a timer
  interrupt in that window waited for a lock that only the origin
  releases, and the origin was never resumed.
* **Fix:** after such a handback the executor keeps interrupts off until
  the resume is published (`struct kd_irq_hold`, `kd_irq_release()`).
* **Check:** #65, 6 runs of the recipe without a hang; #66, 3 more. Before,
  every run on #63 and #64 hung.
* **Not changed:** the origin still continues natively with a lock of the
  executor's CPU held. That is as designed (ARCHITECTURE 5, DIFFERENCES
  D3); it is correct only as long as the remaining code uses the pointers
  it already computed.

## Reader phase on mmap1

Iterations per second, kd, means of 2 passes per run.

| Build | Workers | rphase 0 | rphase 1000 |
| --- | --- | --- | --- |
| #65, one phase per reader found (5 runs) | 4 | 210600-218300 | 187100-189000 |
| #65 | 16 | 198700-203600 | 180300-183000 |
| #65 | 32 | 203700-204600 | 178400-179900 |
| #65 | 64 | 128400-129300 | 124500-127100 |
| #66, no phase for a single reader (3 runs) | 4 | 223500-236800 | 224600-244100 |
| #66 | 16 | 217100-223200 | 218000-232500 |
| #66 | 32 | 217300-218800 | 219000-235700 |
| #66 | 64 | 132800-134400 | 132100-134500 |

* On #65 the reader phase cost mmap1 about 12% at 4-32 workers: the one
  reader is the tail of the previous munmap after its downgrade. The first
  run of #65 is left out of the ranges; its rphase 1000 values were
  11-26% higher than in the other five runs, unexplained.
* #66 gives a single reader no phase; mmap1 then shows no difference.
* The nano gain stays (#66, in-boot alternation, 3 rounds, 20% writes,
  Mops/s, rphase 0 -> 1000): 8 workers 4.65 -> 5.41, 16 workers 4.66 ->
  5.76, 32 workers 4.46 -> 5.62, 64 workers 2.95 -> 3.93, 4 workers 7.57
  -> 7.56.

## kd against Native on this host (#66, rphase 1000, 3 runs)

| Workers | kd | Native | kd/Native |
| --- | --- | --- | --- |
| 4 | 224600-244100 | 269600-286500 | 0.83-0.86 |
| 16 | 218000-232500 | 232400-237200 | 0.92-0.98 |
| 32 | 219000-235700 | 233000-237900 | 0.94-0.99 |
| 64 | 132100-134500 | 128700-131100 | 1.02-1.03 |

kd is below Native up to 32 workers here. On 380G10 (`../mmap1-20261113/`)
it was 0.98-1.00 at 1-4 threads and 1.06-1.23 at 8-32. Different host; not
investigated.

## Files

* `m66_rphase0.jsonl`, `m66_rphase1000.jsonl`: the last run on #66.
  Earlier runs were overwritten in the VM; their means are in the tables.
* `corr66.jsonl`, `corr66.txt`: correctness on #66 after these runs:
  `run_corr` 312 points with 0 failed, `mm_stress` and `api_stress` passed
  except `setfd 63` (the fd limit of the test, round 7), no kernel
  complaint.
