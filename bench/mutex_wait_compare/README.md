# Mutex spin and blocking comparison

The KD provider retains the existing spin policy and adds an ordinary blocking
mutex policy. Select `mutex_blocking=1` when loading `kdlock_km.ko`; select `0`
for the spin baseline. `mutex_spin_limit` bounds the number of PAUSE iterations
before sleeping; zero requests immediate sleeping. Both parameters are immutable
for that provider lifetime. The public mutex API and caller ABI are unchanged.

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

Individual runners accept `--mutex-wait-mode spin|blocking` and
`--mutex-spin-limit N`. KD records contain the actual module policy and
`mutex_wait_before/after/delta`: result schedule calls, successful result wakes,
and gate wait calls. A call count alone does not prove a task descheduled; the
[scheduler probe](../../tests/kernel/mutex/run_wait_selftest.py) separately
observes sleeping tasks and same-CPU progress.

Create `STOP` in the output directory to stop between groups. A failure preserves
the group and halts further work; only a fully drained NO_JIT exclusion permits
later groups. Never pool interrupted or tuning candidates into final scores.
Raw evidence belongs outside the checkout and reports under
`bench/results/10.176.26.71/bench/mutex_wait/`.
