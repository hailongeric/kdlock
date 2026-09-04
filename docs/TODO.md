# kdlock Open Tasks

Last updated: 2026-09-05

This file tracks unfinished work only. Completed behavior belongs in
`DESIGN.md`, the current register contract belongs in `JIT_REGISTER_ABI.md`,
and the latest mode 0/1/2/3/4/5/10/11 execution evidence belongs in
`VALIDATION.md`.

## Correctness And Coverage

- [ ] Implement effective translated-memory address validation and preserve live
      EFLAGS around it. Segment errors now have a deterministic exit reason, but
      the general address guard is still disabled.
- [ ] Define and test any required cross-exit EFLAGS and SIMD/FPU ABI before
      translating critical sections that depend on those states. Kernel GS
      memory access is implemented through explicit lowering, not hardware
      segment-state restoration; FS remains deliberately unsupported.
- [ ] Add kernel integration pressure tests for translation-table and executable
      block-pool exhaustion; these are currently covered only by unit-level
      bounded lookup tests.
- [ ] Add shadow mutex table saturation and reuse tests so the fixed 1024-entry
      limit has explicit runtime coverage.
- [ ] Evaluate waitqueue-based mutex waiter parking. The current wait loops may
      call `schedule()` while migration-pinned, but there is no true parked
      waiter/wakeup protocol.
- [ ] Add a recovery test that injects nested mutex failure after B acquisition
      and proves reverse-order cleanup without duplicate A execution.
- [ ] Decide whether to wire a scheduler/wakeup frontend to the retained
      low-level `kd_exe_on_call()` futex compatibility entry or remove that API.
      No in-tree path currently submits delegated futex waiters to it.

## Features

- [ ] Add a fixed-signature, bounded logging hostcall backed by a per-CPU buffer;
      do not expose raw variadic `printk` or arbitrary format strings.
- [ ] Define exactly-once behavior for side-effecting hostcalls before adding
      any service that cannot safely be repeated after a later JIT abort.
- [ ] Enable and validate `NUMA_AWARE` combining on a multi-socket guest.
- [ ] Implement a NUMA-local mutex queue path. Only the spinlock source retains
      dormant branches behind `NUMA_AWARE`.
- [ ] Expose spin and mutex batch sizes as module parameters.
- [ ] Add rwsem delegation using TCLocks' rwsem protocol as the reference.
- [ ] Add structured delegation statistics or tracepoints for perf/ftrace rather
      than relying only on module-exit `dmesg` summaries.
- [ ] Add an automated benchmark matrix over all twelve workload modes, thread
      counts, and contention levels.

## Performance And Portability

- [ ] Measure hostcall exit/resume overhead and establish when native service
      execution is cheaper than translating a callee into the sandbox.
- [ ] Measure adaptive batch sizing against the fixed batch limits of 1024.
- [ ] Quantify mode 3/4/5 delegation benefit and overhead against native mutexes;
      the current tests are correctness tests, not performance evidence.
