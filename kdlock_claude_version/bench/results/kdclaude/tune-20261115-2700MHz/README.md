# Tuning at a fixed 2.7 GHz (builds #67-#71, 2026-11-15)

Host and VM as round 7. Host frequency fixed at 2.7 GHz with turbo on
(BUILD_AND_TEST 1). Everything here is an in-boot alternation
(`run_ab.sh`, 3 rounds, kd only) unless stated; `*.summary.txt` is the
`ab_summary.py` output of the `.jsonl` of the same name, median and range
per point and value. File names end in the build they were measured on.

## 1. Rates differed between boots: the site lines (found on #69, fixed in #70)

* **Symptom:** kd spin c01 at 32 workers, fully delegated in each case:
  6.37 Mops/s (#67), 6.48 (#68), 4.38 (#69), with the same session code.
  The other families moved the same way but independently of each other:
  rwlock writers 5.87, 4.46, 4.48; rwsem writers 3.81, 3.90, 3.23; mutex
  c01 3.17, 3.87, 3.83. Native and TCLock did not move. The frequency was
  already fixed (2.0 GHz) in rounds 7 and 8, which show the same.
* **Cause:** `struct kd_site`, 72 bytes from the 96-byte slab, began at
  offset 0 or 32 of a cache line. At 0, `rip` and `entry`, which every
  contended caller reads, shared a line with the counters the combiner
  writes per section.
* **Fix:** the two groups are in separate lines and the object is aligned
  (ARCHITECTURE 3).
* **Check:** two boots of #70 agree within 2.2% at 24 points
  (`../grid-20261115-r9-64cpu/README.md`), all at the higher rate.
* Every kd number of rounds 1 to 8 carries this: each site was at one of
  the two rates. In-boot comparisons of those rounds are not affected.

## 2. CLDEMOTE (`dem67`, `dem69`, `dem70`)

`kd_cldemote` bits: 1 packet, 2 stack top (waiter, spin class); 4 the
combiner demoting both back after a section (#67 only); 16, 32 the waiter
bits for the sleepable class (from #69; in #67 bits 1 and 2 applied to
both classes).

| Value | Build | Result against 0 |
| --- | --- | --- |
| 3 | #67 (both classes) | spin c01 +0.6 to +1.2%, rwlock writers +0.6 to +2.2%, spin c08 +0.3 to +1.6% (16-64 workers); mutex c01 -0.3 to +0.2%, mutex c16 -0.4 to -0.9%, rwsem writers +0.2 to +1.4% |
| 3 | #70 (spin class) | spin c01 +3.0, +1.3, +1.4% at 8, 32, 64 workers; rwlock writers +2.0, +1.2, +1.4%; spin c08 -0.2, +0.4, +1.3% |
| 51 | #70 (both classes) | as 3 for the spin class; mutex c01 +0.3 to +0.7%, mutex c16 -0.6 to -2.7%, rwsem writers +0.4 to +1.1% |
| 4, 7 | #67 | -3 to -20% (spin c01 -20%, rwlock writers -18%, mutex c16 -11%) |

* Default 3: spin class only. Not kept: the combiner side.
* `dem69` is from the boot of #69 in which the spin c01 site was at the
  slow rate; its signs differ (spin c01 -0.6 to -3.1%, spin c08 +3.4 to
  +3.9%) and it is not used.
* The effect is small because the combiner already requests the next
  packet one section ahead.

## 3. Session prefetch stages (`pf68`), rejected

`kd_pf` bits, against 0 (the existing prefetch), 8-64 workers:

| Value | Meaning | Result |
| --- | --- | --- |
| 1 | sleepable class requests the next packet early, at the address guessed from `mnodes[0]` | -2 to +1% (mutex c01 at 8 workers +6%) |
| 2 | next waiter's stack top after the section | mutex and rwsem writers -15 to -27%, spin c01 -1 to -10%, spin c08 -7 to -8% |
| 3 | 1 and 2 | -1 to -10% |
| 6, 7 | plus node and guessed packet of the waiter after next | -1 to -14% |
| 14, 15 | plus the next stack top before the section | -1 to -18% |

The nano sections do not touch the origin's stack, and each line requested
is a transfer from a core that needs it back. Code archived as
`refs/archive/kdclaude-session-prefetch-stages-20261115`.

## 4. Session length (`batch68`)

`kd_batch`, against 1024:

| Workers | 256 | 4096 | 16384 |
| --- | --- | --- | --- |
| 16, 32 (one node) | -0.1 to -2.1% | -0.2 to +0.8% | -0.2 to +0.7% |
| 64, spin c01 | -16.6% | +5.1% | +5.9% |
| 64, rwlock writers | -11.8% | +3.0% | +3.7% |
| 64, rwsem writers | -11.8% | +2.0% | +2.1% |
| 64, mutex c01 / c16 | -10.5 / -10.3% | +1.2 / +1.6% | +0.7 / +1.7% |

Default 4096 from #69. The delay bound of a waiter on the other node grows
with it. TCLock's batch in the bench is 1024, its maximum.

## 5. Downgrade kept under the write side (`mmv_*`, `t71*`)

will-it-scale mmap1, threads, iterations per second, Native and kd in the
same boot; `kd_vdown` 0 and 1 alternating, 3 runs (`mmv.sh` recipe).

| Build | Threads | Native | kd, `kd_vdown=0` | kd, `kd_vdown=1` |
| --- | --- | --- | --- | --- |
| #71 | 4 | 318600-336300 | 258500-263900 | 373000-401100 |
| #71 | 8 | 288000-288300 | 259700-266400 | 369200-383500 |
| #71 | 16 | 271000-279900 | 255000-261400 | 368500-374800 |
| #71 | 32 | 274000-276100 | 251600-257200 | 371200-375800 |
| #71 | 64 | 147800-151200 | 150600-152200 | 305600-307700 |

* kd/Native with `kd_vdown=1`: 1.11-1.26 at 4 threads, 1.28-1.38 at 8-32,
  2.03-2.08 at 64. With 0: 0.77-0.83 at 4, 0.90-0.96 at 8-32, 1.00-1.03 at
  64.
* Sessions: with 0 every session serves one waiter and ends in a handback
  (`mmv_vdown0`: sessions = handbacks). With 1 at 32 and 64 threads the
  sessions run to the batch limit and handbacks are near zero.
* #67 and #69 (`mmv_*_b67`, `_b69`) show the same, with one difference:
  there the first run after the daemon started was slow (248000-270000 at
  4-16 threads), while the read part was still being learned and was
  handed back. On #71 a warm-up (`t71warm`) ran first.
* `mm_stress` (munmap of touched memory) passes with `kd_vdown=1`; there
  the read part is handed back at the TLB shootdown and the downgrade is
  done for real (`vdown_hb`).
* Cost not measured here: readers of the rwsem wait through the read
  parts. mmap1 has no readers.

## 6. Switched-off sites were never tried again (found on #70, fixed in #71)

* **Found:** on #70 the correctness run (`mm_stress`) came before mmap1.
  It switched the `mmap` and `munmap` sites off (most sections end at a
  frontier there), and mmap1 then ran without delegation
  (`mmv_*_b70_sites_off`: only `plain` waits; 281800-341300 at 4-32
  threads, 160800-170900 at 64).
* **Fix:** a switched-off site is switched on again after a wait that
  doubles from 1 s to 64 s with each switch-off in a row
  (`kd_site_retry()`, counter `site_retry`).
* **Check (#71, `t71_b71.txt`):** mmap1 directly after `mm_stress`:
  359400-383100 at 16 threads, 298800-306400 at 64, as before it.

## 7. Reader phase at 2.7 GHz (`rp70`)

`kd_rwsem_rphase_ns`, kd Mops/s:

| Profile | Workers | 0 | 250 | 500 | 1000 | 2000 | 4000 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rwsem c01 20% writes | 8 | 5.75 | 6.34 | 6.66 | 6.96 | 7.07 | 6.90 |
| rwsem c01 20% writes | 32 | 5.15 | 6.35 | 6.73 | 6.96 | 6.74 | 6.70 |
| rwsem c01 20% writes | 64 | 3.38 | 4.01 | 4.38 | 4.59 | 4.44 | 4.41 |
| rwsem c16 20% writes | 32 | 4.91 | 5.24 | 5.39 | 5.33 | 4.92 | 4.65 |
| rwsem c16 20% writes | 64 | 3.01 | 2.80 | 2.96 | 3.54 | 3.35 | 3.37 |
| rwsem c01 1% writes | 32 | 9.76 | 10.03 | 10.19 | 10.48 | 10.93 | 11.54 |
| rwsem c01 1% writes | 64 | 6.53 | 7.06 | 7.26 | 7.66 | 8.20 | 8.70 |

1000 stays the default: best or near it with 20% writes. With 1% writes a
longer phase is better, and kd is still far from TCLock there (12.42 at 64
workers in round 9). Open.

## 8. Correctness on #71

`corr71_b71.jsonl`, `corr71_b71.txt`: `run_corr` 312 points with 0
failed, `mm_stress` and `api_stress` passed except `setfd 63` (the fd
limit of the test), no kernel complaint.
