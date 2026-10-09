# Verification

Build and execute checks only in the recovery guest. [Operations](../docs/AGENTS.md)
owns identity, snapshots, frozen inputs and drain; [the project guide](../docs/PROJECT_GUIDE.md)
owns setup. Run basic plus directly affected checks, not an automatic full suite.

## Unit checks

```sh
make -C tests/unit run
make -C tests/unit run PY_TESTS='spin/test_spin_direct.py spin/test_spin_entry.py'
python3 tests/unit/run.py --list
```

The default runs two basic C programs. `PY_TESTS` selects affected drivers; `run-all`
requires explicit intent. Drivers extract production bodies through
[source_text.py](unit/infrastructure/source_text.py), expanding private `.inc` files.
Missing dependencies, skips, crashes and compile failures are not passes.

| Changed area | Relevant drivers under `tests/unit` |
| --- | --- |
| Spin entry/tickets |`spin/test_spin_direct.py`, `test_spin_entry.py`, `test_spin_preempt.py` |
| Native pending/MCS |`spin/test_spin_nondelegated.py`, `test_spin_shadow.py` |
| Continuation/frame/queue |`spin/test_spin_storage.py`, `test_spin_batch.py`, `test_spin_outer_progress.py`, `execution/test_exec_capacity.py` |
| Wrapper, typed service and batch |`execution/test_jit_entry_scope.py`, `codegen/test_clobber_abi.py`, `test_jit_body_witness.py` |
| Mutex resources/terminal path |`mutex/test_mutex_resources.py`, `test_mutex_terminal.py`, `test_mutex_outer_progress.py` |
| Task/source/registry lifetime |`infrastructure/test_source_lifetime.py`, `execution/test_exe_registry.py` |
| Native ACK and remote continuation |`execution/test_remote_outer.py`, `test_remote_depth_protocol.py`, `test_remote_outer_protocol.py` |
| Context, aliases and guards |`admission/test_context_policy.py`, `test_context_memory.py`, `test_context_guards.py` |
| Heat/ratio |`infrastructure/test_hotlock_sampling.py` |
| IRQ/BH variants |`spin/test_spin_irq.py`, `test_spin_cold.py`; [kernel consumer](kernel/spin/irq_api/README.md) |
| TCLock assembly/parking |`spin/test_tclock_context.py`, `mutex/test_tclock_mutex_context.py` |
| Reader/writer exclusion and ordering | `rwlock/test_rwlock.py`; [live rwlock controls/JIT](kernel/rwlock/README.md) |
| TCLock rwlock assembly and benchmark oracles | `rwlock/test_tclock_rwlock_context.py`; `bench/rwlock_compare/test_bench.py`; [rwlock benchmark](../bench/rwlock_compare/README.md) |
| Runner/assembly export |`bench/tclock_compare/test_direct.py`, `bench/spin_cacheline/test_assembly.py` |

Fixtures validate modeled production transitions and machine-code continuations,
not every live kernel schedule. Protocol oracles under `protocols/` validate identity,
owner/ACK/order/effects in traces; synthetic traces are not actual JIT evidence.
The large wrapper fixture now groups entry/services/timing/spin/mutex cases under
[unit/execution/jit_entry_scope](unit/execution/jit_entry_scope/) without changing checks.

## Live checks

`tests/run_all.sh` with no arguments lists its scope; `--case module --dry-run`
previews it. The basic module case checks provider/device lifecycle without executing JIT bodies:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 timeout 240s tests/run_all.sh \
  --case module --output /root/kdlock-evidence/module-current-new
```

Confirm the snapshot in the monitor first. Use a new output directory outside the
repository. The runner freezes inputs, checks kernel errors and residual callers,
and preserves failures. `verify_evidence.py` only checks existing archives offline.

Actual JIT uses [the direct runner](../bench/tclock_compare/README.md). Select
plain, nested or early according to the changed path; nested/early are KD spin
cacheline only. Functional multithread positives need nonzero returned-body JIT;
explicit `spin_delegate=0` is a separate zero-JIT control. Do not infer delegation
from thread count, queue publication or NORMAL status.

The [mutex task/ACK probe](kernel/mutex/run_task_selftest.py) and selected SELFTEST
hotlock/entry probes check resource/routing/drain without executing JIT bodies;
they do not replace contended returned-body acceptance. KD mutex JIT is always
enabled; the task/ACK probe constructs its continuation packet before hooks are
published. Normal/SELFTEST builds stay separate.

## Recent verification and historical evidence

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
host `bench/.tmp/mutex-jit-required-20261008/guest-evidence.tar.gz`. Archive SHA256:
`e55f8b372391cca78daaf16598e3b7532d636901c6a380be83d1ccf575239d8f`.
This verification text is a documentation-only follow-up to the frozen inputs.

The earlier cleanup, executable comparisons and archive identities remain in the
fixed [cleanup record](https://github.com/hailongeric/kdlock/blob/10d800ea90d99e2b5e0e3e8d002dfe97b738d94e/tests/README.md).
Other results remain tied to their versions in [VALIDATION](../docs/VALIDATION.md)
and [benchmark history](../bench/tclock_compare/results/HISTORY.md). Retain original
ignored/guest archives and failed candidates; known failures and deferrals remain in
[TODO](../docs/TODO.md).
