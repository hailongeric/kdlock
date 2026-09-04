# kdlock Component Map

Last updated: 2026-09-04

This document describes the project files by responsibility. Build, module
loading, daemon execution, benchmarks, and integration tests run inside the
QEMU guest at `/root/host_fs/kdlock`; source editing and git inspection happen
on the host checkout.

## Top-level Files

- `.gitignore`: excludes kernel build outputs, generated daemon/JIT workspaces,
  Python caches, editor noise, and local test binaries from version control.
- `README.md`: root project overview, quick start, test entry points, and links
  to detailed docs.
- `setup.sh`: guest initialization step after each VM boot or restart. It
  loads the workload module and applies the sysctl settings expected by tests.
- `compiler_install_kernel.sh`: kernel build/install helper. Do not run during
  normal development unless explicitly authorized because it modifies the guest
  kernel installation.

## Tool Metadata

- `.agents/`: automation metadata directory. It currently contains no tracked
  project files.
- `.codex/`: Codex metadata directory. It currently contains no tracked project
  files.
- `.claude/settings.local.json`: local Claude permissions for SSH and git
  commands. Treat it as tool configuration, not runtime project logic.

## Documentation

- `docs/AGENTS.md`: operating manual for AI/automation sessions, including host
  vs guest boundaries, safety rules, validation order, and crash handling.
- `docs/DESIGN.md`: full architecture and protocol design for hooks,
  delegation, sandbox translation, JIT execution, and known limitations.
- `docs/COMPONENTS.md`: this file, a file-by-file component and test map.
- `docs/CRASH_LOG_PLAN.md`: plan and current status for high-risk JIT recovery,
  QEMU monitor usage, and crash evidence collection.
- `docs/NESTED_SPIN_JIT_TASKS.md`: completed phased checklist and validation
  evidence for TCLock-style nested spinlock JIT delegation.
- `docs/plan.md`: current execution checklist, decisions, failures, and
  validation results; read and update it before task operations.
- `docs/TODO.md`: task status, recently fixed bugs, validation
  status, and future work.

## Kernel Module

The `kernel_module/` directory builds `kdlock_km.ko`, the loadable module that
installs hooks into the patched Linux kernel and implements delegation.

- `kernel_module/Makefile`: kbuild entry for `kdlock_km.ko`.
- `kernel_module/kd_main.c`: module init/exit. Initializes subsystems, installs
  exported hook pointers, registers `/dev/kd_dev`, and removes hooks with exit
  synchronization.
- `kernel_module/kd_lock.c`: hook layer for raw spinlocks and mutexes. Handles
  target filtering, hot-lock checks, original fallback paths, mutex shadow-table
  lookup, transition draining from original mutex users to kd mutex users, and
  nested spin known-call acquire/unlock/abort handling.
- `kernel_module/kd_exec.c`: bounded per-CPU execution-frame stack for nested
  JIT register continuations, lock ownership, completion, and abort invariants.
- `kernel_module/kd_spinlock.c`: spinlock delegation protocol. Implements the
  queue, combiner path, shadow stack, waiter completion, nested/OOO unlock
  handling, and JIT execution for spinlock critical sections.
- `kernel_module/kd_mutex.c`: mutex delegation protocol. Implements kd mutex
  queueing, combiner handoff/fallback, per-CPU shadow stacks, optional
  `mutex_jit=1` sandbox execution, resume after delegated `mutex_unlock`, and
  protocol counters.
- `kernel_module/exe.c`: JIT execution engine. Manages `kd_exe_info` entries,
  executable code-block pool, endpoint resolution, write-back state, miss
  handling, and sandbox invocation through the assembly wrapper.
- `kernel_module/sys.c`: `/dev/kd_dev` character device for daemon/kernel
  communication. Exposes pending translation requests and receives generated
  `jit.bin` payloads.
- `kernel_module/kd_int3.c`: hot-lock promotion state machine and int3-based
  runtime redirection support.
- `kernel_module/kd_futex.c`: futex delegation support inherited from the BCD
  path. Handles futex wait/wake interaction when translated code hits futex
  syscalls.
- `kernel_module/combiner.c`: shared combiner support code retained from the
  original delegation implementation.
- `kernel_module/timing_stats.c`: timing/statistics support routines.
- `kernel_module/km.sh`: legacy/manual module loader helper. Prefer the test
  scripts or explicit `insmod` sequence documented in `docs/AGENTS.md`.

## Public Headers and Assembly

The `include/` directory contains shared declarations used by kernel code,
daemon code, tests, and generated sandbox assembly.

- `include/asm_head.h`: assembly header used by generated JIT code.
- `include/combiner.h`: shared combiner constants and structures.
- `include/exe.h`: JIT execution constants, status codes, and `kd_exe_info`
  declarations shared with kernel code.
- `include/exe_info.h`: daemon/kernel wire-format structure for `/dev/kd_dev`.
- `include/kd_futex.h`: futex delegation declarations.
- `include/kd_int3.h`: hot-lock/int3 declarations.
- `include/kd_lock.h`: lock hook and fallback declarations.
- `include/kd_exec.h`: nested JIT execution-frame, event, combiner snapshot,
  and lock-ownership declarations.
- `include/kd_mutex.h`: kd mutex structures and function declarations.
- `include/kd_spinlock.h`: kd spinlock structures and function declarations.
- `include/mcs_spinlock.h`: MCS queue primitives used by delegation code.
- `include/qspinlock_i.h`: qspinlock-compatible internal constants/helpers.
- `include/sys.h`: `/dev/kd_dev` declarations.
- `include/timing_stats.h`: timing-statistics declarations.
- `include/utils.h`: logging and utility macros shared by kernel sources.
- `include/wrapper.S`: assembly wrapper that saves/restores register state and
  transfers control into generated sandbox code.

## Userspace Daemon

The `daemon/` directory builds the process that polls `/dev/kd_dev`, invokes
the translator, and writes generated JIT binaries back to the kernel.

- `daemon/Makefile`: daemon build rules.
- `daemon/daemon.c`: unified daemon implementation. Supports mode 1 and mode 2
  workspace layouts, logs translation state, invokes Python translation, and
  writes `jit.bin` back through `/dev/kd_dev`.
- `daemon/README.md`: daemon-local usage notes, mode selection, and translation
  workspace behavior.
- `daemon/0x*/`: generated translation workspaces, ignored by git. Each
  workspace contains copied asm templates, generated `jit.S`, `jit.bin`, and
  `bin.txt`.

## Translator

The `disassem/` directory contains the Python/miasm translation pipeline that
reads kernel text and emits sandbox assembly.

- `disassem/disassem.py`: main translation driver. Reads kernel bytes for an
  entry RIP, builds the control-flow view, invokes translation passes, and
  emits build artifacts.
- `disassem/memread.py`: helpers for reading kernel text, normally through
  `/proc/kcore`.
- `disassem/translation.py`: core instruction translation logic from kernel
  instructions to sandbox-safe assembly.
- `disassem/normal.py`: handling for ordinary instructions and control-flow
  cases.
- `disassem/indirect_jump.py`: indirect-jump table and miss handling support.
- `disassem/special_inst.py`: translation support for special instructions
  that need custom lowering.
- `disassem/conflict.py`: register/memory conflict handling for generated
  assembly.
- `disassem/assist.py`: helper routines used by translation passes.
- `disassem/solve_bug.py`: debugging/repair helper for known translator edge
  cases.
- `disassem/miasm_compat.py`: compatibility shims for the pinned miasm version.

## Workload Module

The `klock_module/` directory builds `klock_module.ko`, the synthetic workload
module used by benchmarks and tests.

- `klock_module/Makefile`: kbuild entry for the workload module.
- `klock_module/klock_module.c`: registers `/dev/lock_dev` and implements ten
  benchmark modes (0-9): the original spin/mutex modes plus deep spin nesting,
  OOO unlock, deterministic independent A/B queues, and nested-JIT abort
  recovery. Prints the final counter on unload.

## Benchmark

- `bench/klock_test.c`: userspace driver for `/dev/lock_dev`. Spawns worker
  threads, releases them through a shared start barrier for deterministic
  contention, and issues ioctl workloads with parameters
  `<threads> <loops> <workload> <sys_count> <mode>`.

## Test Tools

- `test_tools/test_read_kernel.py`: host/guest helper for checking whether
  kernel bytes can be read for translator debugging.

## Integration Tests

Integration tests are shell scripts under `tests/`. They load real kernel
modules and must run inside the guest with timeouts.

- `tests/common.sh`: shared test helpers for building, module load/unload,
  daemon lifecycle, dmesg assertions, JIT artifact checks, and stat parsing.
- `tests/run_all.sh`: default low-risk integration suite. Runs tests 01-06 and
  intentionally excludes opt-in `mutex_jit=1` tests.
- `tests/snapshot_test.sh`: helper for running a selected mode with QEMU
  snapshot intent. It requires a working host monitor socket and should not be
  treated as crash protection unless `savevm` succeeds.
- `tests/test_01_module_load.sh`: validates basic module build/load/unload and
  device creation without running a benchmark.
- `tests/test_02_jit_engine.sh`: validates default JIT pipeline behavior:
  endpoint resolution, hot-lock promotion, `kd_exe_add`, daemon kernel-text
  reads, `jit.S` structure, `jit.bin`, objdump output, and write-back.
- `tests/test_03_hotlock.sh`: validates hot-lock promotion state transitions
  and evidence that a lock reaches delegation.
- `tests/test_04_spinlock.sh`: validates spinlock modes 0/1/2/6/7/8 by default,
  including complete JIT artifacts, write-back, real translated execution,
  exact counters, per-lock diagnostics, zero waiter leaks, and clean dmesg.
  Recovery-only selectors cover mode 9 failure kinds and mode 8 queue-owner
  abort cleanup.
- `tests/test_05_mutex.sh`: validates mutex modes 3-5 with `mutex_jit=0`,
  requiring promotion, slowpath entry, combiner election, handoff, and clean
  dmesg.
- `tests/test_06_daemon.sh`: validates daemon workspace creation, translation
  artifacts, and kernel write-back.
- `tests/test_07a_mutex_jit_smoke.sh`: high-risk opt-in smoke test. Loads
  `mutex_jit=1`, confirms translation, then uses four synchronized one-shot
  workers to require exactly one real mutex sandbox completion and exact final
  counter accounting.
- `tests/test_07_mutex_jit.sh`: high-risk opt-in bounded mode 3 confirmation.
  Requires translation artifacts, daemon write-back, real sandbox completion,
  nonzero JIT success, exact final counter, and clean dmesg.
- `tests/test_08_mutex_jit_modes.sh`: recovery-only modes 4/5 validation. It
  independently validates every initial translation workspace and write-back,
  then attempts bounded real sandbox execution with exact counter accounting.
  Both modes passed on 2026-07-03 under `pre_mutex_jit_modes45_fix`; the test
  must remain outside `tests/run_all.sh`.

## Unit Tests

Unit tests under `tests/unit/` are userspace C tests for isolated protocol
logic. They do not load kernel modules.

- `tests/unit/Makefile`: builds and runs all unit tests.
- `tests/unit/mock_kernel.h`: small mock kernel API surface for atomics and
  assertions used by unit tests.
- `tests/unit/test_harness.h`: tiny test harness macros and result reporting.
- `tests/unit/test_exe_hash.c`: validates bounded `kd_exe_info` hash lookup,
  reuse, full-table failure, and acquire/release readiness publication.
- `tests/unit/test_hotlock_state.c`: validates hot-lock promotion and ignore
  state transitions.
- `tests/unit/test_mutex_count.c`: validates kd mutex per-CPU node count
  accounting.
- `tests/unit/test_mutex_shadow.c`: validates create-or-find lookup on lock and
  lookup-only behavior on unlock for the mutex shadow table.
- `tests/unit/test_mutex_transition.c`: validates original-to-shadow promotion
  draining rules so original mutex users cannot overlap shadow mutex users.
- `tests/unit/test_tail_encoding.c`: validates kd mutex tail encode/decode
  behavior.
- `tests/unit/test_exec_frame.c`: validates nested frame parent/LIFO rules,
  lock-stack/OOO invariants, exact completion, capacity failure, repeated-lock
  rejection, and reverse-order abort cleanup.
- `tests/unit/test_jit_call_policy.c`: validates outer/inner known-call
  continuations, unknown-call stack unwind, and the continuation bound.
- `tests/unit/test_spin_node_count.c`: validates count-neutral native fallback,
  nested node-exhaustion failure, and capacity reuse after release.

## External VM Script

- `/home/eric/vm/qemu-scripts/run_vm.sh`: host-side QEMU launch script outside
  this repository. Normal mode starts the guest with the 9p share and VFIO;
  `recovery` mode omits both for QEMU snapshots. It exports SSH on port 2222,
  writes serial output to `/tmp/qemu-serial.log`, exposes
  `/tmp/qemu-monitor.sock`, and provides an interactive `monitor` subcommand.
