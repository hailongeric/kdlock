# will-it-scale mmap1 with the mmap lock on kdlock (2026-11-13)

Kernel `7.0.0-38-kdclaude1` with `CONFIG_KDLOCK_MM` (docs/KERNEL_INTEGRATION.md
4a). Workload: the unchanged mmap1 test of will-it-scale from TCLocks'
repository (`bench/wis/`, TCLocks commit `bbfb9f00a`): each iteration maps
128 MiB of anonymous private memory and unmaps it untouched. `threads`
share one mm (one contended mmap lock); `processes` have one mm each (no
contention: a control for the uncontended path). Workers on CPUs 0..N-1
(`-n 1`). `bench/run_mmap1.py`: per point the harness's own warmup, then
three one-second samples; the rate is the harness's `average`
(iterations per second over all tasks). Native and kdlock alternate per
point within one boot: `kd_mm` selects the lock each new mm gets.
Translator daemon on with `{"max_insns": 250000}`. Host governor
`powersave`, frequency not fixed.

| File | Build | What |
| --- | --- | --- |
| `m41a.jsonl` | #41 | first run: works, but kd threads at 0.34-0.68 of Native |
| `m42.jsonl` | #42 | writer queue head spins by time (50 us) instead of 1024 pauses: no change (0.33 at 4 threads) |
| `m43.jsonl` | #43 | every holder of the rwsem's queue mutex spins by time before it sleeps: kd at or above Native |
| `mm1r1.jsonl` | #43 | the comparison below: threads and processes, 1-32 workers, 2 rounds |
| `mm1p.jsonl` | #43 | processes at 12 and 24 workers, 4 rounds: Native and kd both bimodal (about 1.18 M and 1.6 M), so the round-1 differences there are not effects |
| `corr43.jsonl` | #43 | nano correctness pass on the same build: 240 points exact |
| `ab43wspin.jsonl` | #43 | nano rwsem, in-boot A/B of `kd_rwsem_wspin_ns` 2000 against 50000 |

## Result (`mm1r1.jsonl`, medians of two rounds)

| Threads | Native | kd | kd/Native | delegated sections |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 203 734 | 203 560 | 1.00 | 28 |
| 2 | 219 261 | 214 852 | 0.98 | 1 602 |
| 4 | 208 026 | 203 453 | 0.98 | 3.6 M |
| 8 | 182 297 | 193 622 | 1.06 | 3.5 M |
| 12 | 182 696 | 194 791 | 1.07 | 3.5 M |
| 16 | 177 577 | 195 080 | 1.10 | 3.5 M |
| 24 | 107 739 | 132 148 | 1.23 | 2.4 M |
| 32 | 103 436 | 117 115 | 1.13 | 2.1 M |

Delegated sections are the mmap write sections; about as many munmap
sections are handed back at their downgrade, by design (the unmap runs as
a reader on the caller). Processes: 0.95-1.04 except two points inside the
bimodal spread (see `mm1p.jsonl`); no delegation, as expected.

Correctness on the same build: `bench/mm_stress.c` (data-checked mmap,
munmap, mprotect, mremap, MADV_DONTNEED, malloc and fork in one shared mm)
with kdlock mms at 4, 16 and 31 threads for 30 s each: every check passed;
a kernel subtree build and the bench module builds ran with `kd_mm=1`;
no kernel warning.

Nano rwsem with the new spin bound (`ab43wspin`): no change at 4-16
workers; 20% writers at 32 workers +74% (c01) and +87% (c16).

Not compared: TCLock on mmap1. Its port here is a set of modules for the
nano bench; the paper's mmap1 used a TCLocks kernel (5.14) with its rwsem
built in, which this VM does not run.
