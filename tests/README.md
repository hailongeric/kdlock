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
only to KD spin cacheline workloads. A successful multithreaded functional JIT case
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
checks exact drain. These constructed packets execute no JIT bodies; the
[policy benchmark](../bench/mutex_wait_compare/README.md) supplies that evidence.
Use `--mutex-wait-mode blocking` with the task/ACK probe to test the same policy.

## Recent verification and historical evidence

The [mutex c01 optimization record](../bench/results/10.176.26.71/bench/comparison/mutex-opt-20261011T045425Z/README.md#validation)
covers bounded task caching and NUMA queue selection, terminal/refusal/early-release
fixtures, the cross-NUMA task/ACK probe, field-width retirement reads and the
current c01/hash comparison. Live task/ACK probes execute no JIT bodies;
the benchmark supplies actual returned-body evidence. No live nested/early
mutex workload is provided by the maintained runner.

The [new-host NUMA/mutex record](../bench/results/10.176.26.71/bench/comparison/numa-mutex-20261010/README.md#reproduction-and-validation)
covers the registry/owner/CAS/layout/refill changes, basic and affected fixtures,
and drained 36-worker nested-spin, early-unlock and rwlock c01 regression runs.
It retains failed candidates and identifies the limits of the performance gains.

The [2026-10-10 ABI3 record](kernel/rwlock/README.md#abi3-verification-on-2026-10-10)
covers two basic programs plus five affected groups, 13 benchmark checks and
drained KD-native/KD-JIT correctness runs of 4,801,000 operations each.
All 270 sessions in the [RCUHT matrix](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md)
had correct results, worker progress and complete drain. KD matched both alternatives
on both throughput measures at 21 of 30 comparison points. These results belong
to the original 40-vCPU guest and cover the listed checks, not the full suite.
The initial 60-vCPU destination has its own
[migration validation record](../bench/README.md#vm-migration-validation).
Subsequent tests use the 64-vCPU destination with 32 cores per NUMA node; see
[the current environment](../docs/PROJECT_GUIDE.md#guest-workflow).

### Mandatory mutex JIT, 2026-10-08

On 2026-10-08, the mandatory mutex JIT change passed in guest `6.1.159-kdclobber2`:

- Two basic programs plus mutex resource, outer-progress and terminal drivers:
  five groups, zero failures; 48 runner tests also passed.
- NORMAL and SELFTEST `W=1` builds with UBSAN off. Both modules have no
  `mutex_jit` parameter, toggle symbols or UBSAN imports.
- The task/owner probe completed both release orders, four ACKs and two deferred
  frees, then drained. It constructs packets and executes no JIT bodies.
- The 16-thread/eight-cacheline functional run completed 1.6 million operations
  with 114,914 returned JIT bodies, passed data/JIT acceptance and drained.

The first probe load failed before KD initialization with reserved per-CPU
allocation ENOMEM. The existing allocator preparation helper allowed a separate
retry to pass; the initial failure and kernel log are retained. No kernel change,
full suite or performance matrix was run. The guest inputs remained frozen;
concurrent host spin post-work edits were excluded from this verification.

Sources, commands, exits, module identities, snapshot confirmation and live evidence
are at guest `/root/kdlock-evidence/mutex-jit-required-20261008-evidence.tar.gz` and
host `bench/results/380G10/raw/legacy/mutex-jit-required-20261008/guest-evidence.tar.gz`. Archive SHA256:
`e55f8b372391cca78daaf16598e3b7532d636901c6a380be83d1ccf575239d8f`.
This verification text is a documentation-only follow-up to the frozen inputs.

The earlier cleanup, executable comparisons and archive identities remain in the
fixed [cleanup record](https://github.com/hailongeric/kdlock/blob/10d800ea90d99e2b5e0e3e8d002dfe97b738d94e/tests/README.md).
Other results remain tied to their versions in [VALIDATION](../docs/VALIDATION.md)
and [benchmark history](../bench/results/380G10/bench/tclock_compare/HISTORY.md). Retain original
ignored/guest archives and failed candidates; known failures and deferrals remain in
[TODO](../docs/TODO.md).
