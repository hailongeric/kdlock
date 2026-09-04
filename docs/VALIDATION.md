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
6. Mode 2 contains a named allowlisted hostcall stub, never translates that
   service through `callee_table.txt`, performs no runtime recompilation, and
   reports equal nonzero exit/execute/resume counts with no hostcall failure.
7. Mutex modes 3 and 4 load `kdlock_km.ko` with `mutex_jit=1` and verify the
   module parameter before any translated workload runs.

## Environment And Command

The validation ran in the recovery VM with Linux `6.1.159`, 40 online CPUs, and
the guest-local checkout at `/root/host_fs/kdlock`. Before the latest mode 2
rerun, the relevant guest files were SHA256-compared with the host checkout and
were already identical, so no copy was needed. Both kernel modules, the daemon,
and the benchmark were rebuilt from clean outputs. All nine C unit binaries and
the Python hostcall code-generation test passed (10/10 total).

The existing QEMU snapshots were confirmed with `info snapshots` before running
the recovery-only tests. The current complete acceptance command is:

```bash
cd /root/host_fs/kdlock
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4
```

The earlier mode 0/1/3/4 implementation passed those four selectors together
and independently. After adding hostcalls, selector 2 passed independently and
the shared spin translator/executor paths were regression-tested with selectors
0 and 1. Following the register-ABI audit, selector 2 was independently rerun on
2026-09-04 with the same strict acceptance script and passed again. Mutex
selectors 3/4 retain their prior recovery results; they were not rerun for the
mode 2-only change.

## Verified Results

| Mode | Translation and runtime evidence | Exact result |
| --- | --- | --- |
| 0, spin contention | Post-hostcall-change regression installed one 1197-byte `jit.bin`; the runtime lock/IP matched the workspace and all strict spin assertions passed. | `final counter: 12009` |
| 1, nested spin A -> B | Post-hostcall-change regression installed two 1331-byte binaries; the depth-1 runtime lock/IP matched a workspace and all nested continuation/queue assertions passed. | `final counter: 12009` |
| 2, spin hostcall | Entry `0xffffffffc071ee7b` produced one 1407-byte binary containing `KD_HOSTCALL id=1 symbol=ktime_get`. Service `0xffffffff81193700` was absent from the empty `callee_table.txt`; continuation `0xffffffffc071ee88` was present in the dispatcher. Only the initial JIT write-back occurred, all four runtime IPs matched the workspace, and `jit_success=4`. Hostcall stats were `exits=4 executed=4 resumed=4 rejected=0 failed=0 limit=0`; lock waiters and invariant failures were zero. | `final counter: 12009`; `mode2 api observations: 12009` |
| 3, mutex contention | One 1185-byte binary was installed with `mutex_jit=1`, and runtime IP matched its workspace. The repeated/stress workload recorded `jit_success=665`, `jit_resume=665`, and `multi_slot=3`; readiness, JIT, frame, node, context, waiter, and slot failures/leaks were zero. | `final counter: 12934` |
| 4, nested mutex A -> B | The initial 706-byte and 607-byte A/B binaries were installed with `mutex_jit=1`. Runtime IP matched both workspaces and recorded `jit_success=2`, `jit_resume=1`, `nested_queued=1`, `nested_remote=1`; all failure/leak fields were zero. | `final counter: 12008` |

The mode 3 completion count is scheduling-dependent; the contract requires a
minimum repeated-execution threshold and equality between completion and resume
counts, not the literal value 665. The strengthened all-mode run observed 702
completions and the independent rerun observed 665; both satisfied the same
assertions.

As an additional cross-lock regression for the shared hostcall executor,
`tests/test_08_mutex_jit_modes.sh 5` passed with a 1332-byte artifact,
`exits=1 executed=1 resumed=1 rejected=0 failed=0 limit=0`, and
`final counter: 12005`. This bounded run does not replace the open mode 5
repeated/stress coverage task.

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

### Mode 2 Interpretation

Mode 2 translates the code before and after its time API call but does not
translate `ktime_get`. The CALL stub preserves the virtual return RIP and exits
with `KD_EXE_HOSTCALL`; the kernel registry invokes the typed native handler,
writes the timestamp to `regs->ax`, consumes the virtual CALL frame, and invokes
the same artifact at the post-CALL RIP. Equal exit/execute/resume counts prove
all four delegated requests crossed both sandbox boundaries. The exact API
observation counter proves instructions after the CALL consumed a nonzero
result, while one total JIT write-back proves no service miss reached the daemon.

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
/tmp/kdlock-mode2-hostcall-output-20260904.log
/tmp/kdlock-mode2-hostcall-dmesg-20260904.log
/tmp/kdlock-mode2-jit-rerun-20260904.log
/tmp/kdlock-mode2-jit-rerun-20260904-dmesg.log
/tmp/kdlock-mode5-hostcall-regression-20260904.log
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
answered a five-second SSH health check after the complete suite and every
independent rerun, including the final mode 2 rerun. `kdlock_km`, `klock_module`,
and the translation daemon were not running, and the final guest log contained
no `BUG:`, panic, double-fault, soft-lockup, or unable-to-handle signature.
