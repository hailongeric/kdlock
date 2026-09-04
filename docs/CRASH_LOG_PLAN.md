# Crash Log Plan

Last updated: 2026-09-04

## Goal

Make high-risk JIT tests debuggable even when the guest hangs or panics.

## Constraints

- Default tests must stay low-risk.
- `mutex_jit=1` tests remain opt-in.
- Normal QEMU mode includes VirtFS and VFIO and cannot be used for snapshots.
- High-risk tests require `run_vm.sh recovery`, a confirmed snapshot, and a
  guest-local repository at `/root/host_fs/kdlock`.
- Normal mode sees the host tree through 9p and needs no file synchronization.
  Recovery mode uses guest ext4 at the same pathname: compare hashes and `scp`
  only changed individual files; never move or recursively copy the directory.

## Phases

1. Use the host-visible QEMU monitor socket.
   - `run_vm.sh` exposes `/tmp/qemu-monitor.sock`.
   - Use `run_vm.sh monitor` to connect; detach with `Ctrl-C`, never HMP `quit`.
   - Use `savevm` / `loadvm` only after the monitor command reports success.
2. Capture QEMU serial output on the host.
   - `run_vm.sh` writes guest serial output to `/tmp/qemu-serial.log`.
3. Recover crash evidence after a reboot.
   - Read the host serial log first.
   - If the guest boots again, run `journalctl -b -1 -k` inside the guest.
4. Split opt-in JIT validation.
   - One smoke test for a single sandbox completion.
   - One bounded contention test.
   - Nested spin abort tests for FAST and QUEUE_OWNER ownership.
   - One stress test only after recovery is reliable.

## Current status

- Default JIT pipeline checks verify translation artifacts and write-back.
- `tests/test_07a_mutex_jit_smoke.sh` is the fastest runtime sandbox
  confirmation: exactly one real mutex JIT completion.
- `tests/test_07_mutex_jit.sh` remains the bounded mode 3 confirmation.
- `run_vm.sh recovery` omits VirtFS and VFIO; normal mode keeps both.
- On 2026-07-02, recovery mode created and listed `pre_mutex_jit` (about
  4.99 GiB). The corrected smoke test passed with `jit_success=1` and final
  counter `12005`; the bounded test passed with `jit_success=1` and final
  counter `14001`. No kernel error signatures were found.
- A second snapshot, `pre_mutex_jit_modes45`, protected independent mode 4 and
  mode 5 runs. Mode 4 produced a JIT page fault after nested-lock state
  corruption; mode 5 hung after repeated call misses. `loadvm` restored a
  clean, SSH-reachable guest after both failures.
- Host evidence is retained in `/tmp/kdlock-mode4-*`,
  `/tmp/qemu-serial-mode4-crash.log`, `/tmp/kdlock-mode5-*`, and
  `/tmp/qemu-serial-mode5-hang.log` for the current host boot.
- On 2026-07-03, snapshot `pre_mutex_jit_modes45_fix` protected the fixed
  mode 4/5 run. Both `tests/test_08_mutex_jit_modes.sh 4` and `5` passed with
  one sandbox completion, exact final counter accounting, and no kernel error
  signatures. Host evidence is retained in `/tmp/kdlock-mode4-pass-*` and
  `/tmp/kdlock-mode5-pass-*`.
- On 2026-09-04, nested spin recovery tests passed in recovery mode. Mode 9
  covered post-B failure plus CALL miss, IJ miss, and instruction-limit faults
  with the daemon stopped. Mode 8's not-ready topology then forced B to
  `KD_EXEC_LOCK_QUEUE_OWNER` and verified one reverse cleanup, A native retry,
  exact counter `12014`, zero waiters, and no execution-frame invariant error.
