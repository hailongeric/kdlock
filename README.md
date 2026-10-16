# kdlock

The [fresh legacy c01/pipebytes comparison](bench/results/10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md)
covers 1–8 workers by one and 12–60 by four, with all 378 sessions accepted.
It uses the recovered legacy provider and the documented common 64-round
post-unlock work for c01. Source and results are in `/tmp/kdlock-mutex-legacy-grid`
on `bench/legacy-mutex-c01-pipebytes` at commit `74676c3`.

The adaptive mutex experiment was rejected. The [recovered legacy baseline](bench/results/10.176.26.71/bench/comparison/mutex-legacy-recovery-20261016T113518Z/README.md)
is committed as `6ecdd0a` on `recovery/mutex-legacy-5m330` in
`/tmp/kdlock-mutex-legacy-5m330`. It reproduces the 60-worker pipebytes result at
5.367 Mops/s. This primary checkout retains the experimental source and the
35 pre-existing edits; use the recovered worktree for legacy development.

kdlock is an experimental lock library for x86_64 Linux kernel code. When several
threads need the same lock, one thread can hold it and run critical sections for
waiting threads. That thread is the **combiner**. A background daemon translates
the critical-section machine code; the combiner runs the generated JIT code.

KD provides three kinds of lock:

- **Spinlock:** uses KD's own four-byte lock object.
- **Mutex:** the experimental 128-byte `struct kd_mutex` contains its owner, spin
  queue and waiter list, using ported optimistic spinning and sleeping. Its protocol
  makes no Linux mutex calls on that object.
- **Read-write lock:** lets readers run concurrently on their own CPUs. Writers
  can run locally or delegate through the spin JIT engine.

The repository also includes TCLock ports and Linux Native workloads so all three
implementations can be compared. Callers choose an API explicitly; loading KD does
not redirect ordinary Linux lock calls. Builds require the recorded `kdclobber2`
guest-kernel interfaces.

Use the [project guide](docs/PROJECT_GUIDE.md) to build and run in the verified
guest. [Performance status](docs/PERFORMANCE.md) summarizes measured outcomes,
and the [results index](bench/results/README.md) retains source-specific evidence.
The [earlier expanded mutex comparison](bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
covers all five cacheline payloads, RCUHT and the private pipe/file API adapter
at 1–60 workers. [Performance status](docs/PERFORMANCE.md) keeps these results
separate from the accepted c01/post64 profile at 1–8 workers and earlier studies.
The [current protocol flowcharts](docs/design/mutex_implementation.md#owned-abi4-acquisition-and-release-flow)
show local acquisition, delegation and owner acknowledgements.
Current owned-mutex code also supports immutable image versions and opt-in
origin-readiness/NUMA policies. The [policy comparison](bench/tclock_compare/README.md#owned-origin-and-numa-comparison)
uses fresh controls; earlier acceptance applies to its recorded implementation.

## Documentation

| Start here | Content |
| --- | --- |
| [Project guide](docs/PROJECT_GUIDE.md) | Current state, reading order and guest setup |
| [Lock protocols](docs/design/lock_protocols.md) | How KD, TCLock and Native acquire locks, run waiting work and release resources |
| [Spin implementation](docs/design/spin_implementation.md) | Spin source paths, objects, cachelines, queues, prefetch and stack/packet flow |
| [Mutex implementation](docs/design/mutex_implementation.md) | How mutex acquisition, delegation, sleeping and owner acknowledgements work |
| [Read-write lock](docs/design/rwlock_implementation.md) | How to use the rwlock and how it coordinates readers and writers |
| [KD design](docs/DESIGN.md) | Execution model, glossary and supported scope |
| [KD ownership](docs/design/locking.md) / [frames](docs/design/frames.md) | Which task owns each lock and when request memory can be reused |
| [JIT execution](docs/JIT_EXECUTION.md) / [register ABI](docs/JIT_REGISTER_ABI.md) | How code is accepted, translated, executed and returned to the caller |
| [Code map](docs/CODE_MAP.md) | Source and documentation responsibilities |
| [Operations](docs/AGENTS.md) | Where to build and test, how to shut down safely, and VM recovery |
| [Known limitations](docs/TODO.md) / [performance status](docs/PERFORMANCE.md) | Known problems, measured performance and work left for later |
| [Benchmark workloads](docs/BENCHMARK_WORKLOADS.md) | Shared objects, protected operations and the meaning of cacheline, write-mix and real API labels |
| [Real kernel API benchmarks](bench/real_api/README.md) | Spinlock, mutex and bounded reader/writer syscall workloads; results, kernel-lock mapping and TCLocks paper context |
| [Validation and cleanup](docs/VALIDATION.md) | Completed checks, evidence retention and closeout scope |

## Repository

| Directory | Responsibility |
| --- | --- |
| [kernel_module](kernel_module/README.md) | KD spin/mutex/rwlock provider and shared execution engine |
| [include](include/README.md) | Shared ABI, direct API headers and wrapper assembly |
| [disassem](disassem/README.md) | Decode, admission, register lowering and code generation |
| [daemon](daemon/README.md) | Translation requests and code publication |
| [tclock_backend](tclock_backend/README.md) | TCLock ports, compatibility contexts and upstream provenance |
| [workload_modules](workload_modules/README.md) | Spin, mutex and rwlock kernel payloads and rwlock correctness workload |
| [bench](bench/README.md) | Clients, measurement instructions and performance evidence |
| [tests](tests/README.md) | Targeted verification entry points and evidence |
| [kernel_baseline](kernel_baseline/README.md) | Captured guest kernel configuration, interfaces and identity |
| [kernel_experiments](kernel_experiments/README.md) | Separately authorized historical kernel experiments |

Edit source on the host; build and run tests in the recovery guest, following
[operations](docs/AGENTS.md). Each directory guide contains its own commands.
This project targets x86_64 only. Its JIT checks are not a security sandbox; read
[admission limits](docs/design/admission.md), [resource lifetimes](docs/design/lifetimes.md)
and [known limitations](docs/TODO.md#delivery-scope) before using it.
