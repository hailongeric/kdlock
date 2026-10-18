# Verification

JIT means just-in-time compilation: KD generates machine code so one lock holder
can perform another waiting task's protected work. The [terminology guide](../docs/TERMINOLOGY.md)
explains the lock, execution-state and measurement terms used below.

The [KD-only local mutex probe](kernel/mutex/local/kd_mutex_local_probe.c) checks
ordinary API aliases, exclusion, sleeping/nested owners, interruptible/killable
cancellation, I/O accounting, trylock and 2,048 independent objects. It checks
exact drain before unload. The [current receipt](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/validation.json)
keeps the live probe separate from unit fixtures and returned-body JIT benchmarks.
The [provider lifecycle fixture](unit/infrastructure/test_provider_lifecycle.py)
checks publication after runtime initialization, failed-start cleanup, and device
removal before teardown in ordinary and SELFTEST control flow.
The [rwsem admission probe](kernel/rwsem/README.md) checks sleeping reader/writer
semantics, cancellation, trylocks and ordinary downgrade on the selected KD
mutex. It also checks that outer writers stay unpublished until sleeping or
downgraded readers release, including same-CPU progress. These checks use local
outer returns; they do not claim JIT execution. Proc snapshot and rwsem runner
checks are in `bench/rwlock_compare/test_bench.py`;
full procfs/mmap integration is outside these checks.

Build and run all checks only in the recovery guest on `10.176.26.71`. Use the
[project guide](../docs/PROJECT_GUIDE.md) for setup and
[operations](../docs/operations/VM.md) for kernel verification, snapshots, fixed test inputs
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
| Checked spin pointer loads | `admission/test_address_guards.py`, `admission/test_guard_flags.py`, `execution/test_jit_entry_scope.py`, `execution/test_mutex_images.py`; [live check](kernel/spin/address_guard/README.md) |
| Original bounded string helpers | `admission/test_strcmp_service.py`, `admission/test_strscpy_service.py`, `execution/test_jit_entry_scope.py`, `execution/test_mutex_images.py`; [live strcmp check](kernel/spin/string_service/README.md) |
| Completed-body observation overlay | `execution/test_bench_completion.py`; applies the real benchmark patch and checks dispatcher/batch counting |
| Conditional instruction exit | `admission/test_native_escape.py`, `codegen/test_native_escape_codegen.py`, `execution/test_jit_entry_scope.py`, `execution/test_native_escape_restore.py`, `execution/test_mutex_images.py`; [live check](kernel/jit_escape/README.md) |
| Mutex resources/terminal path |`mutex/test_mutex_resources.py`, `test_mutex_task_cache.py`, `test_mutex_terminal.py`, `test_mutex_outer_progress.py` |
| Provider initialization/publication | `infrastructure/test_provider_lifecycle.py` |
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
[unit/execution/jit_entry_scope](unit/execution/jit_entry_scope) without changing checks.

The instruction-exit checks distinguish generated-code behavior from final task
resumption. Translation checks verify that reviewed instructions become exit
markers, short generated sequences that return control before the original
instruction, and that unreviewed instructions remain refused. Generated-code checks
execute the marker without executing its original privileged instruction. The
restoration check executes the provider's actual x86 register-restoration code
for all 64 combinations of arithmetic condition flags, which describe results
such as zero, carry and overflow. It also checks every general-purpose register,
the exact stack position, unchanged waiter control flags governing interrupts
and access checks, and untouched memory outside the two temporary stack words.
These userspace checks do not establish
kernel ownership or concurrent progress.

The checked-pointer fixtures verify the generated address comparison, the proof
that incoming arithmetic flags are overwritten before use, exact exit metadata,
and the runtime's ownership/image checks. String-service fixtures check the
captured helper instructions, argument bounds, source CALL and return validation,
and separate limits of 128 `strcmp` calls plus 16 other services/control
continuations. That second allowance includes the writing helper `strscpy_pad`.
Native helpers are substituted in the runtime fixtures; those checks alone do
not prove that the actual kernel helper completed.

The completion-observation fixture applies the actual benchmark overlay to a
private source copy. It counts one witnessed root invocation only after a
validated matching outer unlock, whether the body used a fast batch or returned
through helper services. A root invocation starts at the registered entry;
a nested or remote continuation that executes only a suffix is excluded.
Native fallback, quota exhaustion, malformed exits and missing witnesses do
not count as complete. Counter mutations must compile and fail assertions;
a compile failure is not mutation detection. These counters never control
admission, lock ownership or retirement.

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
only to KD spin cacheline workloads. A successful multithreaded functional JIT case
must return at least one JIT body. `spin_delegate=0` is a separate control that must
return zero. Many threads, a published request or NORMAL status alone do not prove
delegation occurred.

Rwlock correctness uses [its own live runner](kernel/rwlock/README.md), checking
reader overlap, writer exclusion, updates and exact count/gate drain. The
[rwlock benchmark](../bench/rwlock_compare/README.md) adds the real TCLock port and
1%/20% RCUHT mixes. Its `--require-jit` checks returned writer bodies; performance
parity is a separate `--require-parity` result. Readers do not count as JIT bodies.
The same runner's `--lock-kind rwsem` mode compares Linux Native with KD outer
ABI2 writers; `--delegate off` selects the local KD control. Mixed c08 runs check
reader consistency while entry and matching-unlock completion counters record
actual delegated execution. Whole-kernel mmap replacement is outside this scope.

The [conditional instruction-exit check](kernel/jit_escape/README.md) uses a
mutex operation containing a branch to `RDTSC`, the x86 processor-counter read.
With the branch untaken, it requires completed delegated bodies. Taking the
branch must stop generated execution immediately before that instruction,
resume the original waiter without repeating earlier updates, and disable
future delegation for that operation. After all earlier calls finish, a final
phase requires correct local execution and no further generated-code entries.
The check also verifies task identity, arithmetic flags, mutual exclusion and
complete release of execution records before unloading modules. It supplies
correctness evidence, not a throughput comparison.

The [checked-address probe](kernel/spin/address_guard/README.md) exercises one
supported spin pointer load. Its cold address is disjoint from a stack pointer
slot; its hot address safely aliases that slot. The failed check must resume the
original load on the waiter, preserve earlier effects and disable future
delegation of that entry. The [original-string-service probe](kernel/spin/string_service/README.md)
uses short stable strings for delegated `strcmp`, then valid strings longer than
the service's 256-byte check bound. That refusal must leave the helper unexecuted
and continue its pending CALL on the original waiter. Both probes require exact
operation counts, task identity, lock exclusion and final drain; their cold
phases require positive matching entry and completed-body counts. Neither is a
performance benchmark or a general pointer-safety test. The string probe does
not exercise the separate `strscpy_pad` writing service.

The current provider advertises capability version 9. Each runner also checks
its required feature in the provider's feature-bit mask; a version number alone
is insufficient. The supported compatibility ranges are:

| Boundary or service | Accepted capability versions | Required feature bit |
| --- | --- | --- |
| Mutex instruction marker | 6, 7, 8, 9 | 5: native instruction exit |
| Checked spin pointer load | 7, 8, 9 | 6: address guard |
| Original bounded `strcmp` | 8, 9 | 7: string services |
| Original `strscpy_pad(..., 64)` | 9 | 8: string writing service |

The writing-service capability is separate from the read-only comparison
capability. Its focused unit checks and exact taskname workload are separate
from the `strcmp` continuation probe. See the
[admission guide](../docs/design/admission.md#bounded-original-strcmp-service)
for the single-lock, source-lifetime and stable-memory limits. Publication and
unit success do not imply live workload or performance acceptance.

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

## Legacy compatibility checks

The [backport](../docs/history/legacy_mutex_compatibility.md) adds
`admission/test_instruction_policy.py` and `execution/test_mutex_images.py`.
`execution/test_exe_registry.py` also executes production `kd_mutex_prepare()`
against a newly registered root with no code block, terminal refusals and source
closure. Select these with the existing basic, context/codegen, source-lifetime,
entry-scope, wrapper and legacy ABI checks; no full inventory run is implied.
The [2026-10-17 validation receipt](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/validation.json)
records the completed selected checks and builds. The accompanying report records
504 accepted/drained live benchmark sessions and independent archive replay.


## Validation receipts

Use [the validation index](../docs/VALIDATION.md) for current and historical scope.
The [main-consolidation receipt](../bench/results/10.176.26.71/tests/main-consolidation-20261018/README.md)
records the affected tooling/path checks. Obsolete trace-only tests for removed
shadow-map and signal hooks were retired; their deletion does not establish
oversubscription correctness. Current limitations remain in [TODO](../docs/TODO.md).
