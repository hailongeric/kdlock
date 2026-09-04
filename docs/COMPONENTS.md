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

## Documentation

- `docs/AGENTS.md`: operating manual for AI/automation sessions, including host
  vs guest boundaries, safety rules, validation order, and crash handling.
- `docs/DESIGN.md`: full architecture and protocol design for hooks,
  delegation, sandbox translation, JIT execution, and known limitations.
- `docs/JIT_REGISTER_ABI.md`: current x86-64 JIT entry/exit ABI, wrapper stack,
  physical/virtual register mapping, call frames, hostcall continuations, and
  waiter resume rules.
- `docs/COMPONENTS.md`: this file, a file-by-file component and test map.
- `docs/VALIDATION.md`: canonical latest end-to-end test procedure, evidence,
  and mode-specific interpretation.
- `docs/MODE2_HOSTCALL_IMPLEMENTATION.md`: mode 2 hostcall scope, ABI, safety
  invariants, implementation sequence, and acceptance checklist.
- `docs/TODO.md`: unfinished features and known gaps only.

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
  nested spin/mutex known-call acquire, unlock, continuation, and abort handling.
- `kernel_module/kd_exec.c`: bounded per-CPU execution-frame stack for nested
  JIT register continuations, lock ownership, completion, and abort invariants.
  A task owner prevents a suspended frame from being reused by another task on
  the same CPU.
- `kernel_module/kd_spinlock.c`: spinlock delegation protocol. Implements the
  queue, combiner path, shadow stack, waiter completion, nested/OOO unlock
  handling, and JIT execution for spinlock critical sections.
- `kernel_module/kd_mutex.c`: mutex delegation protocol. Implements kd mutex
  queueing, combiner handoff/fallback, independently reserved per-CPU waiter
  stacks, optional `mutex_jit=1` execution frames, release/acquire completion,
  local register snapshots before scheduler restoration, resume after delegated
  `mutex_unlock`, and protocol/invariant counters. A contended nested mutex uses
  a virtual waiter with a stack-owned context so a B combiner can proxy through
  `mutex_unlock(B)` and return the post-B continuation to A.
- `kernel_module/exe.c`: JIT execution engine. Manages `kd_exe_info` entries,
  executable code-block pool, endpoint resolution, allowlisted native hostcall
  dispatch/resume and diagnostics, write-back state, miss handling, and sandbox
  invocation through the assembly wrapper.
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
- `include/kd_hostcall.h`: stable hostcall IDs and service safety flags.
- `include/kd_hostcalls.def`: declarative hostcall manifest shared by the kernel
  registry and Python translator.
- `include/kd_futex.h`: futex delegation declarations.
- `include/kd_int3.h`: hot-lock/int3 declarations.
- `include/kd_lock.h`: lock hook and fallback declarations.
- `include/kd_exec.h`: nested JIT execution-frame, event, combiner snapshot,
  lock-ownership, waiter GS base, and logical-task declarations.
- `include/kd_mutex.h`: kd mutex structures and function declarations.
- `include/kd_segment.h`: x86 helper for capturing the kernel GS base of the
  current CPU or the CPU associated with a target task.
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
  entry RIP, resolves the `current_task` per-CPU offset, classifies resumable
  control calls and hostcalls, preflights segment operands, builds the
  control-flow view, invokes translation passes, and emits either executable
  code or a terminal unsupported-instruction artifact.
- `disassem/hostcall.py`: parses the shared hostcall manifest and resolves the
  service addresses available in the running kernel.
- `disassem/memread.py`: helpers for reading kernel text, normally through
  `/proc/kcore`; excludes hostcall targets from callee-table expansion.
- `disassem/translation.py`: core instruction translation logic from kernel
  instructions to sandbox-safe assembly.
- `disassem/normal.py`: ordinary instruction handling, including explicit
  waiter-GS addressing, logical `current_task` substitution, and fail-closed
  FS/unsupported-segment policy.
- `disassem/indirect_jump.py`: indirect-jump tables plus distinct hostcall and
  ordinary call-miss stub generation.
- `disassem/special_inst.py`: translation support for special instructions
  that need custom lowering.
- `disassem/conflict.py`: register/memory conflict handling for generated
  assembly, including virtual waiter GS (`RGS`) and logical task (`RCT`).
- `disassem/assist.py`: helper routines used by translation passes.
- `disassem/solve_bug.py`: debugging/repair helper for known translator edge
  cases.
- `disassem/miasm_compat.py`: compatibility shims for the pinned miasm version.

## Workload Module

The `klock_module/` directory builds `klock_module.ko`, the synthetic workload
module used by benchmarks and tests.

- `klock_module/Makefile`: kbuild entry for the workload module.
- `klock_module/klock_module.c`: registers `/dev/lock_dev` and implements twelve
  benchmark modes (0-11): the original spin/mutex modes plus deep spin nesting,
  OOO unlock, deterministic independent A/B queues, nested-JIT abort recovery,
  and spin/mutex waiter-GS context validation. Modes 2 and 5 consume the native
  time-service result after their CALL. Modes 10 and 11 execute translated
  per-CPU MOV read/write, INC RMW, and `current` reads, then report exact probe
  success/failure counts. Modes 4 and 11 expose seven synchronized mutex roles
  that independently order A and B queues. Prints final counters on unload.

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
  daemon lifecycle, dmesg assertions, JIT artifact/runtime-entry matching,
  hostcall stub validation, waiter GS/current artifact inspection, and stat
  parsing.
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
  Mode 2 additionally requires a named hostcall stub, no service callee
  translation or runtime recompilation, matching exit/execute/resume counts,
  and exact post-CALL API observations.
  Recovery-only selectors cover mode 9 failure kinds, mode 8 queue-owner abort
  cleanup, and mode 10 translated GS/current semantics under remote nested
  proxying.
- `tests/test_05_mutex.sh`: validates mutex modes 3-5 with `mutex_jit=0`,
  requiring promotion, slowpath entry, combiner election, handoff, and clean
  dmesg.
- `tests/test_06_daemon.sh`: validates daemon workspace creation, translation
  artifacts, and kernel write-back.
- `tests/test_07a_mutex_jit_smoke.sh`: high-risk opt-in smoke test. Loads
  `mutex_jit=1`, confirms translation, then uses four synchronized one-shot
  workers to require exactly one real mutex sandbox completion and exact final
  counter accounting.
- `tests/test_07_mutex_jit.sh`: high-risk opt-in repeated/stress mode 3
  confirmation. After translation becomes ready, it runs 32 deterministic
  owner/waiter rounds, four CPU-1 waiters behind a CPU-0 holder, and an 8-thread
  continuous workload. It requires repeated sandbox completion, same-CPU
  multi-slot evidence, matching completion/resume counts, exact final counter,
  and zero JIT/frame/overflow/waiter/slot-leak diagnostics.
- `tests/test_08_mutex_jit_modes.sh`: recovery-only modes 4/5/11 validation. It
  independently validates every initial translation workspace and write-back.
  Mode 4 then creates deterministic A/B queues with seven CPU-pinned roles and
  requires runtime IP matches for both A/B workspaces, outer plus inner JIT
  completion, queued/remote B evidence, exact counter accounting, and zero
  protocol failures or leaks. Mode 5 runs repeated owner/waiter rounds, a
  CPU-pinned queue, and continuous contention; it requires one hostcall cycle
  and final waiter resume per JIT completion, no runtime recompilation, exact
  counters, and zero failures or leaks. Mode 11 reuses the deterministic mode 4
  topology and additionally requires waiter-GS/current artifact and runtime
  probe evidence. The script remains outside `tests/run_all.sh`.
- `tests/test_09_jit_execution_modes.sh`: recovery-only acceptance suite for
  modes 0/1/2/3/4/5/10/11. Modes 0/1/2/10 reuse the strict spinlock execution
  checks, with mode 2 adding hostcall proof and mode 10 adding GS/current proof;
  mode 3 uses the repeated/stress mutex JIT test; modes 4/11 use deterministic
  nested-mutex JIT tests; mode 5 uses the repeated mutex hostcall test. Every
  selected mode must match runtime execution IPs to installed workspaces, not
  only generate or install an artifact.

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
- `tests/unit/test_mutex_count.c`: validates kd mutex bitmap slot reservation,
  capacity reuse, and that post-JIT registers are snapshotted before node reuse.
- `tests/unit/test_mutex_shadow.c`: validates create-or-find lookup on lock and
  lookup-only behavior on unlock for the mutex shadow table.
- `tests/unit/test_mutex_transition.c`: validates original-to-shadow promotion
  draining rules so original mutex users cannot overlap shadow mutex users.
- `tests/unit/test_tail_encoding.c`: validates kd mutex tail encode/decode
  behavior.
- `tests/unit/test_exec_frame.c`: validates nested frame parent/LIFO rules,
  lock-stack/OOO invariants, exact completion, capacity failure, repeated-lock
  rejection, reverse-order abort cleanup, two-word GS/task arguments, and
  nested context inheritance.
- `tests/unit/test_jit_call_policy.c`: validates outer/inner control-call
  continuations, allowlisted hostcall resume, forged hostcall rejection,
  unknown-call stack unwind, and the continuation bound.
- `tests/unit/test_hostcall_codegen.py`: verifies manifest loading and that
  generated hostcall/call-miss stubs use distinct exit and virtual-stack rules.
- `tests/unit/test_segment_codegen.py`: verifies GS MOV read/write and INC RMW
  lowering, logical `current_task`, FS/current-write/`SWAPGS` rejection,
  alignment NOP handling, and exact wrapper slot/argument definitions.
- `tests/unit/test_spin_node_count.c`: validates count-neutral native fallback,
  nested node-exhaustion failure, and capacity reuse after release.

## External VM Script

- `/home/eric/vm/qemu-scripts/run_vm.sh`: host-side QEMU launch script outside
  this repository. Normal mode starts the guest with the 9p share and VFIO;
  `recovery` mode omits both for QEMU snapshots. It exports SSH on port 2222,
  writes serial output to `/tmp/qemu-serial.log`, exposes
  `/tmp/qemu-monitor.sock`, and provides an interactive `monitor` subcommand.
