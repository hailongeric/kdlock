# JIT Validation Record

Last validated: 2026-09-05

This is the canonical record for the latest end-to-end validation. Architecture
belongs in `DESIGN.md`, register and continuation rules belong in
`JIT_REGISTER_ABI.md`, operating procedures belong in `AGENTS.md`, and open
work belongs in `TODO.md`.

## Acceptance Contract

Generating `jit.S` or installing `jit.bin` is not enough. A JIT mode passes only
when all applicable checks below succeed:

1. Every expected workspace contains non-empty `jit.S`, `jit.bin`, and
   `bin.txt` files with the requested kernel entry RIP.
2. The translator reports a nonzero structured kernel-text read summary, and
   the kernel reports that the completed binary was installed.
3. Runtime diagnostics contain an executed JIT IP matching an inspected
   workspace and a successful completion through the expected unlock endpoint.
4. Executable generated assembly contains the complex workload's branch,
   rotate, multiply, scaled-index access, and dependent state writes.
5. Native replay matches every protected sequence, sum, branch, rotate, lane,
   and commit field, with exact operation and active-state counts.
6. Execution frames, lock queues, and node slots drain completely, with no
   kernel error or JIT/protocol failure diagnostic.
7. Modes 2 and 5 contain a named `ktime_get` hostcall stub, perform no runtime
   recompilation, and report equal nonzero exit, execute, and resume counts.
8. Mutex modes 3, 4, 5, and 11 verify `mutex_jit=1` before translated execution.
   Mode 5 also requires hostcall, JIT completion, and waiter resume counts to
   match.
9. Modes 10 and 11 load both `Stack_RGS` and `Stack_RCT`, retain no live hardware
   segment operand, execute the inspected context artifact, and report no
   GS/current mismatch.

## Environment And Commands

Validation used the recovery VM with Linux `6.1.159` and 40 online CPUs. The
guest-local checkout was `/root/host_fs/kdlock` on ext4. The running QEMU command
contained neither VirtFS nor VFIO, and `info snapshots` confirmed four recovery
snapshots before the high-risk tests.

Changed files were hash-compared and copied individually. No repository tree was
moved or recursively replaced. The daemon was built and tested without a
pre-created `daemon/asm` template.

Host-side source checks (no module execution on the host):

```bash
uvx ruff format --check disassem tests/unit
uvx ruff check disassem tests/unit
uvx --from shellcheck-py shellcheck -x -P SCRIPTDIR tests/*.sh
bash -n tests/*.sh
git diff --check
```

Build and unit checks:

```bash
cd /root/host_fs/kdlock
python3 -m compileall -q disassem tests/unit
make -C tests/unit clean
make -C tests/unit -j"$(nproc)" run
make -C kernel_module clean && make -C kernel_module W=1 -j"$(nproc)"
make -C klock_module clean && make -C klock_module W=1 -j"$(nproc)"
make -C daemon clean && make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c \
  -o bench/klock_test -lpthread
```

All nine C unit binaries and both Python code-generation tests passed (11/11).
The daemon, benchmark, and ordinary kernel source compilation produced no
compiler warnings. The remaining kernel build warnings are objtool reports
caused by the project's deliberate naked returns, stack switching, dynamic JIT
call, and UACCESS regions. Guest locale warnings are unrelated to the source.

Strict translated-execution suite:

```bash
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5 10 11
```

Additional and default coverage:

```bash
bash tests/test_04_spinlock.sh 9
bash tests/run_all.sh
```

## Verified Results

| Mode | JIT artifact bytes | Exact protected result |
| --- | ---: | --- |
| 0 | 1688 | 12009 operations, 1 state, 0 replay failures |
| 1 | 1774 + 1774 | 12009 operations, 1 state, 0 replay failures |
| 2 | 1844 | 12009 operations/API observations, 0 replay failures |
| 3 | 1688 | 12934 operations, 1 state, 0 replay failures |
| 4 | 1177 + 1078 | 12008 operations, 2 states, 0 replay failures |
| 5 | 1844 | 12582 operations/API observations, 0 replay failures |
| 10 | 1053 + 1053 + 3479 + 3385 + 1774 + 1774 | 12014 operations, 2 states, 0 replay failures |
| 11 | 1999 + 1905 | 12008 operations, 2 states, 0 replay failures |

Every listed artifact passed static instruction checks and runtime-IP matching.
Mode 3 completed 618 JIT delegations. Mode 2 completed four hostcall cycles and
mode 5 completed 368; every exit was executed and resumed without recompilation,
rejection, failure, or continuation-limit exhaustion. The mode 5 count also
matched mutex JIT completion and waiter resume. Modes 4 and 11 executed both
independent A and B translated entries and recorded remote nested execution.
Modes 10 and 11 passed their waiter GS/logical-current probes.

Spin modes outside the strict selector also passed:

| Mode | Scenario | Exact protected result |
| --- | --- | --- |
| 6 | A -> B -> C nesting | 12009 operations, 1 state, 0 failures |
| 7 | Out-of-order A/B unlock | 12009 operations, 1 state, 0 failures |
| 8 | Independent A/B contention | 12014 operations, 2 states, 0 failures |
| 9 | Nested JIT recovery topology | 12006 operations, 2 states, 0 failures |

The default six-script suite passed 6/6. Its `mutex_jit=0` paths replayed 40001
mode 3 transitions and 20001 transitions for each of modes 4 and 5. This proves
the stronger workload remains valid for native mutex handoff as well as opt-in
translated execution.

## Result Interpretation

Each `kd_cs_state` transition updates nine words with chained dependencies. A
partial, skipped, duplicated, or reordered execution cannot hide behind the
legacy counter because module exit replays the complete transition from zero
and compares every field. Independent physical locks use independent states.

Mode 1 keeps one outer A translation active while known-call handling crosses
B lock/unlock. Mode 4 instead creates independent A and B mutex queues and
requires both translated entries to execute. Modes 2 and 5 preserve a virtual
CALL frame while native `ktime_get` runs, then dispatch back into the same
artifact at the post-CALL RIP. Exact API-observation counts prove that code after
the call executed.

Modes 10 and 11 run while the combiner may differ from the original waiter.
Generated code must use the captured waiter GS base and logical task arguments,
not the combiner's hardware GS/current state. Artifact checks and runtime probes
jointly establish this contract.

## Retained Guest Evidence

The current recovery guest retains these logs:

```text
/tmp/kdlock-code-cleanup-build-20260905.log
/tmp/kdlock-module-load-code-cleanup-20260905.log
/tmp/kdlock-run-all-code-cleanup-20260905.log
/tmp/kdlock-jit-modes-code-cleanup-20260905.log
/tmp/kdlock-jit-modes-code-cleanup-20260905-dmesg.log
/tmp/kdlock-mode9-code-cleanup-20260905.log
```

These logs are diagnostic evidence, not substitutes for rerunning tests after
code changes. Kernel addresses and scheduling-dependent completion counts may
change between runs.

## Post-test Health

After validation, the host still reported the recovery
`qemu-system-x86_64` process and the guest answered the five-second SSH health
check. No test left `kdlock_km`, `klock_module`, or the translation daemon
running, and the final kernel log contained no BUG, panic, double fault, soft
lockup, or unable-to-handle signature.
