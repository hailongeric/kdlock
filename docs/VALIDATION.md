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
6. Modes 2 and 5 contain a named allowlisted hostcall stub, never translate that
   service through `callee_table.txt`, perform no runtime recompilation, and
   report equal nonzero exit/execute/resume counts with no hostcall failure.
   Their exact API observation counters prove post-CALL instructions ran.
7. Mutex modes 3, 4, and 5 load `kdlock_km.ko` with `mutex_jit=1` and verify the
   module parameter before any translated workload runs. Mode 5 additionally
   requires hostcall counts to equal both mutex JIT completion and waiter resume
   counts across repeated and continuous contention.

## Environment And Command

The validation ran in the recovery VM with Linux `6.1.159`, 40 online CPUs, and
the guest-local checkout at `/root/host_fs/kdlock`. The checkout is on the
guest's ext4 root filesystem rather than a shared mount. Before mode 5 testing,
the three changed files were SHA256-compared and only those files were synced;
their post-copy hashes matched the host. Both kernel modules, the daemon, and
the benchmark were rebuilt from clean outputs. All nine C unit binaries and the
Python hostcall code-generation test passed (10/10 total).

The existing QEMU snapshots were confirmed with `info snapshots` before running
the recovery-only tests. The current complete acceptance command is:

```bash
cd /root/host_fs/kdlock
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5
```

The earlier mode 0/1/3/4 implementation passed those four selectors together
and independently. Mode 5 then passed a reduced orchestration run, the full
default repeated/stress run, and a final independent run that polled and
observed `mutex_jit=1` while the test was active. Selector 4 passed again after
its shared cleanup assertions were refactored, and selector 2 passed again
against the rebuilt workload module. Selectors 0/1/3 retain their prior recovery
results because the mode 5 change does not modify their runtime paths.

## Verified Results

| Mode | Translation and runtime evidence | Exact result |
| --- | --- | --- |
| 0, spin contention | Post-hostcall-change regression installed one 1197-byte `jit.bin`; the runtime lock/IP matched the workspace and all strict spin assertions passed. | `final counter: 12009` |
| 1, nested spin A -> B | Post-hostcall-change regression installed two 1331-byte binaries; the depth-1 runtime lock/IP matched a workspace and all nested continuation/queue assertions passed. | `final counter: 12009` |
| 2, spin hostcall | Post-mode-5 regression entry `0xffffffffc071ee88` produced one 1464-byte binary containing `KD_HOSTCALL id=1 symbol=ktime_get`. Service `0xffffffff81193700` was absent from the empty `callee_table.txt`; continuation `0xffffffffc071ee95` was present in the dispatcher. Only the initial JIT write-back occurred, all four runtime IPs matched the workspace, and `jit_success=4`. Hostcall stats were `exits=4 executed=4 resumed=4 rejected=0 failed=0 limit=0`; lock waiters and invariant failures were zero. | `final counter: 12009`; `mode2 api observations: 12009` |
| 3, mutex contention | One 1185-byte binary was installed with `mutex_jit=1`, and runtime IP matched its workspace. The repeated/stress workload recorded `jit_success=665`, `jit_resume=665`, and `multi_slot=3`; readiness, JIT, frame, node, context, waiter, and slot failures/leaks were zero. | `final counter: 12934` |
| 4, nested mutex A -> B | The initial 706-byte and 607-byte A/B binaries were installed with `mutex_jit=1`. Runtime IP matched both workspaces and recorded `jit_success=2`, `jit_resume=1`, `nested_queued=1`, `nested_remote=1`; all failure/leak fields were zero. | `final counter: 12008` |
| 5, mutex hostcall | The final independent run observed `mutex_jit=1`. Entry `0xffffffffc071edea` produced one 1464-byte binary containing the named `ktime_get` hostcall stub and continuation `0xffffffffc071edf7`. `callee_table.txt` was empty and exactly one JIT write-back occurred. Repeated, CPU-pinned, and 8-thread continuous contention produced 381 matching runtime entry executions and successful completions. Mutex stats were `jit_success=381 jit_resume=381 multi_slot=3 max_waiters=8`; hostcall stats were `exits=381 executed=381 resumed=381 rejected=0 failed=0 limit=0`. All readiness, JIT, frame, node, context, waiter, slot, and invariant failures/leaks were zero. | `final counter: 12582`; `mode5 api observations: 12582` |

Mode 3 and mode 5 completion counts are scheduling-dependent. Their contracts
require a minimum repeated-execution threshold and equality between completion
and resume counts, not the literal values above. Mode 5 further requires one
complete hostcall cycle per successful mutex JIT completion.

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

### Mode 5 Interpretation

Mode 5 uses the same hostcall ABI as mode 2, but the outer lock is a mutex and a
combiner executes queued waiters remotely. Each translated waiter reaches
`ktime_get`, exits through `KD_EXE_HOSTCALL`, resumes the same artifact after the
CALL, and completes at `mutex_unlock`. Equality across hostcall exits, native
executions, internal JIT resumes, mutex JIT completions, and original-waiter
resumes proves both levels of continuation occur exactly once. The exact API
observation counter proves every native and delegated critical section consumed
a nonzero return value.

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
/tmp/kdlock-mode5-jit-final-20260904.log
/tmp/kdlock-mode5-jit-final-20260904-dmesg.log
/tmp/kdlock-mode5-mutex-jit1-confirm-20260904.log
/tmp/kdlock-mode5-mutex-jit1-confirm-20260904-dmesg.log
/tmp/kdlock-mode5-safe-mode-regression-20260904.log
/tmp/kdlock-mode5-safe-mode-regression-20260904-dmesg.log
/tmp/kdlock-mode4-regression-after-mode5-20260904.log
/tmp/kdlock-mode4-regression-after-mode5-20260904-dmesg.log
/tmp/kdlock-mode2-regression-after-mode5-20260904.log
/tmp/kdlock-mode2-regression-after-mode5-20260904-dmesg.log
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
independent rerun, including the final mode 5, mode 4 regression, and mode 2
regression runs. `kdlock_km`, `klock_module`, and the translation daemon were not
running, and the final guest logs contained no `BUG:`, panic, double-fault,
soft-lockup, or unable-to-handle signature.
