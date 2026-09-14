# kdlock

kdlock delegates contended x86-64 kernel critical sections to a combiner and
translates their existing machine code at runtime. The aim is TCLock-style
delegation without rewriting each critical section's source. Existing guest
lock hooks are still required; this is not an unmodified-kernel solution.

The project targets **x86_64 machines only**. Implementation, testing and the
task list do not include ports to other architectures.

Development prioritizes supported main paths. Rare-scenario implementation and
dedicated tests are optional, not current delivery gates; known gaps remain
documented. Existing guards and actual-JIT acceptance are retained. See the
[delivery scope](docs/TODO.md#delivery-scope).

Start reading or running this checkout with the Chinese
[code map and step-by-step manual](docs/PROJECT_GUIDE.md). It indexes production
code, test drivers and fixtures, and separates host commands from guest execution.

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

**2026-09-14:** this working-tree version is an experimental x86_64 kernel JIT
delegation prototype. This checkpoint collects the implementation, consolidated
tests and documentation developed since `1d5fc7259d96863aa143343d22c79aaf93023c9e`.
The final cleanup makes timing-label mappings explicit and improves comments and
formatting; it does not change the lock protocol or reopen deferred work. See
the [checkpoint verification](docs/VALIDATION.md#repository-checkpoint).

The Chinese [version overview](docs/PROJECT_GUIDE.md#1-当前进展) is the single
summary of completed capabilities, remaining work and explicit deferrals.
Per-freeze test results stay in [VALIDATION](docs/VALIDATION.md); implementation
contracts and priorities stay in [TODO](docs/TODO.md).

- Implemented: contended spin/mutex JIT, nested delegation, allowlisted services
  returning to JIT, supported forward native continuation, real native-owner
  exclusion and ACKs, static admission, selected-test evidence and guest setup.
  Modes 0-8 have evidence on their stated freezes; this is not a new full rerun.
- Latest kernel-JIT run, before checkpoint cleanup: native-handoff timing adds
  two default-off rows, for ten
  enabled timing intervals. Six affected units, W=1 build, off-mode 4/8,
  eight paired sessions and on-mode 4/5/8 pass on 211 frozen inputs, retaining
  **1,252 returned JIT bodies**. Mutex positives use `mutex_jit=1`.
  Owners, ACKs, frame/args layout and the guest kernel are unchanged. See
  [this acceptance](docs/VALIDATION.md#native-handoff-timing), including the
  initial invalid-repeat CLI rejection that started no workload.
- Unresolved: the earlier two-CPU short mode-5 session published code but ran
  zero JIT bodies. It remains a failure, not a performance PASS; queue/parking
  strategy, complete cost attribution, speedup and a faithful TCLock comparison
  are unfinished. No automatic retry or new rare-case matrix is added.
- Deferred: access-time address guards and pre-instruction continuation,
  local/general flags and special-instruction repairs, immutable JIT versions
  and per-version reclamation. Static screening is not dynamic memory or
  execution-context safety; broader service/lifetime support remains limited.

The earlier isolated-runtime acceptance (40 unit programs, 25 admission cases,
core 5/5) and the earlier 64/64 matrix remain historical, not merged with this
increment. Rare scenarios may remain unimplemented and untested; existing
actual-JIT and state/owner checks are not weakened.

## Quick Start

Host checkout: `/home/eric/vm/vm-shared/kdlock`.
Build and execute **only in the recovery guest**, reached with
`ssh -p 2222 root@127.0.0.1`; never load these modules on the host.
The guest needs the [captured Linux 6.1.159 hook baseline](kernel_baseline/README.md),
x86-64, boot-time `nokaslr`, the CPython 3.10
[pinned runtime](disassem/requirements.txt) and access to
`/proc/kcore`. A generic kernel with the same release string is insufficient.
Install/activate the guest venv using the
[single dependency procedure](docs/PROJECT_GUIDE.md#33-检查依赖与空闲状态) before the
commands below. Tests and daemon translation children inherit its PATH; merely
setting `VIRTUAL_ENV` is insufficient. No host or global pip installation is needed.

### Recovery / normal mode difference

- normal mode: guest mounts host source via 9p, so edits in host are visible immediately
  at `/root/host_fs/kdlock` inside guest.
- recovery mode: guest runs `/root/host_fs/kdlock` from its own ext4 image, so edits are
  not auto-visible and must be synced explicitly.
- normal mode is for fast iteration and smoke-style checks.
- recovery mode is for high-risk kernel-live tests, crash recovery, and snapshot-backed rollback.

For normal operation in recovery mode, compare file hashes and sync only changed files;
do not move or recursively copy the repository. Confirm VM recoverability and snapshot
availability before live execution by following [AGENTS](docs/AGENTS.md) first.

The following is initial environment acceptance, not a per-edit checklist.
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

After initial acceptance, select affected complex tests rather than repeating
basic smoke tests. Preview is read-only; live execution below is guest-only:

```sh
bash tests/run_all.sh --suite mutex --dry-run
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite mutex
```

This selects modes 4/5, explicitly enables `mutex_jit=1`, builds/loads the modules,
runs daemon/workloads and checks returned generated-body evidence before draining.
These live tests are not harmless userspace tests. No-argument `run_all.sh` only
lists scopes; `--case` selects one case, overlapping scopes are deduplicated and
execution stops on failure. Covered diagnostics stay opt-in, not daily prerequisites.
See [selection and consolidation](docs/JIT_EXECUTION.md#7-分层与增量回归) for independent
contracts that must remain, and the [manual sequence](docs/PROJECT_GUIDE.md#3-一步一步运行)
for individual component startup and cleanup.

The runner retains frozen source, environment observations, logs and artifacts
outside the checkout. Check an existing result with
`python3 tests/verify_evidence.py "$RUN_DIR"`; this does not rerun JIT or certify
current code. Capture errors and incomplete drain cannot create `accepted`.
See [evidence handling](docs/JIT_EXECUTION.md#执行与证据) for the full contract.

## Benchmark Modes

| Mode | Backend | Scenario | Latest ordinary JIT gate |
| --- | --- | --- | --- |
| 0 | Spin | Contended single lock | Pass |
| 1 | Spin | Nested A/B | Pass, guarded admission |
| 2 | Spin | Allowlisted service, return to JIT | Pass |
| 3 | Mutex | Contended single lock | Pass, `mutex_jit=1` |
| 4 | Mutex | Nested A/B | Pass, guarded admission, `mutex_jit=1` |
| 5 | Mutex | Allowlisted service, return to JIT | Pass, `mutex_jit=1` |
| 6 | Spin | Deep A/B/C nesting | Pass |
| 7 | Spin | Unlock A before B | Pass |
| 8 | Spin | Independent queues / opt-in remote chains | Pass; stage-2/3 register continuation also passes |
| 9 | Spin | Recovery topology | Legacy synthetic post-entry faults are fail-stop |
| 10 | Spin | GS/current rejection | Native-only negative test |
| 11 | Mutex | GS/current rejection | Native-only negative test, `mutex_jit=1` |

Daemon `--mode flat/per-tgid` (`1/2` and `v1/v2` remain as legacy aliases) selects
workspace layout, not any benchmark mode.

`KD_TEST_METRICS=1` adds structured ioctl measurements to the existing benchmark:
worker-envelope time, ioctl p50/p99, summed worker CPU time and exact completed
counts. Failed runs have null performance fields. Existing complex spin and
mode-5 stress drivers retain measured logs and before/after kernel evidence.
These are instrumented measurements, not a speedup or native-delegation baseline;
see the [measurement flow and limits](docs/JIT_EXECUTION.md#33-带观测的负载测量).
The [comparator assessment](docs/DESIGN.md#13-performance-comparator-contract)
confirms that upstream TCLock mutex is not a drop-in module for this guest;
broader matched native/JIT trials and a faithful native-delegation comparison
group remain separate open work, all on x86_64.

## Boundaries

- Admission rejects GS memory, FS operands and recognized context-sensitive
  operations in retained JIT code, including statically resolved addresses in
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
  call the guest hook predicates; stopping benchmark workers is not a reader
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
| `klock_module/`, `bench/` | Kernel workloads and ioctl driver |
| `tests/` | Units, protocol oracles and opt-in live tests |
| `kernel_baseline/` | Existing guest patch/config/identity, read-only verifier |

- [Code map and manual run](docs/PROJECT_GUIDE.md): file index and first-run steps.
- [Execution and tests](docs/JIT_EXECUTION.md): complex-case flows and acceptance.
- [Design](docs/DESIGN.md): implementation and ownership contracts.
- [Register ABI](docs/JIT_REGISTER_ABI.md): entry, registers, stacks and exits.
- [Operations](docs/AGENTS.md): host/guest safety, source sync and recovery.
- [Validation](docs/VALIDATION.md): current evidence and historical index.
- [Test inventory](docs/TEST_EXAMPLES.md): per-test purpose, overlap review and scoped execution.
- [Tasks](docs/TODO.md): remaining main functionality and deferred work.
- [Daemon](daemon/README.md): CLI, diagnostics and publication limits.
- [Kernel baseline](kernel_baseline/README.md): prerequisite and reproduction.
