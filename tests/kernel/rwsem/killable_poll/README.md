# Original-task signal checks at killable phase polling

This correctness-only probe is a separate candidate based on
`22d62d5c13cad3c61c97dd47524da908769f1a52`. It does not modify or replace
that generation's provider, translated images, or scored applications. Commit
this contract before implementation. All builds and execution belong in the
VM; source inspection and Git operations belong on 380G10.

The runner extracts `kd_rwsem_reserve_local` and `kd_rwsem_poll_killable`
verbatim from the explicitly selected frozen source root. It retains the full
source, exact extracted bodies and SHA-256 provenance, and uses the actual
`kd_rwsem_types.h` layout. The test module does not load the provider or add
an exported production symbol. Thin private wrappers count reservation,
reschedule, signal and PAUSE calls while returning the real kernel primitive
results. The extracted reservation retains its real ordered atomic CAS.

Run four fixed cases, without retry: busy/free phase crossed with pending
`SIGUSR1`/`SIGKILL`. A bound but preemptible kernel thread allows and sends the
signal to itself before entering the helper. The private object's exclusive
phase belongs either to the controller (busy case) or to the successful worker
(free case). This is a phase reservation, not a completed rwsem acquisition:
no physical gate, reader drain or protected workload body is executed.

- Busy phase: require exactly one failed reservation, one false real
  `need_resched()` result, one true real `signal_pending(current)` result,
  zero PAUSE calls and a false helper result. The controller's phase must
  remain reserved until the worker has returned and joined.
- Free phase: require exactly one successful reservation, a true helper result
  and no reschedule, signal or PAUSE checks. This proves the helper consumes
  successful admission before consulting a pending signal. The worker releases
  exactly its successful phase before reporting completion.
- If an actual reschedule request short-circuits a busy case before the signal
  check, record **INCONCLUSIVE**, not a signal-stop pass. Do not mask that flag,
  disable preemption, extend the budget, retry or infer a pass from elapsed time.
- Record signal/fatal state and preempt/IRQ state before and after the helper;
  require no waitqueue or OSQ membership. Join each worker before the next case.
  A timeout is not drain; preserve the client/module and evidence if completion
  cannot be established. No force unload or automatic retry is permitted.

The fixture has instrumentation and a source-extracted helper. It is not proof
of the uninstrumented provider ELF, real queued signal cancellation, waitqueue
memory ordering, or performance. Existing full-API rwsem cancellation/rollback
checks and the deterministic 25-scenario/10-mutation fixture remain separate.
A pass must not be interpreted as JIT execution or a benchmark improvement.

The runner uses maintained `bench_runtime` idle/command/fault handling and
`kernel_identity` capture. It accepts an explicit `--source-root` so this
separate test tree can be uploaded outside the frozen provider tree. It checks
hash-bound source-state/source-map inputs and retains every compiled input,
the executed runner, support snapshots, kernel identity and module hash.
The client returns observations before validation; after all workers have
joined, normal module unload and final idle checks may finish even when a
case is inconclusive. The final result still fails such a case.

Planned invocation, with actual synchronization and identity paths supplied by
the VM controller (not executable evidence):

```sh
python3 /path/to/killable_poll/run.py \
  --source-root /root/host_fs/kdlock \
  --source-state /path/to/source-state.json --source-state-sha256 ACTUAL_SHA \
  --source-manifest /path/to/source-sha256.json --source-manifest-sha256 ACTUAL_SHA \
  --kernel-variant EXPLICIT_VARIANT --kernel-source MATCHING_BUILD \
  --kernel-baseline MATCHING_BUNDLE --cpu 0 --output NEW_EXTERNAL_DIRECTORY
```

Implementation and validation status: planned; no build, live result or
performance measurement is recorded by this document.
