# kdlock

kdlock delegates contended x86-64 kernel critical sections to a combiner and
translates their existing machine code at runtime. The aim is TCLock-style
delegation without rewriting each critical section's source. Existing guest
lock hooks are still required; this is not an unmodified-kernel solution.

The project targets **x86_64 machines only**. Development priorities and explicit
deferrals are maintained in the [delivery scope](docs/TODO.md#delivery-scope).
Start with the Chinese [code map and manual](docs/PROJECT_GUIDE.md) for the
implementation index and host/guest environment setup.

## Execution Model

```text
kernel lock hook -> native lock L + kdlock request queue
                 -> validate root / logical-child scope
                 -> optional entry predicates before generated body
                    -> refusal: unstarted native execution, no body replay
                 -> combiner executes waiter state in generated JIT code
                    -> lock control: update ownership, validate continuation
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
Unconditional context/backend bans cover every emitted block, including RET
targets skipped by sequential value analysis. This is not a runtime memory-
freshness or arbitrary concurrent-mutation guarantee.

Spin and mutex delegation retain the original Linux lock as the exclusion
authority. Private queues schedule requests; they do not replace native
ownership. During native continuation the combiner retains its acquired locks
and services waiter unlock notifications. Mutex owner handoff is not added.
Final logical ACK can precede physical A release when its combiner still owns
the batch. Dropping the last acquisition reference removes task membership
before ACK; reclamation waits for RCU readers.

## Current Status

This is an experimental kernel JIT delegation prototype. It implements
contended spin/mutex delegation, nested requests, allowlisted services,
supported forward native continuation, native-owner exclusion and ACKs.
The default provider requires the `kdclobber2` caller-clobber v1 kernel interface.
Fresh admission checks CPU-local activity, then that CPU’s per-lock frequency,
then task identity; only locally qualified addresses enter the shared hot set.
Ordinary spin and mutex use separate versioned caller identities:
normal requests retain RIP/RSP/RBP and intermediate exits materialize full
logical GPR state. Legacy callers and special lock APIs retain
their existing contracts; older kernel hook installers are no longer supported.
The Chinese [version overview](docs/PROJECT_GUIDE.md#1-当前进展) describes supported
capabilities; [DESIGN](docs/DESIGN.md) defines their contracts and
[TODO](docs/TODO.md) tracks unfinished and deferred work.

## Quick Start

Host checkout: `/home/eric/vm/vm-shared/kdlock`.
Build and execute only in the recovery guest at `root@127.0.0.1:2222`, using
`/root/host_fs/kdlock`; never load these modules on the host.
The guest requires a verified [hook baseline](kernel_baseline/README.md),
`nokaslr`, access to `/proc/kcore`, and the
[pinned Python runtime](disassem/requirements.txt). Follow the
[dependency procedure](docs/PROJECT_GUIDE.md#33-检查依赖与空闲状态) and
[operations guide](docs/AGENTS.md) before building.

```sh
# Recovery guest only, with the appropriate kernel build tree installed.
cd /root/host_fs/kdlock
make -C kernel_module W=1
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
```

In normal mode the guest sees host source through 9p. Recovery mode uses a
separate ext4 checkout: compare file hashes and sync only changed files.
Do not move or recursively replace the repository. Kernel identity, dependency
setup, recoverability and controlled module lifecycle remain explicit
[environment requirements](docs/AGENTS.md#环境边界).

## Boundaries

- Both spinlock and mutex delegation support explicit GS memory operands by
  default, using the pinned waiter's kernel GS base; a supported
  `current_task` load uses the logical waiter task. Queued waiters poll with
  `cpu_relax()` (`pause` on x86), with preemption disabled until completion or
  native handoff. This prevents other tasks from running on the origin CPU
  during delegation; it does not exclude IRQ/NMI access to the same storage.
- Admission rejects FS operands, hardware segment/base manipulation and
  recognized context-sensitive operations, including statically resolved addresses in
  each possible CPU's [core static area and boot-reserved module arena](docs/DESIGN.md#722-static-per-cpu-ranges).
  This requires the matching provider's module-range capability, not merely
  readable symbol names; missing capability is a translation environment error.
  This does not prove arbitrary aliases,
  per-CPU concurrency or scheduling/IRQ/RCU equivalence. Unresolved runtime pointers and
  concurrent pointer replacement can bypass this screening, as reproduced with
  benign generated userspace code. `CONTEXT_SCREENING_ONLY` makes this limit
  explicit; it does not add a guard. See the
  [dynamic-address gap](docs/DESIGN.md#721-dynamic-address-gap).
- The two-word input remains `args[0]=waiter GS base`,
  `args[1]=logical waiter task`; it does not switch hardware task context.
- JIT is not a security sandbox. Memory guards and instruction semantics are
  incomplete. INT can become NOP; some special operations only warn.
  Flags can be clobbered by instrumentation and are not restored across exits.
- Native continuation is supported at specific validated boundaries, not for
  arbitrary faults after progress. Unsupported post-entry states fail-stop.
- Code is replaced in place without immutable versions or per-version reclamation.
  This risk is explicitly deferred, not solved by lock serialization.
- Frames, lock tables, node pools and stacks are bounded. Source/lock address
  reuse and hot module unload are not generally safe. Non-target tasks also
  call the guest hook predicates; stopping known workload callers is not a reader
  drain. The [lifetime assessment](docs/DESIGN.md#31-source-lock-and-hook-lifetimes)
  separates source pins, lock-object retirement and missing hook capabilities.
- `mutex_jit` is enabled by default; `mutex_jit=0` is only for explicit native
  baseline controls. No userspace/futex frontend, rwsem, RT/PI/WW mutex or
  general IRQ/BH delegation. Only explicitly allowlisted hostcalls, not arbitrary
  printk.

## Repository And Documentation

| Path | Responsibility |
| --- | --- |
| `kernel_module/` | Hooks, native locks, queues, frames and execution |
| `disassem/` | Decode, admission, register lowering and code generation |
| `daemon/` | Translation requests, workspaces and publication |
| `include/` | Shared ABI, protocol headers and wrapper assembly |
| `workload_modules/` | Demo kernel critical-section modules |
| [bench/](bench/README.md) | Workload clients and measurement documentation |
| [tests/](tests/README.md) | Verification documentation and entry points |
| `kernel_baseline/` | Captured guest patch, configuration and identity verifier |
| `kernel_experiments/` | Separately authorized kernel experiments |
| [tclock_backend/](tclock_backend/README.md) | Independent TCLock native stack-delegation backend |

- [Code map and manual](docs/PROJECT_GUIDE.md): source index and environment setup.
- [Execution](docs/JIT_EXECUTION.md): execution flows and protocol contracts.
- [Design](docs/DESIGN.md): implementation and ownership contracts.
- [Register ABI](docs/JIT_REGISTER_ABI.md): entry, registers, stacks and exits.
- [Operations](docs/AGENTS.md): host/guest boundaries, source sync and recovery.
- [Tasks](docs/TODO.md): remaining main functionality and deferred work.
- [Daemon](daemon/README.md): CLI, diagnostics and publication limits.
- [Kernel baseline](kernel_baseline/README.md): prerequisite and reproduction.
