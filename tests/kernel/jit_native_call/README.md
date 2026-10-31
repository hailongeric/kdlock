# Reached Native CALL continuation probe

This is a correctness probe under development, not a benchmark or a real-world
API substitute. Build and execute only in the verified recovery VM under the
[VM operations contract](../../../docs/operations/VM.md). No build, execution or
pass is established by this source plan.

The first version uses the ordinary public KD mutex pair (ABI2) around an
unchanged Native raw spinlock object. Its conditional branch invokes the actual
kernel `_raw_spin_trylock`, then releases that Native lock in the original
waiter's suffix. The outer mutex serializes the Native word, so trylock must
succeed. Direct and register-indirect CALLs are separate compiled payloads and
separate source/provider sessions. The indirect case always targets a permanent
Native boundary, so it must remain a fresh CALL miss without requesting image
learning. The runner checks the emitted CALL bytes and target import before load.

Each session runs warmup followed by cold, taken, cold and repeated taken phases.
Cold phases require positive matching JIT-entry/returned-completion counts.
Taken phases require positive matching JIT-entry/validated-CALL-continuation
counts and zero returned JIT completions. All operations must increment prefix
and suffix exactly once, preserve exclusion and the Native word, record the
original physical task and CPU in the native suffix, and restore the caller's
preemption/IRQ/migration state. The source entry, generation, code address and
published bytes must remain unchanged and NORMAL through all phases. No
same-invocation return to JIT is expected.

A private recorded provider observation patch counts successful terminal/fresh
CALL validators only. It does not alter selection, target checks, source leases,
ownership, native ACKs or status publication. Kernel messages must bind the
selected CALL class, exact source return PC, actual Native target and original
worker task. Counters are not sufficient on their own: every worker must join,
exact effects must match, frames and owners must drain, and source retirement
and ordinary unload must complete. A timeout preserves callers/modules for
diagnosis and never authorizes forced cleanup.

The probe covers mutex-root Native CALL continuation. Other lock families,
contended Native locking, arbitrary RET/JMP recovery, non-C incoming-flags ABIs,
and broader kernel replacement remain separate validation scopes. The existing
[instruction marker probe](../jit_continuation/README.md) retains its own four-family
coverage and counters.

Run each mode in a new output directory while the guest is idle, after the
maintained recovery/snapshot checks. The runner captures kernel identity and
all inputs before preparing its private provider. For the maintained source and
output separated kernel, pass the declared build output as `--kernel-source`
and its authenticated schema-2 bundle as `--kernel-baseline`, as in VM.md.

```sh
python3 tests/kernel/jit_native_call/run.py --call-mode direct \
  --cpus 0-15 --warmup-iterations 200000 --iterations 100000 \
  --kernel-source /mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build \
  --kernel-baseline /root/kdlock-kernel-baselines/linux70-kdlock1-20261027 \
  --output /root/kd-results/native-call-direct
python3 tests/kernel/jit_native_call/run.py --call-mode indirect \
  --cpus 0-15 --warmup-iterations 200000 --iterations 100000 \
  --kernel-source /mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build \
  --kernel-baseline /root/kdlock-kernel-baselines/linux70-kdlock1-20261027 \
  --output /root/kd-results/native-call-indirect
```

The output includes the exact public-entry and CALL-byte audits, source/binary
hashes, private observation patch and prepared input hashes, per-phase worker
and registry receipts, generated image hashes, validated native events, and
source retirement state. Existing native begin/complete/unlock counters are
read only after all workers join and must equal the validated CALL count in
each phase. The original task returns from its outer unlock only after the
runtime's physical-unlock ACK; final native totals must match again at provider
exit. The physical outer owner observed before and after the Native CALL must
remain nonzero and unchanged (flag changes are masked); PICKUP must be absent.
The probe does not infer ownership from a counter or record a token after its
lifetime ends.

The directly affected guest checks are
`tests/unit/infrastructure/test_jit_native_call_runner.py` and
`tests/unit/infrastructure/test_jit_continuation_runner.py`, plus the basic checks.
They exercise CALL encoding rejection, exact repeated phase/image/counter
oracles, the diagnostic patch boundaries and caller retention on failures.
They are source additions until the VM runs them. W=1 builds and exact emitted
CALL inspection remain required before loading either mode.
