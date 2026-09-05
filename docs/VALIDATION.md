# JIT Validation Record

Last validated: 2026-09-05

Fresh guest builds and JIT tests ran against source revision `ed00edb` on
2026-09-05, with runtime tests from 10:11 to 10:17 Asia/Shanghai (02:11 to 02:17
UTC). Only documentation changed on the host. Strict selectors passed 8/8;
extra modes 6/7/8/9 passed in a separate run after an initial mode 6 promotion
failure. Both attempts are retained below.

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
   the daemon's device writes succeed. The kernel's final-chunk diagnostic is
   supporting evidence only: it is emitted before the copy/publication completes.
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
contained neither VirtFS nor VFIO. A new snapshot,
`pre_jit_audit_20260905_1010`, was created and confirmed by `info snapshots`
before testing; the four existing recovery snapshots were retained.

All 66 code/build/test inputs matched host and guest SHA-256 hashes before the
build, so no source synchronization was needed. No repository tree was moved
or recursively replaced. The daemon was built and tested without a pre-created
`daemon/asm` template. The guest used GCC 11.4.0 and miasm 0.1.5.

Formatting/lint checks from the preceding code-cleanup run (not rerun for this
documentation-only update):

```bash
uvx ruff format --check disassem tests/unit
uvx ruff check disassem tests/unit
uvx --from shellcheck-py shellcheck -x -P SCRIPTDIR tests/*.sh
```

This run rechecked every shell script with `bash -n` in the guest and checked
documentation links, fenced blocks, and `git diff --check` on the host. No
module was built or executed on the host.

Fresh guest build and unit checks:

```bash
cd /root/host_fs/kdlock
python3 -m compileall -q disassem tests/unit
for script in tests/*.sh; do bash -n "$script" || exit; done
make -C tests/unit clean
make -C tests/unit -j"$(nproc)" run
make -C kernel_module clean && make -C kernel_module W=1 -j"$(nproc)"
make -C klock_module clean && make -C klock_module W=1 -j"$(nproc)"
make -C daemon clean && make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c \
  -o bench/klock_test -lpthread
```

All nine C unit binaries and both Python code-generation tests passed (11/11),
with miasm present and no skips. `tests/test_01_module_load.sh` also passed.
The C tests model selected algorithms rather than compile the kernel sources.
The Python tests exercise real translator code, but missing miasm currently
produces a successful `SKIP`; required runs must explicitly reject skips.
The shell syntax loop above is the corrected all-file command;
`bash -n tests/*.sh` checks only its first script, not every expanded filename.
The daemon, benchmark, and ordinary kernel source compilation produced no
compiler warnings. The remaining kernel build warnings are objtool reports
associated with the project's naked returns, stack switching, dynamic JIT
call, and UACCESS regions. They remain an unwind/stack-validation gap, not
warnings proven harmless. Guest locale warnings are unrelated to the source.

Strict translated-execution selectors ran separately to retain each mode's
kernel log and artifacts before the next test cleared them:

```bash
export KDLOCK_RECOVERY_CONFIRMED=1
unset KD_SPIN_ABORT_INJECT KD_JIT_FAULT_KIND KD_MODE8_NOT_READY
for mode in 0 1 2 3 4 5 10 11; do
  timeout --kill-after=10s 300s \
    bash tests/test_09_jit_execution_modes.sh "$mode" || exit
  # Archive this mode's dmesg, daemon log, artifacts, and hashes here.
done
```

Additional modes used the same per-mode retention procedure:

```bash
for mode in 6 7 8 9; do
  timeout --kill-after=10s 180s bash tests/test_04_spinlock.sh "$mode" || exit
done
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

Every listed artifact passed static instruction checks. Runtime-IP checks prove
at least one inspected entry per spin mode, with lock-specific/context checks
where required; they do not prove execution of all mode 1 or mode 10 artifacts.
Mutex modes 4 and 11 require both A/B entries to execute.

The IP diagnostic is emitted by `execute_cs` before calling the artifact, not
by an instruction inside `jit.bin`. It must be interpreted together with JIT
completion, zero failure/not-ready counters where required, nested-remote
evidence, and exact state results. There is no per-generation in-JIT entry/exit
trace or all-path instruction coverage yet.

Mode 3 completed 640 JIT delegations. Mode 2 completed four hostcall cycles and
mode 5 completed 398; every exit was executed and resumed without recompilation,
rejection, failure, or continuation-limit exhaustion. The mode 5 count also
matched mutex JIT completion and waiter resume. Modes 4 and 11 executed both
independent A and B translated entries and recorded remote nested execution.
Modes 10 and 11 passed their waiter GS/logical-current probes.

Spin modes outside the strict selector passed in the separate follow-up run:

| Mode | Scenario | Exact protected result |
| --- | --- | --- |
| 6 | A -> B -> C nesting | 12009 operations, 1 state, 0 failures |
| 7 | Out-of-order A/B unlock | 12009 operations, 1 state, 0 failures |
| 8 | Independent A/B contention | 12014 operations, 2 states, 0 failures |
| 9 | Nested JIT recovery topology | 12006 operations, 2 states, 0 failures |

The first mode 6 attempt failed before the translated workload: only one of
three required artifacts was generated. Its hot-lock diagnostics showed C
promoted at 24,973,040 cycles, while B/A were ignored at 25,007,630/25,009,662
cycles. `kd_hotlock_record()` tightens the shared window on C's promotion;
these values cross the resulting 25,000,000-cycle boundary. The unchanged
independent rerun generated all three artifacts and executed JIT successfully.
This is a timing-sensitive promotion/test issue, not a clean first-pass result
or proof that the issue is fixed. No test assertion was relaxed. See `TODO.md`.

The mode 9 command above did not enable `KD_SPIN_ABORT_INJECT` or
`KD_JIT_FAULT_KIND`. It validates that topology's normal execution, not the
fault-injection variants or recovery after arbitrary partial writes.

Historical coverage, not rerun this time: the preceding code-cleanup run's
default six-script suite passed 6/6. Its `mutex_jit=0` paths replayed 40001
mode 3 transitions and 20001 transitions for each of modes 4 and 5. This proves
the stronger workload remains valid for native mutex handoff as well as opt-in
translated execution.

## Result Interpretation

Each `kd_cs_state` transition updates nine words with chained dependencies.
Module exit replays the complete transition from zero and compares every field,
which detects more errors than the legacy counter. Independent physical locks
use independent states. This is not a per-request history: identical transitions
cannot distinguish a skipped request offset by a duplicated one. It does not
prove linearizability or exactly-once execution for arbitrary workloads.

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

That contract is addressing and identity for the tested variables. It does not
validate concurrent origin-CPU interrupt updates, arbitrary non-locked per-CPU
RMW, or scheduler/RCU context substitution.

Not established by this run: precise native continuation after partial writes
or completed nested sections (the preferred target, not a requirement for
memory rollback); mixed native/shadow mutex users; all-instruction/flags
correctness;
concurrent JIT replacement and module unload; real-kernel workload safety; or
speedup against native locks/TCLocks. See [TODO.md](TODO.md) for targeted tests.

## Retained Evidence

Fresh evidence is retained on both host and guest at
`/tmp/kdlock-jit-audit-20260905-1010/`:

```text
environment.log                 Kernel, mount, compiler, miasm, source, snapshot
source.sha256                   66 matching source/build/test inputs
build-unit.log                  Clean builds and 11 unit/codegen tests
module-load{,-dmesg}.log         Module load/unload test
run.sh / suite.log              Initial strict run, then first mode 6 failure
mode-{0,1,2,3,4,5,10,11}/        Successful strict selectors
mode-6/                         Preserved first failed promotion attempt
extra-run.sh / extra-suite.log  Independent follow-up run
extra-rerun/mode-{6,7,8,9}/      Successful additional selectors
extra-rerun/completed-at        Follow-up completion timestamp
snapshots.log                   Host-only snapshot inventory
post-test-health.log            Final source hashes and guest health (host copy)
```

Each mode directory contains `command.log`, `test.log`, `dmesg.log`,
`exit-status`, daemon logs, `artifacts.sha256`, and `artifacts.tar.gz`. The
runner archives generated files before later tests clean their workspaces.
The original suite stopped on mode 6 and has a nonzero exit status; its eight
strict selectors passed, and the follow-up suite exited zero. Do not collapse
these into a claim that the initial entire suite passed.

The guest also retains `/tmp/kdlock-run-all-code-cleanup-20260905.log` for the
historical default suite. Its earlier strict-suite `-dmesg.log` contains only
mode 11; use the fresh per-mode evidence above for the current JIT results.

These logs are diagnostic evidence, not substitutes for rerunning tests after
code changes. Kernel addresses and scheduling-dependent completion counts may
change between runs.

Artifact hashes and matching runtime RIPs are now retained per mode, but the
runtime protocol still lacks a generation identifier and an in-JIT trace.

## Post-test Health

After validation, the host still reported the recovery
`qemu-system-x86_64` process and the guest answered the five-second SSH health
check. No test left `kdlock_km`, `klock_module`, or the translation daemon
running, and the final kernel log contained no BUG, panic, double fault, soft
lockup, or unable-to-handle signature.
