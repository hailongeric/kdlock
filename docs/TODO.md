# kdlock Open Tasks

Last updated: 2026-09-04

Completed implementation history is available in Git and is intentionally not
duplicated here. Current architecture is documented in `DESIGN.md`; the latest
mode 0/1/2/3/4/5 JIT execution results are in `VALIDATION.md`.

## Current Baseline

- Spinlock JIT delegation supports contention, nested A -> B -> C execution,
  out-of-order unlock, independent inner queues, and transactional abort/retry.
- Mode 2 uses a distinct allowlisted hostcall exit for `ktime_get`, executes the
  typed native service while retaining the outer spinlock, and resumes the same
  JIT artifact after CALL. Artifact and runtime counters prove this path.
- Mutex JIT delegation is opt-in through `mutex_jit=1`. Repeated mode 3 and
  nested mode 4 A/B proxy execution pass the recovery-only acceptance suite.
  Mode 5 repeatedly executes the same allowlisted hostcall protocol under mutex
  contention with exact hostcall, JIT completion, and waiter resume accounting.
- The default integration suite keeps `mutex_jit=0` for modes 3-5 and validates
  only the mutex queue, promotion, handoff, and fallback protocol.
- No mode 0/1/2/3/4/5 acceptance failure is currently known. Any code change to the
  translation, frame, queue, or resume paths must rerun the acceptance contract
  in `VALIDATION.md`.

## Correctness And Coverage

- [ ] Implement effective translated-memory address validation, preserve live
      EFLAGS around it, and assign `seg_error` a deterministic exit reason.
- [ ] Define and test any required cross-exit EFLAGS, FS/GS, and SIMD/FPU ABI
      before translating critical sections that depend on those states.
- [ ] Initialize `Stack_INST_CNT` from R11 or remove `args[1]` from the wrapper
      output contract; it is currently an undefined reserved value.
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

- [ ] Add a fixed-signature, bounded logging hostcall backed by a per-CPU buffer;
      do not expose raw variadic `printk` or arbitrary format strings.
- [ ] Define exactly-once behavior for side-effecting hostcalls before adding
      any service that cannot safely be repeated after a later JIT abort.
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

- [ ] Measure hostcall exit/resume overhead and establish when native service
      execution is cheaper than translating a callee into the sandbox.
- [ ] Measure adaptive batch sizing against the fixed batch limits of 1024.
- [ ] Quantify mode 3/4/5 delegation benefit and overhead against native mutexes;
      the current tests are correctness tests, not performance evidence.
- [ ] Support architectures beyond x86-64. The wrapper, register layout, and
      translated instruction model are currently architecture-specific.
