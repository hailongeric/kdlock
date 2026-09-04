# Plan

Last updated: 2026-09-04

## Latest Overall Status

The TCLock-style nested spinlock JIT plan is complete. The authoritative phased
checklist and evidence are in `docs/NESTED_SPIN_JIT_TASKS.md`.

- Explicit per-CPU execution frames preserve A while B/C enter kdlock's own
  fastpath, queue, combiner, OOO unlock, and continuation paths.
- Translation readiness is acquire/release published; incomplete B artifacts
  receive safe queue ownership instead of partial JIT execution.
- Failure cleanup releases nested locks in reverse order, restores combiner
  state once, waits for native A ownership, and resumes the original CS entry.
- Modes 0/1/2/6/7/8 pass by default. Recovery mode 9 passes post-lock and
  CALL/IJ/instruction-limit faults; mode 8 additionally passes queue-owner abort.
- Nine unit binaries and all six scripts in `tests/run_all.sh` passed on
  2026-09-04. Mode 0 and mode 1 both executed validated translation artifacts.
- Final VM state was SSH-reachable with no kdlock modules or daemon running and
  no dmesg crash signatures.

## Initial Mutex Recovery Task

Confirm whether the mutex JIT smoke/recovery task is complete:

- Add `tests/test_07a_mutex_jit_smoke.sh` to confirm one real mutex JIT sandbox
  execution.
- Do not add a host recovery wrapper.
- Modify `/home/eric/vm/qemu-scripts/run_vm.sh` directly to expose a QEMU
  monitor socket for host-side snapshot/recovery commands.
- Keep high-risk `mutex_jit=1` runtime tests opt-in.

## Checklist

- [x] Verify `tests/test_07a_mutex_jit_smoke.sh` exists and checks exactly one
      real sandbox completion.
- [x] Verify no host recovery wrapper remains in the repo.
- [x] Verify `/home/eric/vm/qemu-scripts/run_vm.sh` exposes
      `/tmp/qemu-monitor.sock`.
- [x] Run static checks only; do not run high-risk `mutex_jit=1` tests unless
      explicitly requested.
- [x] Summarize completion status and remaining risk.

## Status

Task implementation is complete at the static/code level:

- `tests/test_07a_mutex_jit_smoke.sh` exists, is executable, stays out of
  `tests/run_all.sh`, enables `mutex_jit=1`, forces translation, checks daemon
  kernel-text read and JIT artifacts, then requires exactly one sandbox
  completion with `jit_success=1` and exact final counter accounting.
- No host recovery wrapper remains in the repository.
- `/home/eric/vm/qemu-scripts/run_vm.sh` directly exposes
  `/tmp/qemu-monitor.sock` through `-monitor unix:/tmp/qemu-monitor.sock,server,nowait`.
- Static checks passed:
  `bash -n tests/common.sh tests/test_07a_mutex_jit_smoke.sh tests/test_07_mutex_jit.sh tests/run_all.sh tests/snapshot_test.sh`
  and `git diff --check`.

Remaining risk:

- The high-risk runtime smoke test was not run in this confirmation pass.
- QEMU monitor socket support is configured for the next VM start, but recovery
  is only proven after a host-side `savevm` command succeeds for the current VM
  configuration.

## Previous Mutex JIT Runtime Task

Run mutex JIT correctness validation after explicitly requested by the user.

Planned validation order:

- [x] Confirm current host/guest recovery conditions before enabling
      `mutex_jit=1`.
- [x] Run low-risk static/build checks in the guest.
- [x] Run default low-risk integration checks needed as baseline.
- [x] If recovery is confirmed, run `tests/test_07a_mutex_jit_smoke.sh` first.
- [x] Only if the smoke test passes and the guest remains healthy, consider the
      heavier `tests/test_07_mutex_jit.sh`.
- [x] Record dmesg/error evidence and final result.

Initial blocker (resolved):

- `/tmp/qemu-monitor.sock` is missing on the host.
- SSH to `127.0.0.1:2222` is refused.
- No guest-side tests have been run in this pass because the VM is currently
  unreachable. Start/restart of QEMU requires explicit user confirmation.

2026-07-02 update:

- User explicitly authorized starting QEMU with the updated `run_vm.sh`.
- Next action is to check for an existing QEMU instance/port 2222 listener, then
  start the VM if none is present.
- QEMU started successfully; `/tmp/qemu-monitor.sock` exists and SSH on port
  2222 is reachable.
- First guest project command after VM start completed:
  `cd /root/host_fs/kdlock && bash setup.sh`.
- Low-risk guest build/static checks passed: unit tests, Python byte-compile,
  `kernel_module`, `klock_module`, `daemon`, and `bench/klock_test`.
- Focused low-risk integration baseline passed: `test_01_module_load.sh`,
  `test_02_jit_engine.sh`, and `test_05_mutex.sh` with default
  `mutex_jit=0`.
- Host monitor is reachable with `sudo`, but `savevm pre_mutex_jit` failed:
  `Migration is disabled when VirtFS export path '/home/eric/vm/vm-shared' is
  mounted in the guest using mount_tag 'hostshare'`.
- Recovery is therefore not confirmed for the current VM configuration. Do not
  run `mutex_jit=1` tests unless the user explicitly accepts no-snapshot crash
  risk or the VM is relaunched without the blocking VirtFS configuration.
- Operator error: a later HMP command included `quit`, which exits QEMU rather
  than merely closing the monitor client. QEMU stopped; SSH port 2222 and the
  monitor socket disappeared. Restart QEMU using the previously authorized
  `run_vm.sh`, and do not send `quit` to HMP in future monitor probes.
- QEMU was restarted using the authorized `run_vm.sh`; SSH and monitor socket
  recovered.
- First guest project command after restart completed again:
  `cd /root/host_fs/kdlock && bash setup.sh`.
- Cleanup after restart unloaded `klock_module`/`kdlock_km`; final module check
  was empty and `DMESG_ERRORS=0`.
- Final status: `mutex_jit=1` runtime tests were not run because QEMU `savevm`
  is blocked by the mounted VirtFS share in the current VM configuration.

## Recovery Follow-up

- [x] Recheck current QEMU/SSH state.
- [x] Determine whether QEMU 6.2 supports snapshot migration with the existing
      VirtFS export.
- [x] Select a recovery method that preserves crash evidence and does not add a
      host wrapper.
- [x] Re-establish a clean guest and run `test_07a_mutex_jit_smoke.sh` only
      after recovery requirements are satisfied.
- [x] Update this plan with the result.

Selected recovery method:

- Add a recovery mode directly to `run_vm.sh`; do not add a wrapper.
- Normal mode keeps the existing VirtFS and VFIO devices.
- Recovery mode omits both VirtFS and VFIO because either can block QEMU
  save/restore.
- Recovery mode uses the existing guest-root copy at `/root/host_fs/kdlock`.
  Compare hashes and sync only individual changed files; do not move or
  recursively copy the repository.

Recovery validation result:

- `run_vm.sh recovery` boots without VirtFS and VFIO.
- The repository was copied to the guest root disk at
  `/root/host_fs/kdlock`; that path is backed by `/dev/sda1` ext4.
- Host serial output is persisted at `/tmp/qemu-serial.log`.
- The monitor socket is owned by the launching user and can be reached with
  `run_vm.sh monitor`.
- `savevm pre_mutex_jit` completed without an error; `info snapshots` reports
  `pre_mutex_jit` with a VM state size of approximately 4.99 GiB.
- First `test_07a_mutex_jit_smoke.sh` run failed safely: translation/artifact
  checks passed and the final counter was correct (`12005`), but the smoke
  workload produced `slowpath=0`, `combiner=0`, and `jit_success=0`. Four
  threads with one loop did not create real mutex contention.
- A start barrier was added to `bench/klock_test.c`, and the smoke workload was
  changed to four synchronized threads with one long critical section.
- The corrected `test_07a_mutex_jit_smoke.sh` passed with `slowpath=3`,
  `combiner=1`, `jit_success=1`, exact final counter `12005`, and no dmesg
  kernel error signatures.
- `test_07_mutex_jit.sh` then passed with `slowpath=9`, `combiner=4`,
  `handoff=3`, `jit_success=1`, exact final counter `14001`, and no dmesg
  kernel error signatures.
- Shared benchmark regressions passed: `test_04_spinlock.sh` and
  `test_05_mutex.sh` (modes 3/4/5 with default `mutex_jit=0`).
- Final guest state: SSH healthy, no kdlock/workload modules loaded,
  `DMESG_ERRORS=0`, and `pre_mutex_jit` still listed by QEMU.

## Historical Mutex JIT Modes 4/5 Failure (Resolved)

This section records the pre-fix failure. It is superseded by the implementation
and passing validation in "Mutex JIT Modes 4/5 Implementation Follow-up" below.

- [x] Add an opt-in recovery-protected test for nested mutex mode 4 and
      API-in-mutex mode 5.
- [x] Make mode 5 expose an exact completed-critical-section counter rather
      than relying on a time-derived accumulator.
- [x] Validate every required JIT artifact/write-back before contention.
- [x] Run mode 4 first; collect translation, sandbox, counter, and dmesg
      evidence.
- [x] Restore the recovery snapshot after mode 4, then run mode 5 independently.
- [x] Run affected default regressions with `mutex_jit=0`.
- [x] Update documentation with pass/fail status and remaining limitations.

Preparation status:

- `test_08_mutex_jit_modes.sh` added with independent `4`, `5`, and `all`
  selectors.
- API modes now retain the `ktime_get_ns()` call but use `global_counter` as
  an exact completed-critical-section count.
- Default `test_05_mutex.sh` passed for modes 3/4/5 after the workload change.
- Recovery snapshot `pre_mutex_jit_modes45` was created and listed by QEMU.

Mode 4 result:

- Two initial JIT workspaces were generated and validated.
- The first two nested sandbox attempts returned status `3` and logged
  `kd_mutex_unlock: unexpected locked state 0` after call-miss/fallback.
- A later attempt caused a kernel page fault in JIT code at CR2 `0x20b40`.
- Crash evidence was copied to host `/tmp` as
  `kdlock-mode4-crash-dmesg.log`, `kdlock-mode4-daemon.log`,
  `kdlock-mode4-jit-artifacts.tgz`, and `qemu-serial-mode4-crash.log`.
- `loadvm pre_mutex_jit_modes45` succeeded; SSH recovered with no loaded test
  modules and `DMESG_ERRORS=0` in the restored state.
- At this pre-fix point, mode 4 was not correct and remained unsupported with
  `mutex_jit=1`.

Mode 5 result:

- One initial JIT workspace was generated and validated.
- Two sandbox attempts returned status `3` (call miss), causing the daemon to
  extend and rewrite the translation each time.
- The benchmark then became an unreaped zombie and the test did not complete.
  No Oops signature was present, but no successful sandbox completion or exact
  counter result was produced.
- Hang evidence was copied to host `/tmp` as
  `kdlock-mode5-hang-dmesg.log`, `kdlock-mode5-daemon.log`,
  `kdlock-mode5-jit-artifacts.tgz`, and `qemu-serial-mode5-hang.log`.
- `loadvm pre_mutex_jit_modes45` succeeded again; SSH recovered with no loaded
  test modules and no kernel error signatures in the restored state.
- At this pre-fix point, mode 5 was not correct and remained unsupported with
  `mutex_jit=1`.

Conclusion at that point (superseded):

- Translation, kernel-text acquisition, artifact generation, and kernel
  write-back are observable for both modes, but end-to-end sandbox execution
  is not correct.
- Do not rerun modes 4/5 merely to reconfirm this result. Further runs require
  a code fix, the recovery VM, and a fresh snapshot.
- Default regressions passed after the exact-counter workload change:
  `test_04_spinlock.sh` passed modes 0/1/2 and `test_05_mutex.sh` passed modes
  3/4/5 with `mutex_jit=0`. Final module checks were empty and dmesg contained
  no kernel error signatures.
- Test scripts now use a five-second forced-kill grace period after timeout;
  the mode 4/5 diagnostic also stops immediately on an unexpected mutex state.

## Mutex JIT Modes 4/5 Implementation Follow-up

- [x] Identify why mode 4 call-miss/fallback corrupts nested mutex state.
- [x] Identify why mode 5 remains in call-miss/rewrite and then hangs.
- [x] Implement missing nested/call-miss-safe mutex JIT logic.
- [x] Run low-risk build, unit, and default `mutex_jit=0` regressions.
- [x] Re-run `test_08_mutex_jit_modes.sh` only in recovery mode after a fresh
      snapshot confirms rollback is available.
- [x] Update README/TODO/AGENTS with the new pass/fail state.

Initial hypothesis:

- Mode 4 fails because sandbox fallback returns to the translated nested
  `mutex_lock`/`mutex_unlock` stream after a call miss without preserving the
  outer kd-mutex ownership model. The inner lock may be acquired through the
  shadow path while the fallback/unlock path observes a Linux mutex that is not
  actually locked by the current task.
- Mode 5 likely lacks complete handling for kernel API calls reached from the
  mutex JIT sandbox. The daemon can extend translations after misses, but the
  kernel-side execution path treats repeated call misses as retryable without a
  bounded fallback/resume policy for API-in-CS code.

Implemented so far:

- `kd_exe_on_call_hl_entry()` now keeps a stable entry RIP while allowing
  continuation from `regs->ip`. This lets a mutex JIT run resume at a call's
  return address after the kernel handles a known call.
- Mutex JIT completion is now target-aware: only `mutex_unlock(outer_mutex)`
  returns `KD_EXE_RUN_TO_UNLOCK`. Inner mutex unlocks are not mistaken for the
  end of the outer critical section.
- Known in-CS calls are handled in kernel instead of being blindly translated:
  nested `mutex_lock` uses a non-sleeping shadow-mutex trylock, nested
  `mutex_unlock` releases the matching shadow mutex, and `ktime_get()` /
  `ktime_get_ns()` write the return value into `regs->ax`.
- Unknown direct-call misses now restore `Stack_RSP` after undoing the
  translator's simulated CALL push, so fallback no longer resumes the waiter
  with a polluted stack.
- The translator emits an entry dispatch table, so repeated sandbox calls can
  start from either the original CS entry or a continuation label.
- The translator now also emits continuation labels for known direct-call
  return addresses. This prevents the first nested mutex sandbox from
  executing side effects and then falling back just because the return point
  was not a block entry.
- `mutex_unlock` is no longer treated as a global non-return function by the
  translator. Outer mutex completion is decided by the kernel endpoint check;
  inner mutex unlocks must retain their fall-through path.
- Kernel-side known-call continuation is bounded to 16 passes.  If a translated
  mutex CS keeps returning to known-call handling without reaching the outer
  `mutex_unlock`, the sandbox returns an error instead of spinning forever in
  the combiner path.
- The daemon now starts as a separate process group in tests and is stopped by
  process group, preventing orphaned translator children from losing their
  workspace when the next test removes `daemon/0x*` directories. Daemon command
  history is recorded only after workspace update and compilation succeed.
- The legacy manual call-miss insertion helper now applies the same simulated
  CALL unwind as the generated missing-callee table.
- `test_jit_call_policy` covers outer unlock completion, nested lock/unlock
  continuation, API continuation, unknown-call stack unwind policy, and the
  bounded continuation limit.

Validation result:

- `python3 -m py_compile` for translator modules.
- `bash -n` for updated test scripts.
- `make -C tests/unit clean && make -C tests/unit run`; all seven unit-test
  binaries that existed at this stage passed, including the updated
  `test_jit_call_policy`.
- `git diff --check`.
- In recovery VM, Python/shell static checks, unit tests, `kernel_module`,
  `klock_module`, daemon, and benchmark builds passed.
- Default `test_05_mutex.sh` passed modes 3/4/5 with `mutex_jit=0` after the
  final translator change.
- Snapshot `pre_mutex_jit_modes45_fix` was created and listed by QEMU. `loadvm`
  restored clean state between high-risk runs.
- `tests/test_08_mutex_jit_modes.sh 4` passed with two validated JIT
  workspaces and one real nested mutex sandbox completion.
- `tests/test_08_mutex_jit_modes.sh 5` passed with one validated JIT workspace
  and one real API-in-mutex sandbox completion.
- Final guest state: no kdlock modules loaded, `DMESG_ERRORS=0`, and
  `pre_mutex_jit_modes45_fix` still listed.
- Host evidence: `/tmp/kdlock-mode4-pass-*`, `/tmp/kdlock-mode5-pass-*`, plus
  intermediate diagnostic evidence under `/tmp/kdlock-mode4-quiescence-*` and
  `/tmp/kdlock-mode4-counter-*`.

2026-07-04 explicit `mutex_jit=1` rerun:

- Re-read this plan before operating, then confirmed the recovery VM, QEMU
  monitor, and `pre_mutex_jit_modes45_fix` snapshot were available.
- Compared host/guest files and synchronized the required changed files into
  the recovery VM before rebuilding the kernel modules, daemon, and benchmark.
- Restored `pre_mutex_jit_modes45_fix` before each high-risk run.
- `tests/test_07_mutex_jit.sh` passed, confirming real mode 3 mutex JIT
  sandbox execution. Host evidence: `/tmp/kdlock-rerun-mode3-dmesg.log` and
  `/tmp/kdlock-rerun-mode3-artifacts.tgz`.
- `tests/test_08_mutex_jit_modes.sh 4` passed, confirming real nested mutex
  JIT sandbox execution with `mutex_jit=1`. Host evidence:
  `/tmp/kdlock-rerun-mode4-dmesg.log`,
  `/tmp/kdlock-rerun-mode4-daemon.log`, and
  `/tmp/kdlock-rerun-mode4-artifacts.tgz`.
- `tests/test_08_mutex_jit_modes.sh 5` passed, confirming real API-in-mutex
  JIT sandbox execution with `mutex_jit=1`. Host evidence:
  `/tmp/kdlock-rerun-mode5-dmesg.log`,
  `/tmp/kdlock-rerun-mode5-daemon.log`, and
  `/tmp/kdlock-rerun-mode5-artifacts.tgz`.
- Final guest check after the rerun: no kdlock modules loaded,
  `DMESG_ERRORS=0`, and `pre_mutex_jit_modes45_fix` still listed by QEMU.
