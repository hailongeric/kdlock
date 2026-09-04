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
7. Mutex modes 3, 4, 5, and 11 load `kdlock_km.ko` with `mutex_jit=1` and verify
   the module parameter before any translated workload runs. Mode 5 additionally
   requires hostcall counts to equal both mutex JIT completion and waiter resume
   counts across repeated and continuous contention.
8. Modes 10 and 11 require at least one relevant artifact to load both
   `Stack_RGS` and `Stack_RCT`, require no live hardware segment operand in
   generated instructions, match runtime IPs to those artifacts, and report
   `attempts == successes > 0` with zero GS/current mismatch.

## Environment And Command

The validation ran in the recovery VM with Linux `6.1.159`, 40 online CPUs, and
the guest-local checkout at `/root/host_fs/kdlock`. The checkout is on the
guest's ext4 root filesystem rather than a shared mount. Changed files were
compared and synced selectively; the repository was not moved or recursively
overwritten. Both kernel modules, the daemon, and the benchmark were rebuilt.
All nine C unit binaries and both Python code-generation tests passed (11/11
total), including the exact two-word GS/task wrapper-layout checks.

The existing QEMU snapshots were confirmed with `info snapshots` before running
the recovery-only tests. The current complete acceptance command is:

```bash
cd /root/host_fs/kdlock
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5 10 11
```

The segment-context implementation first passed selectors 10 and 11, then the
complete 0/1/2/3/4/5 regression reran against the same wrapper, translator, and
frame changes. An initial mode 1 run exposed duplicate diagnostic-table slots
when two CPUs raced to publish the same lock address. The cmpxchg loser now
accepts the concurrently published matching address; standalone mode 1 and the
complete 0-5 rerun then passed. After adding raw FSGSBASE/SWAPGS compatibility
guards and correctly scoping bad-block rejection to fetched code ranges, the
entire `0 1 2 3 4 5 10 11` command passed again as the final run.

## Verified Results

| Mode | Translation and runtime evidence | Exact result |
| --- | --- | --- |
| 0, spin contention | The post-segment-ABI regression installed the entry, matched the runtime execution IP, completed through translated unlock, and passed all lock/frame diagnostics. | `final counter: 12009` |
| 1, nested spin A -> B | Both entries were installed; the translated A stream crossed B lock/unlock, remote nested evidence was nonzero, and the corrected diagnostic table reported one record per lock. | `final counter: 12009` |
| 2, spin hostcall | The rebuilt artifact contained the named `ktime_get` stub, did not translate the service, and performed no runtime recompilation. All four runtime entries completed; hostcall stats were `exits=4 executed=4 resumed=4 rejected=0 failed=0 limit=0`. | `final counter: 12009`; `mode2 api observations: 12009` |
| 3, mutex contention | The artifact was installed with `mutex_jit=1` and its runtime IP matched. The repeated/stress workload recorded `jit_success=687` and matching waiter resumes; readiness, JIT, frame, node, context, waiter, and slot failures/leaks were zero. | `final counter: 12934` |
| 4, nested mutex A -> B | Both A/B artifacts were installed with `mutex_jit=1` and both runtime IPs matched. The run required `jit_success=2`, `jit_resume=1`, `nested_queued=1`, `nested_remote=1`, and zero failure/leak fields. | `final counter: 12008` |
| 5, mutex hostcall | The current run used `mutex_jit=1`, matched the installed runtime entry, and recorded `jit_success=399 jit_resume=399`. Hostcall stats were `exits=399 executed=399 resumed=399 rejected=0 failed=0 limit=0`; all protocol and invariant failures were zero. | `final counter: 12582`; `mode5 api observations: 12582` |
| 10, spin GS/current | Six artifacts were complete; the two context-bearing artifacts were 2995 and 2901 bytes and contained both virtual inputs with no live segment operand. Runtime IP `0xffffffffc090aacf` matched a context artifact. A/B each recorded one JIT completion and B proxying recorded `nested_remote=1`; probe stats were `attempts=3 successes=3 failures=0`. | `final counter: 12014` |
| 11, mutex GS/current | The 1695-byte and 1601-byte A/B artifacts both contained virtual GS/current input and both runtime IPs matched. With `mutex_jit=1`, stats were `jit_success=2 jit_resume=1 nested_queued=1 nested_remote=1`; probe stats were `attempts=12002 successes=12002 failures=0`, with every protocol/invariant failure zero. | `final counter: 12008` |

Mode 3 and mode 5 completion counts are scheduling-dependent. Their contracts
require a minimum repeated-execution threshold and equality between completion
and resume counts, not the literal values above. Mode 5 further requires one
complete hostcall cycle per successful mutex JIT completion.

### Modes 10 And 11 Interpretation

These modes distinguish waiter context from the combiner context. The target
waiter initializes two per-CPU values and records its `task_struct *` before it
queues. Its translated critical section performs a `%gs:` MOV read, MOV write,
INC RMW, and `current` read while another CPU may proxy it. After returning to
the original waiter, native code validates the values on the recorded origin
CPU and the observed logical task. Artifact inspection proves those operations
use `Stack_RGS`/`Stack_RCT` and no hardware `%gs:` operand; runtime-IP matching
and nonzero success counts prove that inspected code actually ran. Mode 10 does
this through independent spin A/B queues, while mode 11 does it through the
mutex A/B queue with `mutex_jit=1`.

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
/tmp/kdlock-mode10-gs-jit-verify-20260904.log
/tmp/kdlock-mode10-gs-jit-verify-20260904-dmesg.log
/tmp/kdlock-mode11-gs-jit-verify-20260904.log
/tmp/kdlock-mode11-gs-jit-verify-20260904-dmesg.log
/tmp/kdlock-jit-acceptance-gs-final-20260904.log
/tmp/kdlock-jit-acceptance-gs-final-20260904-dmesg.log
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
independent rerun, including final modes 10 and 11. `kdlock_km`, `klock_module`,
and the translation daemon were not running after each test, and the retained
logs contained no `BUG:`, panic, double-fault, soft-lockup, or unable-to-handle
signature.
