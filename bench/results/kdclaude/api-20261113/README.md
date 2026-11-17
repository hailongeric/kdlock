# Syscall workloads on switchable lock objects (2026-11-13)

Kernel `7.0.0-38-kdclaude1` build #45 with `CONFIG_KDLOCK_MM` and
`CONFIG_KDLOCK_API` (docs/KERNEL_INTEGRATION.md 4b). Workload:
`bench/api_stress.c`, one process with N threads calling the real system
calls; each mode checks every result exactly (see the file header). Rate is
total operations per second over the run. `bench/run_api.py`: one untimed
3 s kd warm-up per mode (so the daemon has translated the sites), then per
point 5 s, Native and kd alternating within one boot through `kd_api`
(new process per point). Translator daemon on with `{"max_insns": 250000}`.
Host governor `powersave`, frequency not fixed. Two rounds: no variance claim.

| File | What |
| --- | --- |
| `api45.jsonl` | setfd, ofd, pipe, seek, xattr; 1-32 workers; 2 rounds; one boot |
| `uts45.jsonl` | uts (20% sethostname, 80% uname); native on the normal boot, kd on a boot with `kd_uts=1`: **two boots** |

## Result (medians of two rounds; ops/s)

| Mode (lock) | Workers | Native | kd | kd/Native | delegated (2 rounds) |
| --- | ---: | ---: | ---: | ---: | ---: |
| setfd (`file_lock`) | 1 | 447 923 | 448 036 | 1.00 | 0 |
| | 4 | 1 409 790 | 1 422 472 | 1.01 | 0 |
| | 8 | 1 623 990 | 1 649 563 | 1.02 | 28 539 |
| | 16 | 1 709 020 | 1 873 742 | 1.10 | 19.5 M |
| | 32 | 1 742 111 | 2 809 232 | 1.61 | 30.9 M |
| ofd (`flc_lock`) | 1 | 529 089 | 530 084 | 1.00 | 0 |
| | 4 | 1 023 721 | 1 249 800 | 1.22 (1.43, 1.06) | 0 |
| | 8 | 721 005 | 762 496 | 1.06 (0.95, 1.18) | 8.8 M |
| | 16 | 936 579 | 1 577 235 | 1.68 | 23.2 M |
| | 32 | 828 449 | 2 199 339 | 2.65 | 33.0 M |
| pipe (`pipe->mutex`) | 1 | 218 634 | 218 257 | 1.00 | 0 |
| | 4 | 359 243 | 352 792 | 0.98 (0.88, 1.09) | 0 |
| | 8 | 339 188 | 341 746 | 1.01 | 1.4 M |
| | 16 | 337 666 | 360 090 | 1.07 | 1.8 M |
| | 32 | 347 588 | 360 592 | 1.04 | 1.8 M |
| seek (`f_pos_lock`) | 1 | 768 664 | 771 155 | 1.00 | 0 |
| | 4 | 724 631 | 771 376 | 1.06 | 0 |
| | 8 | 776 800 | 832 169 | 1.07 | 0 |
| | 16 | 797 110 | 851 636 | 1.07 | 0 |
| | 32 | 776 449 | 809 958 | 1.04 | 0 |
| xattr (`simple_xattrs.lock`) | 1 | 414 512 | 415 292 | 1.00 | 0 |
| | 4 | 1 074 173 | 1 079 265 | 1.00 | 0 |
| | 8 | 1 434 753 | 1 290 582 | **0.90** (0.88, 0.92) | 0 |
| | 16 | 1 425 084 | 1 370 872 | 0.96 | 0 |
| | 32 | 1 367 626 | 1 390 264 | 1.02 (0.91, 1.14) | 0 |
| uts (`uts_sem`), two boots | 1 | 437 026 | 474 308 | 1.09 | 0 |
| | 4 | 455 178 | 1 378 934 | 3.03 | 0 |
| | 8 | 372 900 | 1 233 166 | 3.31 | 0.2 M |
| | 16 | 372 178 | 1 047 496 | 2.81 | 0.6 M |
| | 32 | 323 375 | 921 770 | 2.85 | 0.8 M |

Reading:

* setfd and OFD gain from delegation once it engages (16-32 workers): the
  sections are short and touch one files table or lock list, which stays in
  the combiner's cache.
* pipe delegates but is at parity: most pipe sections copy user memory and
  hand back.
* seek never delegates: `f_pos_lock` is held for a whole `read()`, whose user
  copy hands back, so the lock stays in the plain path. kd at 1.04-1.07.
* xattr never delegates (80% readers; queued writers take the lock plainly
  when the readers leave). The 8-worker point is a loss in both rounds
  (0.88, 0.92): the kd rwlock's reader path against native qrwlock.
* uts: the gain is **not** delegation. At 4 workers native makes 475 218
  voluntary context switches in 5 s, kd 58: native rwsem readers sleep behind
  a writer, the kd rwsem's waiters spin for a bounded time first
  (`kd_rwsem_spin_for`). Also, Native and kd here come from two boots.

## Correctness on this build

* `api_stress`, kd, each mode at 4/16/31 threads x 20 s (uts on the
  `kd_uts=1` boot): all checks passed; 40-66 M delegated sections per point
  for setfd and OFD; no kernel log entries.
* Every point above passed its checks (Native and kd).
* Same subtree build (`defconfig`; kernel/ fs/ mm/ lib/; 808 objects) with
  `kd_api=0` and with `kd_api=7` (every new files table, file, pipe, lock
  context and xattr set on kdlock, with the daemon running): byte-identical
  object files; no kernel warnings.
