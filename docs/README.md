# kdlock (clean rewrite): documentation

kdlock lets the holder of a contended kernel lock run the critical sections of
the waiters queued behind it, from a relocated copy of their code produced by a
userspace translator, so the protected data stays in one CPU's cache. Anything
the copy cannot run correctly goes back to its owner at the exact next
instruction. This directory is a from-scratch implementation of that idea for
Linux 7 on x86_64, covering spinlock, rwlock, mutex and rwsem.

**Status:** the kernel with kdlock built in boots in the `kdclaude` VM; all
four families, two-level nesting and handback pass the data checks with and
without delegation, and module unload with live images is handled. Twelve
measured rounds are in `../bench/results/kdclaude/`; the full worker grid and
the will-it-scale runs behind [MMAP_LOCKS.md](MMAP_LOCKS.md) are round 10,
and rounds 11 and 12 are that grid with the reader-writer families served one
NUMA node at a time (ARCHITECTURE 7b). See
[BUILD_AND_TEST.md](BUILD_AND_TEST.md) and [PERF_PLAN.md](PERF_PLAN.md).

| Read this | For |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | mechanism end to end: objects, wait, session, executor, handback, context transfer, NUMA order, nesting, images, invariants, limits |
| [LOCKS.md](LOCKS.md) | per-family protocol, API, semantics, tunables, the clobber entries (`kd_*_cl()`) |
| [TRANSLATOR.md](TRANSLATOR.md) | what the userspace translator copies and rewrites, exits, learning loop |
| [INTERFACES.md](INTERFACES.md) | `/dev/kdlock`, debugfs counters, kernel parameters, benchmark device |
| [KERNEL_INTEGRATION.md](KERNEL_INTEGRATION.md) | putting kdlock into a kernel tree; configuration; what is and is not replaced |
| [BUILD_AND_TEST.md](BUILD_AND_TEST.md) | the build VM, checks that were done, what is missing |
| [NATIVE_COMPARISON.md](NATIVE_COMPARISON.md) | kdlock against the native Linux locks path by path, with pseudocode and the register/cache-line accounting |
| [MMAP_LOCKS.md](MMAP_LOCKS.md) | every lock inside the mmap write section, which of them kdlock can own, and what the will-it-scale counters say about each |
| [DIFFERENCES.md](DIFFERENCES.md) | where goals or effects differ from the earlier kdlock documents and `AGENTS.md`, with priorities |
| [PERF_PLAN.md](PERF_PLAN.md) | what stands between this state and defensible nano/micro numbers, split into tasks |

Source layout (relative to the repository root):

| Path | Content |
| --- | --- |
| `include/kdlock/` | lock objects (`kd_types.h`), API (`kd_api.h`), user interface (`kd_uapi.h`) |
| `kernel/` | `kd_entry.S` (stubs, resume, jit enter/exit), `kd_core.c` (wait, session, executor), `kd_{spinlock,rwlock,mutex,rwsem}.c`, `kd_era.c` (rw families across NUMA nodes), `kd_image.c` (sites, images, events), `kd_dev.c`, `Makefile`, `Kconfig` |
| `jit/` | `kd_daemon.py`, `kdjit/translator.py`, `kdjit/kernel.py` |
| `integration/` | `apply_to_tree.sh`, `kd_linux_map.h` (API mapping reference), notes |
| `bench/` | `kd_bench.c` (nano workloads), the runners (`run_grid.py` worker grid, `run_place.py` CPU placements and parameter sets in one boot, `run_oversub.py` more threads than CPUs, `run_mmap1.py` will-it-scale, with `--events` for `mmap_lock` counts), `wis/`, `results/` |
| `tclock_backend/` | the original TCLocks locks, the benchmark's third backend |

Wording rules (from the project `AGENTS.md`): prose and comments in English;
neutral terms (continuation, handback, local execution) in new names and text.
