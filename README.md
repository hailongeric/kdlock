# kdlock

kdlock is an experimental lock library for x86_64 Linux kernel code. When several
threads need the same lock, one thread can hold it and run critical sections for
waiting threads. That thread is the **combiner**. A background daemon translates
the critical-section machine code; the combiner runs the generated JIT code.

KD provides three kinds of lock:

- **Spinlock:** uses KD's own four-byte lock object.
- **Mutex:** keeps the original Linux mutex, including its real owner, and adds
  a queue for delegated work. Waiters use bounded polling followed by blocking.
- **Read-write lock:** lets readers run concurrently on their own CPUs. Writers
  can run locally or delegate through the spin JIT engine.

The repository also includes TCLock ports and Linux Native workloads so all three
implementations can be compared. Callers choose an API explicitly; loading KD does
not redirect ordinary Linux lock calls. Builds require the recorded `kdclobber2`
guest-kernel interfaces.

Use the [project guide](docs/PROJECT_GUIDE.md) to build and run in the verified
guest. [Performance status](docs/PERFORMANCE.md) summarizes measured outcomes,
and the [results index](bench/results/README.md) retains source-specific evidence.
The [blocking-mutex verification](bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json)
records the current policy change and its targeted checks.

## Documentation

| Start here | Content |
| --- | --- |
| [Project guide](docs/PROJECT_GUIDE.md) | Current state, reading order and guest setup |
| [Nine lock protocols](docs/design/lock_protocols.md) | How KD, TCLock and Native acquire locks, run waiting work and release resources |
| [Spin implementation](docs/design/spin_implementation.md) | Spin source paths, objects, cachelines, queues, prefetch and stack/packet flow |
| [Mutex implementation](docs/design/mutex_implementation.md) | How mutex acquisition, delegation, sleeping and owner acknowledgements work |
| [Read-write lock](docs/design/rwlock_implementation.md) | How to use the rwlock and how it coordinates readers and writers |
| [KD design](docs/DESIGN.md) | Execution model, glossary and supported scope |
| [KD ownership](docs/design/locking.md) / [frames](docs/design/frames.md) | Which task owns each lock and when request memory can be reused |
| [JIT execution](docs/JIT_EXECUTION.md) / [register ABI](docs/JIT_REGISTER_ABI.md) | How code is accepted, translated, executed and returned to the caller |
| [Code map](docs/CODE_MAP.md) | Source and documentation responsibilities |
| [Operations](docs/AGENTS.md) | Where to build and test, how to shut down safely, and VM recovery |
| [Known limitations](docs/TODO.md) / [performance status](docs/PERFORMANCE.md) | Known problems, measured performance and work left for later |
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
