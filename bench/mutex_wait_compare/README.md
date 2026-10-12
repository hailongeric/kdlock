# Mutex spin and blocking comparison

The KD provider retains the existing spin policy and adds an ordinary blocking
mutex policy. Select `mutex_blocking=1` when loading `kdlock_km.ko`; select `0`
for the spin baseline. `mutex_spin_limit` bounds the number of PAUSE iterations
before sleeping; zero requests immediate sleeping. Both parameters are immutable
for that provider lifetime. The public mutex API and caller ABI are unchanged.
Sleeping result waiters recheck after one timer tick if no wake has arrived;
ordinary wakes can end the sleep sooner. This covers a later critical section
that depends on an earlier completed caller before flushing buffered wakes.

The [implementation guide](../../docs/design/mutex_implementation.md) describes
result/gate wakeup, task lifetime and the blocking image's GS restriction.
This implements ordinary uninterruptible mutex acquisition. It does not add
interruptible/killable APIs, a sleeping rwlock, or a general mmap/rwsem port.

Run only in the recovery VM after source synchronization, kernel/placement
verification and a fresh confirmed snapshot:

```sh
export KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=YOUR_VERIFIED_SNAPSHOT
python3 bench/mutex_wait_compare/run.py \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-wait-RUN \
  --mutex-spin-limit 4096
```

The default grid is 1, 8, 16, 32, 48 and 60 distinct workers, with collector CPU
63 on the regular 64-vCPU VM. Every configuration has three rounds, a two-second
measurement and a best valid 300 ms peak after 300 ms settling. The inherited
runners check warmup, all workers' progress, business results, source/JIT/binary
identity and exact drain. Full-run worker CPU time is retained separately from
throughput; it is not acquisition latency.

The matrix covers every payload in the maintained complete-matrix driver:
spin/mutex c01/c08/c16 and RCUHT; rwlock c01/c02/c04/c08/c16 and RCUHT, each at
1%/20% writes. It also covers all accepted real API configurations: OFD tail
queries with 16/128 ranges, F_SETFD/F_GETFD with 16/512 descriptor spacing,
FIONREAD with 16/128 pipe buffers, F_GETPIPE_SZ, lseek SET/END, and UTS
hostname/domain with 20% writes. Xattr's existing admission refusal is documented
separately; it is not an accepted performance benchmark. FxMark and mmap are
not part of the maintained runnable suite.

Each workload compares Native, TCLock, KD spin and KD blocking. Real APIs also
retain the stock Linux control. Spin/rwlock protocols do not use the mutex wait
policy; their two KD runs are regression controls, not two new spin/rwlock
implementations. The matrix contains 2,430 sessions at the default grid.

For the complete 22-point grid (1–8, then 12–64 in steps of four), use the
verified temporary [66-vCPU layout](../../tools/vm/README.md#complete-164-worker-comparison):

```sh
python3 bench/mutex_wait_compare/run.py --full-grid --paired-policies \
  --cpus $(seq 0 31) $(seq 33 64) --collector-cpu 65 \
  --output /root/kdlock-evidence/10.176.26.71/bench/full-wait-NEW
```

This reruns all 31 configurations, including the larger cacheline controls, for
8,910 measured sessions. Spin/mutex payloads and real APIs pair KD policies
within each round; native rwlock payloads retain separate policy groups as
regression controls. No baseline is duplicated. Worker prefixes use 32 physical
cores on each NUMA node. At 64 workers, collector 65 and worker 64 share host
core 63 with QEMU service threads; this is part of the measurement environment.
Archive the complete evidence before restoring the normal 64-vCPU boot.

Individual runners accept `--mutex-wait-mode spin|blocking` and
`--mutex-spin-limit N`. KD records contain the actual module policy and
`mutex_wait_before/after/delta`: result schedule calls, successful result wakes,
and gate wait calls. A call count alone does not prove a task descheduled; the
[scheduler probe](../../tests/kernel/mutex/run_wait_selftest.py) separately
observes sleeping tasks and same-CPU progress.

The direct spin/mutex and real API runners also accept `both`, which places the two KD
policies next to each other and reverses their order on alternating rounds.
For example, a separate c01/c16 mutex diagnostic is:

```sh
python3 bench/tclock_compare/run_mutex.py \
  --backends kdlock --workload cacheline --cachelines 1 16 \
  --threads 16 60 --collector-cpu 63 --repeats 3 --duration-ms 2000 \
  --mutex-wait-mode both --mutex-spin-limit 4096 \
  --output /root/kdlock-evidence/10.176.26.71/bench/mutex-paired-NEW
```

Create `STOP` in the output directory to stop between groups. A failure preserves
the group and halts further work; only a fully drained NO_JIT exclusion permits
later groups. Never pool interrupted or tuning candidates into final scores.
Raw evidence belongs outside the checkout and reports under
`bench/results/10.176.26.71/bench/mutex_wait/`.

After measurement, export a completed default or full grid into a separate directory:

```sh
python3 bench/mutex_wait_compare/export.py --input RAW_RUN --output NEW_REPORT --plots
python3 bench/mutex_wait_compare/test_export.py
python3 bench/mutex_wait_compare/test_plan.py
```

The exporter verifies saved source/binary/JIT hashes and recorded module policy,
recomputes peaks from raw per-worker progress, and retains all rounds, CPU costs,
wait observations and execution classifications. `statistics-by-execution.csv`
keeps NO_JIT controls separate. `TABLES.md` shows every backend's whole-run and
best peak throughput; the statistics export includes min/median/max/spread.
Matplotlib is needed only for plots.
Optional `--pilots BENCH_PARENT`, `--paired RUN...` and `--superseded MATRIX...`
audit retained tuning, alternating-policy diagnostics and explicitly stopped
earlier versions into separate exports. They never fill missing final samples.
The final matrix must contain all 2,430 or 8,910 planned records, with each executed
session drained; any required-JIT exclusion remains unscored.
The exporter checks every subject/count/backend/round, worker CPU prefix and
paired policy order. Plain 2/3-worker direct cases may be NO_JIT controls, as
specified by the runner; contended mutex cases at four or more workers still
require returned JIT bodies.
The [2026-10-12 report](../results/10.176.26.71/bench/mutex_wait/20261012/README.md)
records the implementation, workload/lock contracts, validation and comparison.
