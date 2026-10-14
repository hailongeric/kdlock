# Verification

Build and run all checks only in the recovery guest on `10.176.26.71`. Use the
[project guide](../docs/PROJECT_GUIDE.md) for setup and
[operations](../docs/AGENTS.md) for kernel verification, snapshots, fixed test inputs
and safe shutdown. Run the basic checks plus those affected by the change. A full
suite requires an explicit request.

Source edits stay in the checkout on `380G10` and are synchronized to this guest
before testing. Use a new `/root/kdlock-evidence/10.176.26.71/tests/<run>` directory
for live evidence and unit-check logs. Keep host archives under
`bench/results/10.176.26.71/raw/tests/<run>` and compact reports under
`bench/results/10.176.26.71/tests/<suite>/<run>`; [the result layout](../bench/results/README.md)
keeps historical machines separate.

## Unit checks

```sh
make -C tests/unit run
make -C tests/unit run PY_TESTS='spin/test_spin_direct.py spin/test_spin_entry.py'
python3 tests/unit/run.py --list
```

The default target runs two basic C programs. Set `PY_TESTS` to add the relevant
Python drivers from the table below; use `run-all` only when explicitly requested.
These drivers use [source_text.py](unit/infrastructure/source_text.py) to extract
production code, including private `.inc` fragments, for their fixtures. A skipped
check, missing dependency, crash or compile failure must not be reported as a pass.

| Changed area | Relevant drivers under `tests/unit` |
| --- | --- |
| Spin entry/tickets |`spin/test_spin_direct.py`, `test_spin_entry.py`, `test_spin_preempt.py` |
| Native pending/MCS |`spin/test_spin_nondelegated.py`, `test_spin_shadow.py` |
| Continuation/frame/queue |`spin/test_spin_storage.py`, `test_spin_batch.py`, `test_spin_outer_progress.py`, `execution/test_exec_capacity.py` |
| Wrapper, typed service and batch |`execution/test_jit_entry_scope.py`, `codegen/test_clobber_abi.py`, `test_jit_body_witness.py` |
| Mutex resources/terminal path |`mutex/test_mutex_resources.py`, `test_mutex_task_cache.py`, `test_mutex_terminal.py`, `test_mutex_outer_progress.py` |
| Mutex blocking/result wakeup | `mutex/test_mutex_parking.py`, `test_mutex_balances.py`, `test_mutex_wait_clobber.py`; [live scheduler probe](kernel/mutex/run_wait_selftest.py) |
| Mutex workload drain | `mutex/test_mutex_drain.py` checks residual owner flags, sleeping waiters and configured Linux OSQ |
| Owned mutex | `mutex/test_owned_mutex_core.py`, `test_owned_mutex_delegation.py --mutations`, `test_owned_mutex_wait_clobber.py`, `test_owned_mutex_outer_api.py`; task-cache and admission checks also cover its private state |
| Owned optimistic entry and OSQ | `mutex/test_owned_mutex_preflight.py`, `test_owned_mutex_osq.py`; the outer API fixture compiles both capture-first and opt-in preflight callers and executes their generated JIT |
| Owned ordinary-C ABI4 | `mutex/test_owned_mutex_cabi.py --mutations`; actual leaf entry/unlock, eight-word late capture/restore, poisoned caller-saved registers, updated callee COMPLETE, exact FULL and cookie checks. Also select `execution/test_native_after_outer.py`, `test_exec_capacity.py` and ABI admission/codegen checks when changing shared state |
| Owned intrusive profiler | `mutex/test_owned_mutex_profile.py`; probe registration/unwind, target filtering and return-value ABI, separate from live diagnostic receipts |
| Task/source/registry lifetime |`infrastructure/test_source_lifetime.py`, `execution/test_exe_registry.py` |
| Native ACK and remote continuation |`execution/test_remote_outer.py`, `test_remote_depth_protocol.py`, `test_remote_outer_protocol.py` |
| Context, aliases and guards |`admission/test_context_policy.py`, `test_context_memory.py`, `test_context_guards.py` |
| Heat/ratio |`infrastructure/test_hotlock_sampling.py` |
| IRQ/BH variants |`spin/test_spin_irq.py`, `test_spin_cold.py`; [kernel consumer](kernel/spin/irq_api/README.md) |
| TCLock assembly/parking |`spin/test_tclock_context.py`, `mutex/test_tclock_mutex_context.py` |
| Reader/writer exclusion, ABI3 admission and retry | `rwlock/test_rwlock.py`, `admission/test_clobber_entry.py`, `codegen/test_spin_paired_jit.py`, `execution/test_jit_entry_scope.py`, `spin/test_spin_wait.py`; [live rwlock controls/JIT](kernel/rwlock/README.md) |
| TCLock rwlock assembly and benchmark oracles | `rwlock/test_tclock_rwlock_context.py`; `bench/rwlock_compare/test_bench.py`; [rwlock benchmark](../bench/rwlock_compare/README.md) |
| Runner/assembly export |`bench/tclock_compare/test_direct.py`, `bench/spin_cacheline/test_assembly.py` |

Fixtures check selected state transitions and machine-code continuations. They
do not exercise every possible kernel schedule. The checkers under `protocols/`
verify identities, owners, ACKs, ordering and effects in traces. A synthetic trace
can check those rules without proving that real JIT code ran.
The large wrapper fixture now groups entry/services/timing/spin/mutex cases under
[unit/execution/jit_entry_scope](unit/execution/jit_entry_scope/) without changing checks.

## Live checks

`tests/run_all.sh` with no arguments lists its scope; `--case module --dry-run`
previews it. The basic module case checks provider/device lifecycle without executing JIT bodies:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 timeout 240s tests/run_all.sh \
  --case module --output /root/kdlock-evidence/10.176.26.71/tests/module-current-new
```

Confirm the snapshot through the QEMU monitor first, and choose a new output
directory outside the repository. The runner saves fixed copies of its inputs,
checks for kernel errors and callers still running, and keeps failure records.
`verify_evidence.py` checks existing archives offline; it does not run the tests again.

Use [the direct runner](../bench/tclock_compare/README.md) to exercise actual JIT.
Choose plain, nested or early according to the changed path; nested/early apply
to KD spin and the explicit owned-v1 c01 mutex functional probes. A successful multithreaded functional JIT case
must return at least one JIT body. `spin_delegate=0` is a separate control that must
return zero. Many threads, a published request or NORMAL status alone do not prove
delegation occurred.

Rwlock correctness uses [its own live runner](kernel/rwlock/README.md), checking
reader overlap, writer exclusion, updates and exact count/gate drain. The
[rwlock benchmark](../bench/rwlock_compare/README.md) adds the real TCLock port and
1%/20% RCUHT mixes. Its `--require-jit` checks returned writer bodies; performance
parity is a separate `--require-parity` result. Readers do not count as JIT bodies.

The [mutex task/ACK probe](kernel/mutex/run_task_selftest.py) and selected SELFTEST
hotlock/entry probes check resource/routing/drain without executing JIT bodies;
they do not replace contended returned-body acceptance. KD mutex JIT is always
enabled; the task/ACK probe constructs its continuation packet before hooks are
published. Normal/SELFTEST builds stay separate.
The task probe also stresses concurrent exact task references and RCU eviction.
Zero references disable routing immediately; cached inactive identities can
remain until eviction or controlled unload. The probe pins a real RCU reader
across eviction and checks deferred task release. Its three stress workers reuse
three records, then verify their actual frees at purge. The production-code
unit fixture additionally checks cache bounds, reactivation/eviction arbitration,
active overflow, allocation failure and nested references.
Use `--cpus 0 32 33` for the current guest's cross-NUMA probe; its
default remains three distinct local CPUs. Final drain requires zero active
task membership after all workers and ACKs finish.

The [mutex wait probe](kernel/mutex/run_wait_selftest.py) tests immediate parking
and spin limits of 1,024 and 4,096. It observes real result/gate sleepers, runs
other work on the parked task's CPU, exercises 3,072 result publications and
checks progress with a deliberately withheld completion wake and exact drain.
It also drives the real admission sampler from hot to cold while a result
reservation and a gate waiter remain outstanding, then checks completion,
native ownership and drain at each polling budget.
These constructed packets execute no JIT bodies; the
[mutex benchmark](../bench/tclock_compare/README.md) supplies that evidence.
The task/ACK probe and scheduler probe both use the only supported blocking policy.

Pass `--owned` to the scheduler probe for the owned FIFO. It reserves and
publishes a real DELEGATE node, cools the independent admission sampler while
that node remains queued, observes actual result sleeping, then checks directed
SELF pickup and exact drain at each polling budget. Its deliberately unstarted
packet executes no JIT. The separate owned functional checks cover both ordinary
and clobber nested controls, delegated early release and checked FULL owner ACKs.
Guarded release is mandatory. The driver verifies
`owned_mutex_protocol=linux_local_first_v1` from sysfs and records that identity
and `owned_release_policy=guarded_owner_release`; there is no early-release flag.
ABI4 local-first acquisition may finish entirely through SELF, so use separate
returned-JIT and forced-FULL functional checks to validate delegation. A correct
zero-JIT performance sample does not replace those checks.

The intrusive profiler's `local_first` option counts the acquisition outcome from
`kd_owned_mutex_outer_cabi_gate`, using its full-width acquisition cookie. Its `ownedlocalfirst` receipt
reports acquired, failed and missed calls; failed local acquisition does not
prove a packet was published or executed. The fixture checks poisoned upper
register bits, exact target filtering, allocation/registration cleanup and
aggregation across CPUs. Instrumented runs are never performance scores.

```sh
python3 tests/kernel/mutex/run_wait_selftest.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/mutex-wait-NEW
```

## Recent verification and historical evidence

The [blocking-only mutex verification](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json)
on 2026-10-12 covers seven basic/affected groups, including 101 context-admission
cases, and 87 runner/report tests. Normal and SELFTEST `W=1` builds with UBSAN off
have no `mutex_blocking` parameter or symbol; build logs retain objtool warnings.
The scheduler probe passed at polling budgets 0, 1024 and 4096, and the cross-NUMA
task/ACK probe passed on CPUs 0, 32 and 33. A 16-worker/eight-cacheline functional
run completed 320,000 operations with 308,209 returned JIT bodies and complete
drain. No full suite or performance matrix was run. The evidence retains the
initial outdated test expectations, corrected checks and exact working-tree inputs.

Earlier mutex, NUMA, rwlock and migration receipts are indexed in
[validation](../docs/VALIDATION.md) and the [machine result indexes](../bench/results/README.md).
Their archived inputs and failed candidates remain available. An older pass does
not validate subsequent source changes or establish a full-suite pass. Known
failures and deferrals remain in [TODO](../docs/TODO.md).
