# Mode 2 JIT Hostcall Implementation Plan

Last updated: 2026-09-04

Status: implemented and independently revalidated on 2026-09-04. Exact runtime
addresses, counters, commands, and retained guest logs are recorded in
[`VALIDATION.md`](VALIDATION.md).

## 1. Objective

Mode 2 validates a spinlock critical section that is translated and executed by
the JIT sandbox while selected kernel APIs execute natively in the trusted
kernel module. A selected API call must not cause the daemon to translate the
API implementation into the sandbox.

The required execution sequence is:

```text
translated critical-section segment A
        |
        | CALL to an allowlisted service
        v
KD_EXE_HOSTCALL exit with target RIP and virtual return address intact
        |
        v
typed kernel hostcall dispatcher executes the native service
        |
        | writes ABI return registers and consumes the virtual CALL frame
        v
same JIT artifact resumes at the instruction after CALL
        |
        v
translated critical-section segment B -> outer spin_unlock
```

The outer delegated lock remains owned throughout the hostcall. A successful
hostcall must not release the lock, start a second top-level translation, ask
the daemon to recompile, or retry the whole critical section natively.

## 2. Scope

This implementation completes the hostcall mechanism and validates it with the
existing mode 2 `ktime_get_ns()` workload. The initial allowlist contains:

- `ktime_get`
- `ktime_get_ns`, when the running kernel exports a standalone symbol

Both services have a fixed signature, are safe in atomic context, do not depend
on the delegated waiter's `current`, and have no externally visible side effect.

Raw variadic `printk()` is deliberately out of scope for this phase. A future
logging service must use a fixed signature and bounded data, preferably writing
to a per-CPU buffer for deferred output. Arbitrary format strings, arbitrary
kernel function addresses, sleeping services, and services whose semantics
depend on the original waiter task are not permitted.

## 3. Safety Invariants

1. Only targets present in the kernel-owned hostcall registry may execute.
2. The dispatcher invokes a typed handler; it never casts and calls an arbitrary
   address supplied by translated code.
3. A hostcall has a distinct `KD_EXE_HOSTCALL` sandbox exit reason and never
   changes an entry to `KD_EXE_CALL_MISS` on success.
4. The virtual CALL return address remains at `regs->sp` when the sandbox exits.
5. The dispatcher writes the service result to the documented x86-64 ABI return
   register, then advances `regs->sp` and `regs->ip` exactly once.
6. Resume uses the same `virt_ptr`, original entry RIP, execution frame, and
   outer lock ownership.
7. Hostcalls per delegated critical section are bounded. Registry rejection,
   handler failure, malformed virtual stack state, or a limit violation fails
   closed through the existing JIT abort/native-retry policy.
8. The initial services are retry-safe. A side-effecting service cannot be added
   until failure after service execution has an explicit exactly-once policy.

## 4. Call Classification

The translator must classify direct CALL targets into separate classes:

| Class | Examples | Translation and runtime behavior |
| --- | --- | --- |
| Control call | `_raw_spin_lock`, `_raw_spin_unlock`, `mutex_lock`, `mutex_unlock` | Preserve virtual return state and use the existing nested-lock/end-point protocol. |
| Hostcall | `ktime_get`, `ktime_get_ns` | Emit `KD_EXE_HOSTCALL`; execute through the kernel registry; resume after CALL. |
| Translatable callee | Explicitly discovered ordinary function | Use `KD_EXE_CALL_MISS`, append to `callee_table.txt`, and recompile. |
| Unsupported call | Unresolved or disallowed target | Fail closed; never execute it as a hostcall. |

The hostcall symbol list is a declarative shared manifest consumed by both the
kernel registry and the Python translator. This prevents the two sides from
silently assigning different service policy.

## 5. Hostcall ABI

On x86-64, translated CALL lowering has already pushed the original return RIP
onto the virtual stack represented by `R13`/`regs->sp`. A hostcall stub performs:

```asm
MOVABS  R14, <native service target>
MOV     Stack_IJ, KD_EXE_HOSTCALL
MOV     Stack_RSP, R13
JMP     exit
```

The wrapper stores `R14` in `regs->ip` and the exit reason in `args[0]`. General
service arguments remain in `regs->di`, `regs->si`, `regs->dx`, `regs->cx`,
`regs->r8`, and `regs->r9`. The initial time services take no arguments and
return nanoseconds in `regs->ax`.

After a successful typed handler, the kernel reads the virtual return RIP from
`regs->sp`, increments `regs->sp` by eight bytes, stores that RIP in `regs->ip`,
saves the continuation in the current execution frame, and invokes the same JIT
artifact again. Stack arguments and variadic services are unsupported.

## 6. Observability Contract

`kdlock_km` reports one module-exit line with these counters:

```text
kd_hostcall stats: exits=N executed=N resumed=N rejected=0 failed=0 limit=0
```

- `exits`: sandbox exits carrying `KD_EXE_HOSTCALL`.
- `executed`: allowlisted native handlers that completed successfully.
- `resumed`: actual subsequent invocations of the JIT artifact after a hostcall.
- `rejected`: targets absent from the registry or denied by policy.
- `failed`: handler or continuation-state failures.
- `limit`: requests rejected by the per-critical-section bound.

The mode 2 workload also reports `mode2 api observations=N`. This counter is
updated after consuming a nonzero native time result, so the exact workload
count proves that execution continued after every API call in both native and
delegated runs.

## 7. Implementation Steps

### Step 0: Preserve and inspect the baseline

- Confirm a clean host worktree.
- Confirm exactly one `qemu-system-x86_64` guest process, working SSH, Linux
  `6.1.159`, the guest build directory, and a recovery snapshot.
- Compare hashes before copying files into a recovery guest.
- Record that the old mode 2 path uses `KD_EXE_CALL_MISS` and has no dedicated
  service counters or artifact assertions.

Exit criterion: the test environment is recoverable and the original source is
understood before editing.

### Step 1: Define the shared protocol and service manifest

- Add `KD_EXE_HOSTCALL` as a sandbox-only exit reason.
- Add a shared hostcall definition file with stable IDs, symbol names, and
  safety flags.
- Add kernel declarations for IDs and flags.

Exit criterion: C preprocessing and Python parsing resolve the same services.

### Step 2: Implement the kernel hostcall dispatcher

- Resolve every manifest symbol with `kallsyms_lookup_name()` during module init.
- Implement one typed handler per service.
- Dispatch by exact resolved target address.
- Reject unresolved and unknown targets.
- Keep time-service handling out of the lock-control call handler.
- Bound requests and add atomic diagnostics.

Exit criterion: unit tests model allowlist success, continuation advancement,
unknown-target rejection, and the request bound.

### Step 3: Implement translator hostcall lowering

- Parse the shared manifest and resolve available symbols from
  `/proc/kallsyms`.
- Keep control-call and hostcall target sets separate.
- Include post-CALL blocks for both classes in continuation dispatch.
- Emit `KD_EXE_HOSTCALL` stubs only for manifest targets.
- Preserve the virtual return address for hostcalls; continue popping it for a
  normal CALL miss.
- Emit a readable hostcall comment in `jit.S` for artifact verification.

Exit criterion: a code-generation unit test proves that a hostcall stub uses the
new exit reason without stack pop while an unknown-call stub still uses
`KD_EXE_CALL_MISS` with stack unwind.

### Step 4: Strengthen the mode 2 workload and integration assertions

- Consume the returned timestamp after the CALL and increment the mode 2
  observation counter.
- Verify the generated artifact contains the `ktime_get` hostcall stub.
- Verify the hostcall target is absent from `callee_table.txt`.
- Record JIT write-back count before execution and require it to remain unchanged
  after execution.
- Require a real translated entry execution and `jit_success > 0`.
- Require `exits == executed == resumed > 0` and zero reject/failure/limit counts.
- Require the exact final counter and exact API observation count.
- Require drained queues/frames and clean kernel diagnostics.

Exit criterion: `tests/test_04_spinlock.sh 2` passes all assertions.

### Step 5: Run validation in increasing-risk order

Run inside the recovery guest, in this order:

```bash
make -C tests/unit clean
make -C tests/unit run
python3 -m py_compile disassem/*.py
make -C kernel_module -j$(nproc)
make -C klock_module -j$(nproc)
make -C daemon
gcc -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
timeout 60 bash tests/test_01_module_load.sh
timeout 180 bash tests/test_04_spinlock.sh 2
timeout 180 bash tests/test_04_spinlock.sh 0 1
```

The mode 0/1 run is required because the modified translator stub generation and
high-level continuation loop are shared with ordinary and nested spin JIT.

Exit criterion: every command succeeds, SSH remains responsive, no modules or
daemon remain loaded, and `dmesg` has no kernel failure signature.

### Step 6: Align project documentation

- Update `README.md` with the precise mode 2 hostcall meaning and command.
- Update `DESIGN.md` with the runtime state machine, call classes, ABI, counters,
  and side-effect limitations.
- Update `COMPONENTS.md` for the manifest, parser, and strengthened tests.
- Record mode 2 as a completed baseline in `TODO.md` only after end-to-end
  validation, while retaining side-effecting/logging hostcalls as future work.
- Add measured mode 2 evidence to `VALIDATION.md`; do not claim success before
  the guest test passes.
- Update `AGENTS.md` so future acceptance runs include selector 2.

## 8. Mode 2 Acceptance Checklist

- [x] Shared manifest is consumed by kernel and translator.
- [x] Generated mode 2 `jit.S` contains a named `ktime_get` hostcall stub.
- [x] Stub uses `KD_EXE_HOSTCALL` and preserves the virtual CALL frame.
- [x] `ktime_get` is not added to `callee_table.txt`.
- [x] Runtime hostcall does not trigger daemon recompilation.
- [x] `exits == executed == resumed > 0` in `kd_hostcall stats`.
- [x] Reject, failure, and limit counters are zero.
- [x] A returned timestamp is observed by instructions after the CALL.
- [x] The installed mode 2 entry actually executes and completes through unlock.
- [x] Final counter and API observation counter are exact.
- [x] Lock waiters, execution frames, and node slots drain.
- [x] Kernel log is free of panic, BUG, double fault, soft lockup, and invalid
      memory-access signatures.
- [x] Modes 0 and 1 still pass their translated-execution checks.

## 9. Follow-up Work

Before adding a side-effecting service such as logging, define an exactly-once
rule for failures after native service execution. The preferred initial logging
ABI is a fixed event ID plus scalar values, with bounded copying into a per-CPU
buffer and deferred emission after unlock. Supporting raw `printk(fmt, ...)` or
arbitrary stack arguments is not part of the mode 2 acceptance contract.

## 10. Execution Record

The plan was completed on 2026-09-04 in the recovery guest running Linux
`6.1.159`. The confirmed QEMU snapshot was
`pre_spin_translation_20260903`. Validation produced these results:

- Nine C unit binaries and `test_hostcall_codegen.py` passed: 10/10.
- Python byte-compilation, both kernel module builds, daemon build, and benchmark
  build succeeded.
- `tests/test_01_module_load.sh` passed and registered `ktime_get` at
  `ffffffff81193700` with flags `7`; standalone `ktime_get_ns` was unavailable
  because this kernel uses the inline wrapper.
- `tests/test_09_jit_execution_modes.sh 2` passed. Its artifact was 1407 bytes,
  contained the named `ktime_get` hostcall stub, had an empty
  `callee_table.txt`, and caused one initial JIT write-back only.
- Runtime mode 2 evidence was `jit_success=4`, `exits=4`, `executed=4`,
  `resumed=4`, `rejected=0`, `failed=0`, `limit=0`, `final counter: 12009`, and
  `mode2 api observations: 12009`.
- `tests/test_04_spinlock.sh 0 1` passed as the shared translator/executor
  regression check.
- The mutex counterpart in mode 5 now passes repeated/stress acceptance with
  `mutex_jit=1` independently observed, 381 complete
  JIT/hostcall/waiter-resume cycles, and exact counters of 12582.
- The guest remained reachable; no module or daemon remained loaded, and no
  kernel panic/BUG/double-fault/soft-lockup/unable-to-handle signature appeared.
- A final strict rerun after the register-ABI audit reproduced the 1407-byte
  artifact and all four hostcall cycles without recompilation or failures; its
  output is retained as `/tmp/kdlock-mode2-jit-rerun-20260904.log` and
  `/tmp/kdlock-mode2-jit-rerun-20260904-dmesg.log`.
- A post-mode-5 regression rebuilt the workload module and again completed all
  four mode 2 hostcall cycles. The shifted entry produced a 1464-byte artifact;
  output is retained as `/tmp/kdlock-mode2-regression-after-mode5-20260904.log`.
