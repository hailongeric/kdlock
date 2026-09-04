# JIT Validation Record

Last validated: 2026-09-04

This is the canonical record for the latest end-to-end validation. Architecture
belongs in `DESIGN.md`, operating and recovery procedures belong in `AGENTS.md`,
and unfinished work belongs in `TODO.md`.

## Acceptance Contract

Generating `jit.S` or writing `jit.bin` back to the kernel is not sufficient.
For every selected mode, `tests/test_09_jit_execution_modes.sh` requires:

1. Every expected workspace contains a non-empty `jit.S`, `jit.bin`, and
   `bin.txt`, and the generated entry label matches the requested kernel RIP.
2. The daemon read kernel text and the kernel logged `write to kernel`.
3. A contended workload logged an execution IP matching the installed workspace
   entry and completed through the matching unlock endpoint (`jit_success > 0`).
4. The workload's final counter is exact, proving the critical-section side
   effect was neither skipped nor executed twice.
5. Execution frames, queues, and node slots drain completely, with no kernel
   error or JIT/protocol failure diagnostics.
6. Mutex modes 3 and 4 load `kdlock_km.ko` with `mutex_jit=1` and verify the
   module parameter before any translated workload runs.

## Environment And Command

The validation ran in the recovery VM with Linux `6.1.159`, 40 online CPUs, and
the guest-local checkout at `/root/host_fs/kdlock`. Before testing, individual
changed files were synchronized into that checkout and both kernel modules were
rebuilt. All nine user-space unit binaries passed.

The existing QEMU snapshots were confirmed with `info snapshots` before running
the recovery-only tests. The complete acceptance command was:

```bash
cd /root/host_fs/kdlock
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 3 4
```

The complete command passed all four selectors. Each selector was then rerun
independently so its final `dmesg` evidence could be retained.

## Verified Results

| Mode | Translation and runtime evidence | Exact result |
| --- | --- | --- |
| 0, spin contention | One 1140-byte `jit.bin` was installed. Runtime IP matched that workspace and the translated entry completed four times: `slowpath=6`, `combiner=1`, `jit_success=4`, `jit_not_ready=0`, `waiters=0`. | `final counter: 12009` |
| 1, nested spin A -> B | A 1271-byte and a 1274-byte binary were installed. Runtime lock and IP matched the depth-1 A workspace, and A completed four times (`jit_success=4`); while it ran, B recorded `nested_lock=4`, `nested_unlock=4`, `native_fallback=0`, and both queues drained. | `final counter: 12009` |
| 3, mutex contention | One 1185-byte binary was installed with `mutex_jit=1`, and runtime IP matched its workspace. The repeated/stress workload recorded `jit_success=665`, `jit_resume=665`, and `multi_slot=3`; readiness, JIT, frame, node, context, waiter, and slot failures/leaks were zero. | `final counter: 12934` |
| 4, nested mutex A -> B | The initial 706-byte and 607-byte A/B binaries were installed with `mutex_jit=1`. Runtime IP matched both workspaces and recorded `jit_success=2`, `jit_resume=1`, `nested_queued=1`, `nested_remote=1`; all failure/leak fields were zero. | `final counter: 12008` |

The mode 3 completion count is scheduling-dependent; the contract requires a
minimum repeated-execution threshold and equality between completion and resume
counts, not the literal value 665. The strengthened all-mode run observed 702
completions and the independent rerun observed 665; both satisfied the same
assertions.

### Mode 1 Interpretation

Mode 1 intentionally does not start a second top-level B combiner. The A sandbox
contains the critical-section instruction stream. When that stream reaches
`spin_lock(B)` and `spin_unlock(B)`, the high-level known-call handler acquires
and releases B, then resumes the same translated A stream. Therefore A owns the
`jit_success` count, while B's `nested_lock`/`nested_unlock` counters prove that
the translated stream crossed both nested lock boundaries without native
fallback. The exact final counter proves the code between those boundaries ran
once per delegated waiter. Independent remote B queue execution is a separate
mode 8 topology.

### Mode 4 Interpretation

Mode 4 does force independent A and B queues. A direct A waiter executes the A
translation until the contended `mutex_lock(B)`. A B combiner then executes the
virtual nested waiter from B's translated entry through `mutex_unlock(B)`, after
which A resumes and reaches `mutex_unlock(A)`. Two distinct runtime entry RIPs,
two successful completions, and `nested_remote=1` establish that both translated
segments executed.

## Retained Guest Evidence

The independent-run `dmesg` snapshots are retained in the recovery guest:

```text
/tmp/kdlock-mode0-jit-verify-20260904.log
/tmp/kdlock-mode1-jit-verify-20260904.log
/tmp/kdlock-mode3-jit-verify-20260904.log
/tmp/kdlock-mode4-jit-verify-20260904.log
```

The complete strengthened-suite output is
`/tmp/kdlock-jit-acceptance-strict-20260904.log`; per-mode assertion output is
stored as `/tmp/kdlock-mode<mode>-strict-output-20260904.log`.

These files are diagnostic evidence, not substitutes for rerunning the tests
after code changes. Module addresses and completion counts may differ on later
runs.

## Post-test Health

The host still reported the recovery `qemu-system-x86_64` process and the guest
answered a five-second SSH health check after both the complete suite and the
independent reruns. `kdlock_km`, `klock_module`, and the translation daemon were
not running, and the final guest log contained no `BUG:`, panic, double-fault,
soft-lockup, or unable-to-handle signature.
