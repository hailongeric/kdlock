# kdlock Open Tasks

Last updated: 2026-09-04

Completed implementation history is available in Git and is intentionally not
duplicated here. Current architecture is documented in `DESIGN.md`; the latest
mode 0/1/3/4 JIT execution results are in `VALIDATION.md`.

## Current Baseline

- Spinlock JIT delegation supports contention, nested A -> B -> C execution,
  out-of-order unlock, independent inner queues, and transactional abort/retry.
- Mutex JIT delegation is opt-in through `mutex_jit=1`. Repeated mode 3 and
  nested mode 4 A/B proxy execution pass the recovery-only acceptance suite.
- The default integration suite keeps `mutex_jit=0` for modes 3-5 and validates
  only the mutex queue, promotion, handoff, and fallback protocol.
- No mode 0/1/3/4 acceptance failure is currently known. Any code change to the
  translation, frame, queue, or resume paths must rerun the acceptance contract
  in `VALIDATION.md`.

## Correctness And Coverage

- [ ] Expand mode 5 API-in-mutex-JIT coverage beyond the current bounded
      recovery test, including repeated execution and exact resume accounting.
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

## Features

- [ ] Enable and validate `NUMA_AWARE` combining on a multi-socket guest.
- [ ] Implement the NUMA-local mutex queue path; its code is currently disabled
      behind `NUMA_AWARE`.
- [ ] Expose spin and mutex batch sizes as module parameters.
- [ ] Add rwsem delegation using TCLocks' rwsem protocol as the reference.
- [ ] Add structured delegation statistics or tracepoints for perf/ftrace rather
      than relying only on module-exit `dmesg` summaries.
- [ ] Add an automated benchmark matrix over all ten workload modes, thread
      counts, and contention levels.

## Performance And Portability

- [ ] Measure adaptive batch sizing against the fixed batch limits of 1024.
- [ ] Quantify mode 3/4 delegation benefit and overhead against native mutexes;
      the current tests are correctness tests, not performance evidence.
- [ ] Support architectures beyond x86-64. The wrapper, register layout, and
      translated instruction model are currently architecture-specific.
