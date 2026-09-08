# kdlock

kdlock delegates contended x86-64 kernel critical sections to a combiner and
translates their existing machine code at runtime. The aim is TCLock-style
delegation without rewriting each critical section's source. Existing guest
lock hooks are still required; this is not an unmodified-kernel solution.

## Execution Model

```text
kernel lock hook -> native lock L + kdlock request queue
                 -> combiner executes waiter state in generated JIT code
                    -> lock control: update ownership, continue JIT
                    -> allowlisted hostcall: native service, continue JIT
                    -> ordinary CALL miss: original waiter finishes native suffix
                 -> physical owner unlocks L and acknowledges completion
```

An ordinary direct CALL to an undecoded callee ends the current JIT episode.
The waiter resumes at the saved callee RIP with the current registers and
virtual CALL stack, not at the critical-section entry. Earlier stores are not
rolled back or replayed. Learning/recompilation affects future invocations.
Admission and code generation use the same possible JIT range; a suffix
reachable by another JIT path still requires checking.

Spin and mutex delegation retain the original Linux lock as the exclusion
authority. Private queues schedule requests; they do not replace native
ownership. During native continuation the combiner retains its acquired locks
and services waiter unlock notifications. Mutex owner handoff is not added.

## Current Status

Latest complete matrix, **2026-09-08**: **37/51 pass**, comprising **23 actual-JIT
cases, 12 context-refusal cases and two native controls**. **14 cases fail**,
including the ordinary complex mode 1/4/8 workloads and related continuations.
Mode 0/2/3/5/6/7 pass actual-JIT checks; mutex positives use `mutex_jit=1`.
Dedicated depth/remote fixtures passing does not make ordinary mode 8 pass.
The later analysis-foundation check passes all 39 unit programs and the
independent 25-case admission audit. Experimental entry predicates are not
enabled in production and do not close the failed nested gates. Their scope
and tests are described in [the usage guide](docs/JIT_EXECUTION.md#5-入口条件分析尚未接入生产).

These are bounded correctness observations, not a claim of complete support.
Commands, failed cases, source identity and evidence are centralized in
[VALIDATION](docs/VALIDATION.md#jit-episode-scope). Do not substitute historical
passes or successful native fallback for the current JIT acceptance gate.

## Quick Start

Host checkout: `/home/eric/vm/vm-shared/kdlock`.
Build and execute **only in the recovery guest**, reached with
`ssh -p 2222 root@127.0.0.1`; never load these modules on the host.
The guest needs the [captured Linux 6.1.159 hook baseline](kernel_baseline/README.md),
x86-64, boot-time `nokaslr`, Python 3 with miasm 0.1.5 and access to
`/proc/kcore`. A generic kernel with the same release string is insufficient.

Normal mode exposes the host source through 9p. In recovery mode the same
`/root/host_fs/kdlock` pathname is guest-local ext4. Compare hashes and transfer
only changed files; do not move or recursively copy the repository.
Confirm the VM and a usable snapshot following [AGENTS](docs/AGENTS.md) first.

All commands below run in the guest:

```sh
cd /root/host_fs/kdlock
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
make -C tests/unit run
python3 tests/audit_context_spills.py
make -C kernel_module W=1
make -C klock_module W=1
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c \
  -o bench/klock_test -lpthread
```

After confirming recovery, a focused single-lock mutex JIT test is:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_09_jit_execution_modes.sh 3
```

This script explicitly enables `mutex_jit=1`, builds/loads the modules, runs
the daemon and workload, checks returned generated-body evidence, then drains
and unloads. It is not a harmless userspace test.
See [JIT_EXECUTION](docs/JIT_EXECUTION.md) for the full flow, all main-mode
commands, native-continuation tests and interpreting failures.
The multi-mode script stops at its first failure; modes 1/4 currently fail.

## Benchmark Modes

| Mode | Backend | Scenario | Latest ordinary JIT gate |
| --- | --- | --- | --- |
| 0 | Spin | Contended single lock | Pass |
| 1 | Spin | Nested A/B | Fails admission |
| 2 | Spin | Allowlisted service, return to JIT | Pass |
| 3 | Mutex | Contended single lock | Pass, `mutex_jit=1` |
| 4 | Mutex | Nested A/B | Fails admission, `mutex_jit=1` |
| 5 | Mutex | Allowlisted service, return to JIT | Pass, `mutex_jit=1` |
| 6 | Spin | Deep A/B/C nesting | Pass |
| 7 | Spin | Unlock A before B | Pass |
| 8 | Spin | Independent queues / opt-in remote chains | Ordinary case fails; selected fixtures pass |
| 9 | Spin | Recovery topology | Legacy synthetic post-entry faults are fail-stop |
| 10 | Spin | GS/current rejection | Native-only negative test |
| 11 | Mutex | GS/current rejection | Native-only negative test, `mutex_jit=1` |

Daemon `--mode 1/2` selects workspace layout, not any benchmark mode.

## Boundaries

- Admission rejects GS memory, FS operands and recognized context-sensitive
  operations in retained JIT code. This does not prove arbitrary aliases,
  per-CPU concurrency or scheduling/IRQ/RCU equivalence.
- The two-word input remains `args[0]=waiter GS base`,
  `args[1]=logical waiter task`; it does not switch hardware task context.
- JIT is not a security sandbox. Memory guards and instruction semantics are
  incomplete. INT can become NOP; some special operations only warn.
  Flags can be clobbered by instrumentation and are not restored across exits.
- Native continuation is supported at specific validated boundaries, not for
  arbitrary faults after progress. Unsupported post-entry states fail-stop.
- Code is replaced in place without immutable versions or executor retirement.
  This risk is explicitly deferred, not solved by lock serialization.
- Frames, lock tables, node pools and stacks are bounded. Source/lock address
  reuse and hot module unload are not generally safe.
- `mutex_jit` defaults to 0; plain non-RT mutex and spin paths are the active
  scope. No userspace/futex frontend, rwsem, RT/PI/WW mutex or general IRQ/BH
  delegation. Only explicitly allowlisted hostcalls, not arbitrary printk.

## Repository And Documentation

| Path | Responsibility |
| --- | --- |
| `kernel_module/` | Hooks, native locks, queues, frames and execution |
| `disassem/` | Decode, admission, register lowering and code generation |
| `daemon/` | Translation requests, workspaces and publication |
| `include/` | Shared ABI, protocol headers and wrapper assembly |
| `klock_module/`, `bench/` | Kernel workloads and ioctl driver |
| `tests/` | Units, protocol oracles and opt-in live tests |
| `kernel_baseline/` | Existing guest patch/config/identity, read-only verifier |

- [Execution and tests](docs/JIT_EXECUTION.md): primary usage guide.
- [Design](docs/DESIGN.md): implementation and ownership contracts.
- [Register ABI](docs/JIT_REGISTER_ABI.md): entry, registers, stacks and exits.
- [Operations](docs/AGENTS.md): host/guest safety, source sync and recovery.
- [Validation](docs/VALIDATION.md): current evidence and historical index.
- [Tasks](docs/TODO.md): remaining main functionality and deferred work.
- [Daemon](daemon/README.md): CLI, diagnostics and publication limits.
- [Kernel baseline](kernel_baseline/README.md): prerequisite and reproduction.
