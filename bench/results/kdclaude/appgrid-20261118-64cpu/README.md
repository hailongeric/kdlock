# Full grid: nano (cachelines 1 and 8) and application benchmarks

> **Baseline caveat (found 2026-11-19).** The native kernel of this round
> was built without `CONFIG_PARAVIRT_SPINLOCKS`. In a KVM guest such a
> kernel leaves `virt_spin_lock_key` on and every contended native spinlock
> (and with it the native rwlock's writer queue) is a test-and-set lock,
> not the queued one; `nopvspin` does not change that without the option.
> Every "native" figure here that depends on a contended spinlock or rwlock
> is therefore against a slower lock than bare-metal Linux runs: ratios of
> kd spinlock and rwlock cases, lock1, the FxMark directory cases and the
> like overstate kd. Cases whose contention is on a mutex or an rwsem (the
> mmap lock) are much less affected. The corrected twins are kdnat11 and
> later; see
> [../plain-20261119-64cpu/](../plain-20261119-64cpu/README.md) section 1.

Done on 2026-11-18 in the kdclaude VM: 64 vCPUs as 2 nodes of 32, 24 GiB,
host fixed at 2.7 GHz, `nokaslr nopvspin`. Workers 1-8 one by one, then
every fourth to 64 (22 points).

## 1. Kernels and modes

| kernel | role |
|---|---|
| `7.0.0-38-kdnat9` #9 | **native**: native locks, kdlock built in (`CONFIG_KDLOCK_ALL` off); also the nano kernel, where native, kd and TCLock run side by side as bench backends |
| `7.0.0-38-kdall10` #13 | **kd**: every lock a kdlock; the committed state (`787264dc`, kdall-native-20261117-64cpu section 8) |

- **kd off:** kdall10 without the daemon (plain mode, nothing delegated).
- **kd on:** kdall10 with `jit/kd_daemon.py`, the allow lists of the native
  comparison (`bench/allow/api.txt`, `torture.txt`, `mm.txt`: the syscall
  locks, locktorture, and the mmap lock writers of brk, mmap and munmap) and
  the knowledge learned for this build (`/root/kds_cmp.json`, boot learn10).
  Nothing else is on the allow lists: file-system, socket and futex locks
  run in plain mode in "on" as well.
- **TCLock** only in the nano grid. Its whole-kernel form is a patched Linux
  5.14.16 (`TCLocks/src/kernel/linux-5.14.16`); it cannot be booted as a
  7.0 kernel, and a 5.14 kernel would not compare with these, so the
  application benchmarks have no TCLock column.

Boots: kdall10 (kd off, then kd on: `app_grid.sh`), then kdnat9 (nano grid,
then native: `nat_boot.sh`). One run per application point, so one boot per
mode: application ratios within about 5% of 1 are within run-to-run noise
(section 5 of kdall-native-20261117-64cpu has the spread of 3-boot series).

## 2. Benchmarks and how they run

Sources, built in the guest (`build_apps.sh`); the guest has no access to
GitHub or to the Ubuntu archive (a proxy answers), so sources were fetched
on 380G10 and the missing packages (libpcre2-dev, libtool, unzip,
libdb-dev) installed from their `.deb` files:

| benchmark | source | run as |
|---|---|---|
| nano | `bench/kd_bench.c`, `run_grid.py --profiles appgrid` | spin, mutex, rwsem (1% and 20% writes), rwlock (1% and 20% writes), each with 1 and 8 cache lines in the section: 12 profiles; 1 s per point after 0.5 s warm-up, 2 rounds |
| will-it-scale | TCLock's copy (`TCLocks/src/benchmarks/will-it-scale`) | threads, `-n 32` (cores per socket, as TCLock's `runtest.py`), 10 s per point; `lock1` and `mmap1` (TCLock's set), `mmap2`, `brk1`, `page_fault1-3`; our own `page_fault_shared*` are not run |
| FxMark | TCLock's copy | MWRM and MRDM on tmpfs, 30 s, as TCLock's `run-fxmark.py` |
| LevelDB | TCLock's `leveldb-1.20` | `fillseq` (1 thread) into a tmpfs database, then `readrandom` with N pinned threads (`--pin_threads=1`, `taskset 0..N-1`) for 30 s, as `run_db_bench.sh` |
| Metis | IntervalVM's copy (`kaist-cp/interval-vm`, `metis/`) | `wrmem -p N` under `taskset 0..N-1`, default input, as TCLock's vbench (model default); wall time |
| Psearchy | IntervalVM's copy (`psearchy/`) | `pedsort -t /tmp/db/db -c N -m 128 -l 200000` over the 93 283 files of the kernel source tree (page cache), index on tmpfs, as TCLock's vbench (mode thread) |
| Apache | IntervalVM's copy: httpd 2.4.62, `mpm_event`, its configurations | 64 KiB static page, `wrk -t64 -c100 -d10s` on the same machine, as in "Scalable Address Spaces using Concurrent Interval Skiplist" (SOSP '25): one server process with N threads, and the default configuration (3-12 processes of 25 threads) once per mode |

Local changes to the benchmark sources (all under `/home/eric/vm/vm-shared/appbench`, not in this repository):
- FxMark's helper scripts (`bin/cpu-sequences`, `set-cpus`, `gen_corepolicy`, `cpuinfo.py`) ported to Python 3 (2to3, `file()` -> `open()`, tabs).
- Metis `lib/bench.h`: without cpufreq in sysfs, `get_cpu_freq()` returns `METIS_CPU_HZ` or 2.7 GHz instead of 0 (only reported times use it; the grid measures wall time). The unpatched binary died with SIGILL.
- LevelDB built without jemalloc (`db_bench` does not link it; the copy lacks jemalloc's doc templates).
- Psearchy: only the indexer (`mkdb`); the query tool needs Berkeley DB.

## 3. Nano grid (kdnat9, one boot)

`nano_grid.sh`, `data/g1-nano*.jsonl`; 1584 points with the daemon (native,
kd, TCLock) and 528 kd points without it, 0 failed data checks, no kernel
complaint. With the daemon kd delegated in every profile (median 4 k to
6.6 M sections per point, no handbacks); without it, nothing.
`nano_ranges.py` (below), `data/nano-g1.md` (every point,
`bench/grid_table.py`), `data/nano-g1-plain.md`.

Ratios per point (median of 2 rounds), min-max within the worker range;
"plain" is kd without the daemon against the same boot's native:

| profile | kd/native 1-8 | 12-32 | 36-64 | kd/TCLock 1-8 | 12-32 | 36-64 | plain kd/native 1-8 | 12-32 | 36-64 | kd Mops/s at 32 / 64 | native | TCLock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| spin_c01 | 0.60-1.00 | 1.17-1.91 | 2.18-3.05 | 1.00-2.03 | 1.36-1.40 | 1.40-1.46 | 0.60-1.08 | 1.22-1.77 | 1.47-1.87 | 6.69 / 6.50 | 3.50 / 2.13 | 4.77 / 4.45 |
| spin_c08 | 0.56-1.00 | 0.93-1.56 | 1.78-2.40 | 1.00-1.52 | 1.55-1.60 | 1.60-1.65 | 0.57-1.00 | 0.89-1.45 | 1.16-1.41 | 5.18 / 5.13 | 3.32 / 2.14 | 3.26 / 3.10 |
| mutex_c01 | 0.94-1.13 | 0.94-0.97 | 1.14-1.67 | 0.99-1.97 | 1.05-1.27 | 1.04-1.14 | 0.99-1.18 | 1.09-1.17 | 1.13-1.45 | 3.84 / 3.69 | 4.10 / 2.22 | 3.67 / 3.53 |
| mutex_c08 | 1.00-1.14 | 1.10-1.15 | 1.24-1.59 | 1.00-1.73 | 1.53-1.58 | 1.49-1.53 | 1.00-1.10 | 1.01-1.09 | 1.01-1.39 | 3.71 / 3.58 | 3.36 / 2.32 | 2.43 / 2.41 |
| rwsem_c01_w1 | 1.00-2.15 | 2.30-2.92 | 3.02-4.20 | 1.00-1.06 | 0.75-1.10 | 0.81-0.99 | 1.00-2.15 | 2.26-2.90 | 3.21-4.33 | 10.58 / 10.26 | 4.56 / 2.45 | 14.14 / 12.65 |
| rwsem_c08_w1 | 1.00-1.51 | 1.92-2.22 | 2.92-3.98 | 1.00-1.22 | 1.00-1.17 | 1.10-1.21 | 1.00-1.51 | 1.88-2.20 | 2.85-3.74 | 9.85 / 9.52 | 4.44 / 2.39 | 9.88 / 8.67 |
| rwsem_c01_w20 | 1.00-3.39 | 2.18-2.24 | 3.07-5.53 | 1.00-1.37 | 0.94-1.08 | 1.17-1.25 | 1.00-3.19 | 2.26-2.40 | 3.06-5.65 | 7.01 / 6.80 | 3.13 / 1.31 | 7.46 / 5.82 |
| rwsem_c08_w20 | 1.00-2.18 | 2.28-2.37 | 2.96-5.04 | 0.93-1.21 | 0.99-1.09 | 1.25-1.30 | 1.00-1.93 | 1.87-1.90 | 2.40-4.04 | 6.05 / 5.85 | 2.55 / 1.24 | 6.13 / 4.68 |
| rwlock_c01_w1 | 1.00-1.14 | 1.32-2.13 | 2.64-3.83 | 1.00-1.13 | 1.02-1.24 | 0.97-1.03 | 1.00-1.14 | 1.31-2.11 | 2.32-3.33 | 14.12 / 13.43 | 6.63 / 3.51 | 13.82 / 13.87 |
| rwlock_c08_w1 | 0.96-1.00 | 1.06-2.24 | 2.49-3.59 | 1.00-1.13 | 0.97-1.02 | 0.94-0.97 | 0.96-1.00 | 1.05-2.20 | 2.45-3.53 | 8.85 / 8.71 | 3.95 / 2.42 | 9.10 / 9.22 |
| rwlock_c01_w20 | 1.00-1.37 | 1.63-2.90 | 3.63-4.48 | 1.00-1.50 | 1.23-1.25 | 1.21-1.30 | 1.00-1.34 | 1.63-2.85 | 2.95-3.34 | 6.22 / 6.09 | 2.15 / 1.36 | 5.04 / 5.02 |
| rwlock_c08_w20 | 0.88-1.53 | 1.89-3.30 | 4.17-5.09 | 0.93-1.17 | 1.08-1.11 | 1.09-1.12 | 0.85-1.35 | 1.66-2.92 | 2.72-3.05 | 4.90 / 4.78 | 1.49 / 0.94 | 4.40 / 4.33 |

- **Across nodes (36-64 workers) kd is ahead of native everywhere,** 1.14-5.53
  delegated and 1.01-5.65 plain: native falls by 31-58% from 32 to 64
  workers in every profile, kd by 1-5%.
- **Against TCLock** kd is ahead in spin (1.36-1.65), mutex (1.04-1.58)
  and the writer-heavy rw profiles (rwlock 20% writes 1.08-1.30, rwsem 20%
  writes 1.17-1.30 across nodes). TCLock is ahead in rwsem with 1% writes
  and 1 cache line (kd/TCLock 0.75-1.10 at 12-32, 0.81-0.99 at 36-64) and
  close in rwlock with 1% writes (0.94-1.24).
- **One node, few workers:** spin is behind native at 2-8 workers, c01
  0.60-0.95 and c08 0.56-0.77, lowest at 3 workers; c01 is ahead from 12
  workers and c08 from 16. Not analysed in this round. mutex c01 is at
  0.94-0.97 of native at 12-32 workers.

## 4. Application grid (native kdnat9, kd off and on kdall10)

`app_grid.sh`, `data/runs.txt` (one line per point with the kd counters
before and after), `data/app-g1.md` (every point, `app_summary.py`),
`data/app-g1.csv`, `app_ranges.py` (below). One run per point and mode;
287 points per mode; no kernel complaint in the three passes; the native
pass also counted 0 fatal signals (the counter was added after kd off and
on, section 6).

| benchmark | off/native 1-8 | 12-32 | 36-64 | on/native 1-8 | 12-32 | 36-64 | native / off / on at 32 | at 64 | delegated at 64 |
|---|---|---|---|---|---|---|---|---|---|
| wis lock1 | 0.47-0.97 | 1.29-3.67 | 2.37-3.75 | 0.47-0.98 | 1.26-3.75 | 2.30-3.64 | 2.49M / 9.14M / 9.36M | 1.54M / 5.77M / 5.61M | 0 |
| wis mmap1 | 0.97-1.01 | 0.98-1.01 | 1.14-1.78 | 1.00-1.25 | 1.23-1.28 | 1.61-2.18 | 297k / 299k / 380k | 177k / 315k / 374k | 11758576 |
| wis mmap2 | 0.98-1.04 | 0.96-0.98 | 1.20-1.71 | 0.97-1.19 | 1.07-1.13 | 1.31-1.79 | 354k / 344k / 382k | 211k / 351k / 366k | 11775657 |
| wis brk1 | 0.73-1.05 | 0.96-1.06 | 1.03-2.12 | 0.93-1.43 | 1.49-1.78 | 1.88-2.85 | 709k / 694k / 1.16M | 402k / 753k / 876k | 14054843 |
| wis page_fault1 | 0.74-0.93 | 0.72-0.98 | 0.97-1.01 | 0.79-0.96 | 0.81-1.05 | 0.99-1.07 | 2.80M / 2.74M / 2.93M | 4.13M / 4.16M / 4.31M | 40 |
| wis page_fault2 | 0.82-0.95 | 0.83-0.99 | 0.80-0.95 | 0.88-0.97 | 0.85-0.90 | 0.81-0.92 | 2.01M / 1.99M / 1.82M | 3.65M / 2.92M / 2.96M | 38 |
| wis page_fault3 | 0.81-0.98 | 0.66-0.93 | 0.96-0.97 | 0.83-1.00 | 0.71-0.98 | 0.98-1.00 | 12.63M / 11.76M / 12.33M | 12.19M / 11.77M / 11.98M | 35 |
| fxmark MWRM | 1.01-1.07 | 1.01-1.05 | 1.04-1.16 | 1.00-1.06 | 1.00-1.04 | 1.03-1.14 | 335k / 347k / 336k | 274k / 305k / 310k | 113 |
| fxmark MRDM | 1.00-1.30 | 1.23-4.23 | 2.74-4.30 | 0.93-1.21 | 1.18-3.98 | 2.95-3.84 | 1.17M / 4.97M / 4.66M | 736k / 3.16M / 2.74M | 0 |
| leveldb readrandom | 0.93-1.06 | 1.01-1.16 | 0.87-1.19 | 0.91-1.02 | 0.98-1.13 | 0.87-1.19 | 1.02M / 1.15M / 1.13M | 697k / 612k / 605k | 103 |
| metis wrmem | 0.97-1.03 | 0.98-1.00 | 0.98-1.19 | 0.96-1.04 | 0.95-1.01 | 0.99-1.18 | 7.73 / 7.85 / 7.67 | 6.34 / 6.17 / 6.19 | 288 |
| psearchy pedsort | 0.99-1.00 | 0.99-1.00 | 0.97-1.01 | 0.99-1.00 | 0.99-1.01 | 0.98-1.01 | 296 / 291 / 293 | 531 / 530 / 529 | 1242 |
| apache single | 1.03-1.15 | 0.97-1.26 | 0.73-0.91 | 1.01-1.14 | 1.28-1.37 | 1.28-1.41 | 33k / 32k / 45k | 31k / 23k / 44k | 439345 |
| apache default (once) | 1.13 | | | 0.58 | | | 143k / 162k / 83k | | 187539 |

Notes on the table:
- **Metis** is wall time (s) for the default input, ratios native/kd.
  **Psearchy** is jobs per hour over all cores. **Apache default** is one
  run per mode (section 6: the kd-on value belongs to the failure there).
- "delegated at 64": sections completed by a combiner in the 64-worker
  point of kd on; 0 means the workload's locks are not on the allow lists.

What the numbers say (one run per point, so a ratio within about 0.05 of 1
is not a result):

- **Large gains without delegation, where native collapses across nodes:**
  - FxMark MRDM (directory reads in a shared directory) 2.74-4.30 at 36-64 workers and 1.23-4.23 at 12-32.
  - will-it-scale `lock1` 2.37-3.75 at 36-64. Native peaks at 19.9 M ops/s with 8 threads and falls to 1.5 M at 64; kd stays between 5.8 and 9.4 M from 8 threads on. So kd is at 0.47 at 8 threads, native's peak, and ahead from 12.
  - mmap1, mmap2 and brk1 at 64 threads: 1.78, 1.66 and 1.87 without delegation, as in kdall-native-20261117-64cpu.
- **Delegation adds on the mmap lock:**
  - mmap1 1.61-2.18 at 36-64 (on), 1.23-1.28 at 12-32;
  - brk1 1.88-2.85 and 1.49-1.78;
  - Apache single process (one mm, every request maps and unmaps its file) 1.28-1.41 at 12-64 workers, against 0.73-1.26 without delegation.
- **Losses:**
  - page_fault1 and page_fault3 at 1-32 threads (0.66-0.98, worst page_fault3 at 12-32), at parity from 36. page_fault2 stays at 0.80-0.95 throughout.
  - Apache single process without delegation at 36-64 (0.73-0.91).
  - LevelDB `readrandom` at 64 threads (0.87, around 1.0 elsewhere).
  - These were not profiled in this round.
- **Small or no difference:** Metis, Psearchy, LevelDB below 64 threads, FxMark MWRM (1.00-1.16).

## 5. TCLock

Only in section 3. Its kernel form (TCLocks' `linux-5.14.16`) is a
different kernel version; booting it here would compare kernels, not
locks, and its scripts target its own 5.14 tree. The application rows
therefore compare kd with the same kernel's native locks only.

## 6. Failures found

1. **kd on: exiting httpd processes hang on their mmap lock (reproduced;
   fixed 2026-11-19, section 8).**
   - **Where it showed:** the reboot after the g1 kd-on pass hung (`../../../../serial-kdall10-hang-20261118.log` on 10.176.26.71, httpd threads "blocked by coredump"); then reproduced in `crash_check.sh on`, at the first cycle of Apache's default configuration.
   - **State** (`data/hang/`: stacks, counters, `diag_kd_mmdump.c` output in `mmdump.txt`):
     - 3-4 httpd worker processes, all threads in `do_exit` waiting for their mm's mmap lock in read mode;
     - each mm's count is `0x5` (writer bit and NEEDWAKE, no reader), while the holder of the queue mutex is a reader that had added its bias (`lock addq $0x100` before it slept);
     - so a reader bias was subtracted that was not that reader's own, and the writer bit is never cleared.
   - **Narrowed down** (`vdown_ab.sh`, `repro_variant.sh`, `drivers/repro_drive.sh`, `data/hang/repro-*.txt`, `g1-vdown.txt`):
     - `kd_vdown=0`: 8 of 8 cycles clean (150-157 k req/s);
     - `kd_vdown=1` (default): hang at the first cycle, also with `kd_xchg=0`, and also with only `__vm_munmap` allowed.
     - With only munmap delegated, every munmap section kept its downgrade and handed the read part back with a real downgrade (`vdown` 100 182, `vdown_hb` 100 164, 21 sections completed in the combiner). The defect is in that path, in the kept downgrade of a delegated rwsem section (`kd_exec_one()` in `kernel/kd_core.c`, LOCKS.md 5); the code was not changed here.
   - **Effect on the data:** Apache default in kd on (0.58, one run) ran with the defect: its stop hung that boot. The single-process Apache points did not hang: 22 cycles in the pass, 22 in `crash_check.sh`. mmap1, mmap2, brk1, page faults and `mm_stress` with delegated munmap did not hang either: their munmap read parts mostly complete in the combiner, or their processes do not exit while sections are handed back.
   - **Workaround:** `kd_vdown=0`.
2. **One segfault of `page_fault2_threads` in kd on** (14:19 in g1 on, glibc, a 16-bit counter increment at address `0xf70` during process teardown, after the measurement: every point has its value). Not reproduced: 90 runs of page_fault2, page_fault1 and mmap1 at 16-64 threads with the daemon (`wis_exit_check.sh`, `data/hang/g1-wisexit.txt`), and 60 runs each in native and kd off (`data/g1-*-crash.txt`), all without a fatal signal.
3. **A per-CPU lock byte left set by handbacks (fixed in the translator
   2026-11-19, section 8; found by the lkp-tests
   session, branch `lkp-macro`, its README section 7; checked here).**
   - **What:** a delegated section that takes memcg's per-CPU
     `obj_stock` local trylock on the executor and is handed back before
     the unlock leaves `acquired` set on the executor's CPU for the rest of
     the boot. The origin's unlock clears its own CPU's byte. Every later
     accounted slab allocation on those CPUs takes the slow path, for all
     tasks.
   - **Checked here** (`pcpu_check.sh`, `data/hang/g1-pcpu.txt`, the
     reading tool is that session's `tools/pcpu.py`): fresh kdall10 boot 0
     of 64 CPUs; after delegated mmap1 and mmap2 still 0; after delegated
     brk1 (1.06 M handbacks at translation misses) **57 of 64**; unchanged
     by page_fault1 and Apache afterwards; `memcg_stock` stays clean.
   - **Effect on this grid:** in the kd-on pass, everything after
     will-it-scale brk1 ran with the bytes set: page_fault1-3, FxMark,
     LevelDB, Metis, Psearchy and Apache. Their on/off ratios in the same
     boot (off ran first) are 0.99-1.04 at the median, except FxMark MRDM
     at 0.95 (0.87-1.07). MRDM allocates accounted dentries and inodes, so
     its kd-on column may be low by about 5%. Apache's on values include
     the effect.
   - **Effect on kdall-native-20261117-64cpu:** boots c4 and a4 ran kd on
     before kd off. Their off values agree with the clean off boots
     (c2/c6, a2/a6) within 0.94-1.06, with two exceptions: pf write at 32
     threads (c4 0.81, a noisy point) and locktorture rwsem (a4 0.92).
     The medians there are not affected.
4. **Setup:** the unpatched Metis binary died with SIGILL (`wrmem` with no cpufreq), fixed before the grid (section 2); the native and kd-off crash checks are clean (no fatal signal, no leftover httpd).

## 8. Fixes of failures 1 and 3 (2026-11-19)

Both are fixed in kdall13 (`7.0.0-38-kdall13 #18`, commits `a26a8578` and
`3a909d50`); every check below ran on a fresh boot of it unless named
otherwise. Data in `data/fix/`.

### 8.1 Failure 1: the mmap lock left write-held

- **Located** with release assertions in `kd_rwsem.c` (a write release or
  downgrade without the writer bit, a read release with it) on kdall11:
  the munmap origin's `up_read` from `vms_complete_munmap_vmas()` ran with
  count `0x109` (writer bit set). A temporary ring of `kd_exec_one()`
  decisions (kdall11d, not committed) showed for every failing task: a
  nested acquisition (the i_mmap rwsem in `unlink_file_vma_batch_final()`)
  ran on another combiner, the packet came back (`KD_WAIT_RESUMED`) and
  went on in generated code, and a later miss was then handled with that
  combiner's verdict, as a completed section: no kept downgrade, no
  suppressed offer (`data/fix/k11-dmesg-excerpt.txt`).
- **Fix:** the verdict counts only when the level ends on it
  (LOCKS.md 5, ARCHITECTURE.md 8).
- **Checks** (`repro_variant.sh`, now with `CYCLES` and `KERNEL`; Apache
  default configuration, only `__vm_munmap` delegated, `kd_vdown=1`,
  `kd_xchg=1`):

| kernel | cycles | result |
|---|---:|---|
| kdall11 (assertions) | 4 | hung (`repro-k11munmap.txt`) |
| kdall11d (assertions, decision ring) | 5 | hung (`repro-k11dmunmap.txt`) |
| kdall11e (fix, ring, old translator) | 20 | clean, 0 assertions (`repro-k11efix.txt`) |
| kdall13 (both fixes) | 20 | clean, 0 assertions, 12 165 nested delegations (`repro-k13munmap.txt`) |

### 8.2 Failure 3: per-CPU lock bytes

- **Fix:** per-CPU regions in the translator (TRANSLATOR.md 3a). Counters
  `hb_region` (an exit left inside a walked region, taken with the
  section's preempt count or IRQ-off raised; an upper bound, an inner lock
  held counts too) and `done_in_region`.
- **Policies tried** (`pcpu_check.sh`, delegated will-it-scale at 64
  threads 10 s, then Apache single process; bytes of `obj_stock` /
  `memcg_stock` after the last workload):

| run | policy | mmap1 delegated / handback | brk1 delegated (that point) | hb_region | bytes |
|---|---|---|---|---:|---|
| kdall10 (`data/hang/g1-pcpu.txt`) | none | 11 721 926 / 31 | 2 398 479, 1 056 779 misses | - | 57 / 0 |
| `k12-pcpu.txt` | every exit a frontier, kernel waits nested in regions | 0 / 6 871 | 451 362 | - | 0 / 0 |
| `k13-pcpu.txt` | exits to depth 2, 60 000-instruction budget | 0 / 2 113 | 265 | 668 (region starts, counter since corrected) | 0 / 0 |
| `k13b-pcpu.txt` | depth 0, budget 60 000 | 0 / 4 565 | 1 928 378, 2.7 M misses (budget) | 153 | 0 / 0 |
| `k13c-pcpu.txt` | depth 0, budget 250 000 | 10 879 599 / 344 509 | 5 535 327 | 15 033 | 0 / **7** |
| `k13d-pcpu.txt` | as committed (reads found during walks also walked) | 11 293 649 / 46 | 14 086 420 / 68 | 99 | 0 / 0 |

  k13c is the one that leaked: identity reads that a walk decoded were not
  walked themselves, so `refill_stock()`'s region missed into
  `drain_stock()`; `hb_region` showed it. The committed loop repeats until
  no new read turns up.
- **In-boot A/B** (`fix_ab.sh k13v2`, `data/fix/k13v2-fixab.txt`,
  `fixab_summary.py`): kd off, then this translator, then the previous one
  (`b6041b6f`) last; each daemon mode starts from no images
  (`drop_sites.py`; a daemon that exits leaves its images loaded) and
  warms up until a pass adds fewer than 1000 misses. Mean of 2 rounds, ops
  per second:

| benchmark | threads | off | new | old | new/off | old/off | new/old |
|---|---:|---:|---:|---:|---:|---:|---:|
| mmap1 | 1 | 501290 | 498097 | 473651 | 0.99 | 0.94 | 1.05 |
| mmap1 | 8 | 314278 | 390136 | 378886 | 1.24 | 1.21 | 1.03 |
| mmap1 | 32 | 315056 | 392146 | 381344 | 1.24 | 1.21 | 1.03 |
| mmap1 | 64 | 325545 | 371582 | 359399 | 1.14 | 1.10 | 1.03 |
| mmap2 | 1 | 417773 | 408826 | 403783 | 0.98 | 0.97 | 1.01 |
| mmap2 | 8 | 300660 | 350016 | 383992 | 1.16 | 1.28 | 0.91 |
| mmap2 | 32 | 361546 | 386025 | 380936 | 1.07 | 1.05 | 1.01 |
| mmap2 | 64 | 348870 | 331226 | 341183 | 0.95 | 0.98 | 0.97 |
| brk1 | 1 | 1050308 | 1028617 | 927628 | 0.98 | 0.88 | 1.11 |
| brk1 | 8 | 770924 | 1017129 | 877506 | 1.32 | 1.14 | 1.16 |
| brk1 | 32 | 779614 | 1145152 | 1001758 | 1.47 | 1.28 | 1.14 |
| brk1 | 64 | 812986 | 1015228 | 818172 | 1.25 | 1.01 | 1.24 |
| page_fault1 | 1 | 641142 | 637596 | 628866 | 0.99 | 0.98 | 1.01 |
| page_fault1 | 8 | 2153946 | 2360815 | 2381829 | 1.10 | 1.11 | 0.99 |
| page_fault1 | 32 | 3002054 | 2983251 | 2922690 | 0.99 | 0.97 | 1.02 |
| page_fault1 | 64 | 4465746 | 4464916 | 4303556 | 1.00 | 0.96 | 1.04 |

| mode | delegated | handback | hb_miss | hb_frontier | hb_region | done_in_region | bytes after (obj_stock, memcg_stock) |
|---|---:|---:|---:|---:|---:|---:|---|
| off | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 |
| new | 242 511 697 | 975 | 2 | 973 | 684 | 0 | 0 / 0 |
| old | 228 471 705 | 1 455 | 449 | 1 006 | 0 | 0 | 46 / 6 |

  - The old translator set 46 obj_stock and 5 memcg_stock bytes already in
    its warm-up, so its measured points ran with those CPUs on the slow
    accounted-allocation path: new/old mixes the translation change with
    the damage the old one does. brk1 gains most (1.14-1.24), mmap1 1.03,
    mmap2 0.91 at 8 threads and 0.97-1.01 elsewhere; page_fault1 is not
    delegated. One boot, 2 rounds: at mmap2 8 threads the old rounds are
    369 k and 399 k, the new ones 353 k and 347 k; the gap is about the
    old round-to-round spread, so a loss there is not established either
    way.
  - `hb_region` 684 in the new mode with no byte set: the counter's upper
    bound includes exits taken with an inner lock held.
  - A first A/B (`k13-fixab-v1.txt`) did not drop images between modes and
    measured the new mode before learning converged; it is kept for the
    old translator's damage in one boot (obj_stock 32 of 64), not for the
    rates.
- **Correctness on kdall13** (`kdall_check.sh` without the era step,
  `data/fix/k13.out`): locktorture ww_mutex, mutex and rwsem 2 runs each,
  all SUCCESS; `run_corr.py` plain and delegated 442 points, 0 failed, 0
  kernel complaints; test-ww_mutex passes (the `stress_inorder_work -35`
  line is in every earlier run too); `mm_stress` 16/32/64 threads ok; 0
  complaints in the kernel log.
- **Limits:** far exits are not proven unreachable with a region open
  (TRANSLATOR.md 3a); report `hb_region` and the bytes with delegated runs.
  The grid of sections 3-4 was not rerun on kdall13.

## 7. Files

| file | what |
|---|---|
| `build_apps.sh`, `prep_text.sh` | building the benchmarks in the guest; the Psearchy input |
| `app_grid.sh` | the application grid, one mode per pass; `app_summary.py`, `app_ranges.py` |
| `nano_grid.sh`, `nat_boot.sh` | the nano grid on a kdnat kernel with TCLock; the kdnat boot; `nano_ranges.py` |
| `crash_check.sh`, `vdown_ab.sh`, `repro_variant.sh`, `wis_exit_check.sh`, `drivers/` | section 6 |
| `diag_kd_mmdump.c`, `dstate.sh`, `hangdump.sh` | diagnostics: the mmap lock state of named processes (module, never left loaded), D-state stacks without reading command lines |
| `data/runs.txt`, `data/app-g1.*`, `data/nano-g1*` | results |
| `data/hang/` | the hang: stacks, counters, lock states, reproductions |
| `pcpu_check.sh`, `fix_ab.sh`, `drop_sites.py`, `fixab_summary.py`, `data/fix/` | section 8 |

