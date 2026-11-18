# Development rules

## What this repository is

kdlock lets the holder of a contended kernel lock (the combiner) run the
critical sections of the waiters queued behind it, so the protected data
stays in one CPU's cache. The combiner does not run the waiters' original
code but a relocated copy of it, built by a userspace translator. In the
copy, the accesses to task identity (`current`, the stack canary, the top of
stack) read the waiter's values. Anything the copy cannot run correctly ends
it, and the waiter continues natively from exactly that instruction
(handback). Delegation is therefore always optional, and a lock waits as
the native one does (plain mode) until its queue is deep.

| Path | Content |
| --- | --- |
| `include/kdlock/`, `kernel/` | the lock families (spinlock, rwlock, mutex, rwsem, ww_mutex), wait, session and executor, sites and images, `/dev/kdlock` |
| `jit/` | the translator (`kdjit/`) and its daemon `kd_daemon.py` (cumulative learning, allow lists) |
| `integration/` | putting kdlock into a Linux 7.0 tree: the mmap lock (`CONFIG_KDLOCK_MM`), syscall-path lock objects (`CONFIG_KDLOCK_API`), every lock (`CONFIG_KDLOCK_ALL`) |
| `bench/` | the benchmark module, the runners, the correctness runner `run_corr.py`, will-it-scale, allow lists, and all results under `bench/results/` |
| `tclock_backend/` | the original TCLocks locks, the benchmark's comparison backend |
| `docs/` | the guides (index: [docs/README.md](docs/README.md)) |

Linux 7.0 (Ubuntu `linux=7.0.0-38.38` source) on x86_64 is the only target.
The mechanism and its invariants are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
The per-family protocols, what may delegate and the tunables are in
[docs/LOCKS.md](docs/LOCKS.md). The translator is described in
[docs/TRANSLATOR.md](docs/TRANSLATOR.md), and kernel integration in
[docs/KERNEL_INTEGRATION.md](docs/KERNEL_INTEGRATION.md). The VM, the kernels
and the build and test procedure are in
[docs/BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md). Change these documents
together with the code; do not restate their details here.

## Goal

The goal is replacing locks inside the kernel, and evaluating unchanged
applications on it (will-it-scale `mmap1` and the like). The steps are
nano/micro performance evidence, then the mmap lock and page faults, then
the whole kernel. The whole-kernel work goes in this order:

1. A kernel with every lock switched, delegation off: done (`CONFIG_KDLOCK_ALL`).
2. Images that follow runtime text patching.
3. Classification of per-CPU (`%gs`) accesses.
4. Delegation lock user by lock user, from allow lists (`kd_daemon.py --allow`).

Report current support and performance limits explicitly.

## Design rules

1. All users of a lock object follow one protocol.
2. Lock ownership is the lock word itself, and lifetimes hold by construction
   (ARCHITECTURE.md). Keep those invariants when changing the code. The
   `kdlock_stats` counters are approximate and are not evidence of ownership.
   Never remove a check or a probe to hide a reproduced failure.
3. Lock entries keep the caller's preemption, interrupt and BH state exactly as
   the native API does, whether the section runs locally, delegated or handed
   back.
4. Prefer preallocated per-CPU storage and explicit lifetime transfer. Avoid
   whole-packet copies, blanket clears or a global lock added only to simplify
   lifetime accounting. Keep the state capture and restore that resumption needs.
5. Kernel and module source are trusted (the user's choice). The translator
   does not prove a section safe and does no context or loop-value analysis.
   It copies faithfully, routes calls and returns exactly, and hands back to the
   original task whatever it cannot run (frontiers and misses, TRANSLATOR.md).
   Trusting source does not add missing translator support.
6. Kernel-side changes for a workload are limited to the critical sections'
   lock calls and the minimal lock binding and lifetime glue. Native bodies,
   their semantics and data structures stay unchanged. Real-world API tests
   go through the userspace system call path. Extracted-body calls and test
   ioctls are mechanism evidence, not substitutes for the real API.
7. The configurations that `kernel/Kconfig` refuses (CONFIG_PREEMPT_RT, lock
   debugging, lockdep and the others listed there) are outside support.

Current validation limits:

* `CONFIG_KDLOCK_ALL` has been tested with delegation off, and with
  delegation for allow-listed lock users (`bench/results/kdclaude/kdall-*`).
* `ww_mutex` applies wait-die to both classes and is never delegated.
* Open failure: a delegated munmap with the kept downgrade (`kd_vdown=1`)
  can leave an mmap lock write-held when Apache's worker processes exit
  (LOCKS.md 5, `bench/results/kdclaude/appgrid-20261118-64cpu/` section 6).
* Call-depth tracking (`CONFIG_MITIGATION_CALL_DEPTH_TRACKING`) is built into
  the kdlock kernels. It is active only on CPUs affected by `retbleed`, which
  the VM's CPU is not, so translated code has not run with it active.

## Working rules

1. Read source and Git status before editing. Preserve unrelated work. Prose
   and comments are in English. Explain protocol purpose and ordering.
2. Source edits, Git, static inspection and read-only checks run on `380G10`.
   All builds, unit tests, modules, daemons and timing run only in the VM
   described in BUILD_AND_TEST.md.
3. Run basic checks plus the directly affected ones. Full suites need an
   explicit user request. Missing dependencies, skips and compile failures are
   not passes.
4. Modifying, building and installing the guest kernel, and rebooting the
   guest, are approved by default.
5. Synchronize only while idle and never edit inputs of a running test.
   Confirm a real recovery snapshot before live module or JIT work. Bound
   remote commands; a timeout does not prove drain. Never force unload or
   clear `/root/host_fs`.
6. Keep one guide per responsibility. Preserve benchmark results, captured
   hashes, numeric evidence, failures and topology identities.

## Naming and wording

Standing user preference for all future sessions and tasks: avoid
cybersecurity-associated terminology in newly created names and newly written
prose. Prefer neutral, technically accurate descriptions of correctness,
execution, ownership, concurrency and performance. This applies to file and
directory names, functions, variables, macros, comments, documentation, commit
messages, branch names, tests and log labels. Prefer terms such as continuation,
handoff, local execution, instruction service, test body and fixture when they
faithfully describe the mechanism.

This is a forward-looking wording rule, not a request to rename existing APIs
or mechanisms. Preserve established identifiers and references exactly, including
when discussing them in new prose. Technical accuracy takes precedence: if an
exact technical term has no faithful neutral equivalent, use it and briefly
explain why it is necessary. This preference concerns wording only; it does not
change implementation behavior or validation requirements.

## Git and reporting

* Local commits and branch organization are authorized. The maintained branch
  is `master`.
* Review staged changes, commit coherent work and report validation limits.
* For rollback use a reviewed path-specific restore or revert; never reset
  unknown work.
* Keep rejected experiments and user work in progress reachable through
  explicit archive refs (`refs/archive/...`).
* Do not claim a performance gain without measurements. Performance results
  come from matched runs in one boot; numbers across boots or kernels are
  indicators only. Do not pool kernels, source versions, topologies, call
  shells, workloads or instrumentation settings.
* A published image is not proof that sections ran delegated: report the
  delegated and handback counters with every rate.
