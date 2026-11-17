# Development rules

**Scope.** This repository holds one implementation of kdlock, the clean
rewrite, plus the original TCLocks locks it is compared against. The earlier
implementation and its documents, benchmarks and results are not in this tree;
every reference below to a document or directory that is not here points into
the earlier tree, which is reachable in git through the tag `full-tree-before-cleanup-20261115`.
This tree's own guides are under [docs/](docs/README.md). Where this
implementation differs from the earlier one's documents, and why, is in
[docs/DIFFERENCES.md](docs/DIFFERENCES.md).

The project goal is relevant in-kernel lock replacement and evaluation of
unchanged applications such as will-it-scale `mmap1`. Follow the three stages of
the project roadmap (the earlier `docs/ROADMAP.md`): micro/nano performance evidence, scoped
mmap/page-fault improvement or parity, then broader kernel integration. Current
support and performance limits remain explicit; a future milestone does not
override the implementation or VM rules below.

Linux 6.1 kernel development is retired; no further adaptation targets it.
Development targets Linux 7.0 (Ubuntu `linux=7.0.0-38.38` source) on x86_64.
The VM, its kernels and the build and test procedure are in
[docs/BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md). Preserve benchmark results.
Legacy commands and measurements are historical references only.

The maintained branch is `master`. What the implementation does is documented
in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (mechanism and invariants),
[docs/LOCKS.md](docs/LOCKS.md) (per-family protocols, what may delegate,
tunables), [docs/TRANSLATOR.md](docs/TRANSLATOR.md) and
[docs/KERNEL_INTEGRATION.md](docs/KERNEL_INTEGRATION.md). Change those
documents together with the code; do not restate their details here.
All users of an object must follow one protocol. The configurations that
`kernel/Kconfig` refuses (CONFIG_PREEMPT_RT, lock debugging, lockdep and the
others listed there) are outside support, not pending integration targets.
Current validation limits:

* The whole-kernel switch (`CONFIG_KDLOCK_ALL`) has been built and tested
  with delegation off, and with delegation only for allow-listed lock users
  (`bench/results/kdclaude/kdall-*`).
* `ww_mutex` applies wait-die to both classes and is never delegated.
* Call-depth tracking (`CONFIG_MITIGATION_CALL_DEPTH_TRACKING`) is built into
  the kdlock kernels. It is active only on CPUs affected by `retbleed`, which
  the VM's CPU is not, so translated code has not run with it active.

The user explicitly selected trusted kernel and module source on October 27.
The translator does not prove a section safe and does no context or
loop-value analysis. It copies faithfully, routes calls and returns exactly,
and hands back to the original task whatever it cannot run (frontiers and
misses, TRANSLATOR.md). Trusting source does not add missing translator
support.

1. Read source and Git status before editing. Preserve unrelated work. Maintained
   prose and comments use English. Explain protocol purpose and ordering.
2. Source edits, Git, static inspection and read-only offline archive checks run
   on `380G10`. All builds, unit tests, modules, daemons and timing run only in the
   VM described in [docs/BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md).
3. Use basic plus directly affected checks. Full suites require an explicit user
   request. Missing dependencies, skips and compile failures are not passes.
4. Lock ownership is the lock word itself, and lifetimes hold by construction
   (ARCHITECTURE.md). Keep those invariants when changing the code. The
   `kdlock_stats` counters are approximate and are not evidence of ownership.
   Never remove a check or a probe to hide a reproduced failure.
5. Prefer preallocated per-CPU storage and explicit lifetime transfer. Avoid
   whole-packet copies, blanket clears or a global lock added only to simplify
   lifetime accounting. Keep the state capture and restore that resumption needs.
6. Lock entries keep the caller's preemption, interrupt and BH state exactly as
   the native API does, whether the section runs locally, delegated or handed
   back.
7. Modifying, building and installing the guest kernel, and rebooting the guest,
   are approved by default; no additional user permission is required.
8. Synchronize only while idle and never edit frozen running inputs. Confirm a
   real recovery snapshot before live module/JIT work. Bound remote commands.
   A timeout does not prove drain. Never force unload or clear `/root/host_fs`.
9. The benchmark module, its runners and the results are in `bench/`. The
   correctness runner is `bench/run_corr.py`.
10. Keep one guide per responsibility. Current instructions belong in maintained
    docs; historical protocols/results belong in history or fixed Git evidence.
    Preserve captured hashes, numeric evidence, failures and topology identities.
11. Permanent real-world API testing constraint: invoke the actual API through
    its userspace system call path. Restrict kernel-side experimental changes to
    the relevant critical sections' lock API calls and minimal required lock
    binding/routing/lifetime glue. Preserve native bodies, surrounding semantics
    and data structures; prefer leaving kernel source unchanged. Extracted-body
    calls and test ioctls are mechanism evidence, not real-world API substitutes.

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

Ongoing local commits and branch organization are authorized. Review staged
changes, commit coherent work and report validation limits. Use a reviewed
path-specific restore or revert for rollback, never reset unknown work.
Keep rejected experiments and user WIP reachable through explicit archive refs;
the tree as it was before this one was separated out is the tag `full-tree-before-cleanup-20261115`.
Do not claim a performance gain without measurements; do not pool source versions,
topologies, call shells, workloads or instrumentation settings. A published
image is not proof that sections ran delegated: report the delegated and
handback counters with every rate.
