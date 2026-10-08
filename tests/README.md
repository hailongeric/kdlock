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
| Runner/assembly export |`bench/tclock_compare/test_direct.py`, `bench/spin_cacheline/test_assembly.py` |

Fixtures validate modeled production transitions and machine-code continuations,
not every live kernel schedule. Protocol oracles under `protocols/` validate identity,
owner/ACK/order/effects in traces; synthetic traces are not actual JIT evidence.
The large wrapper fixture now groups entry/services/timing/spin/mutex cases under
[unit/execution/jit_entry_scope](unit/execution/jit_entry_scope/) without changing checks.

## Live checks

`tests/run_all.sh` with no arguments lists its scope; `--case module --dry-run`
previews it. The basic module case checks provider/device lifecycle with JIT=0:

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
hotlock/entry probes check resource/routing/drain with JIT=0; they do not replace
contended returned-body acceptance. Normal/SELFTEST builds stay separate.

## Recent verification and historical evidence

On 2026-10-08, guest `6.1.159-kdclobber2` passed:

- Two basic programs, the entry-scope fixture/mutations and both TCLock
  assembly/parking drivers: five groups, zero failures.
- 45 runner tests and seven assembly-export tests.
- Seven `W=1` module builds: KD NORMAL, before/after TCLock spin and mutex,
  and both final whitespace rebuilds. All modules have no UBSAN imports. Existing stack-switch objtool warnings
  are unchanged; the logs retain locale fallback warnings too.

Both TCLock modules have identical before/after executable bytes, relocation
records, alignment and function layouts. The three split C units have identical
expanded non-comment tokens. The static audit checked 40 Markdown pages, 426 local
links and 31 fixed Git targets; all maintained files are English and all six
upstream hashes match. No modules were loaded, and no live JIT or performance
benchmarks ran.

Frozen inputs, commands, exits, logs, hashes and modules are archived at guest
`/root/kdlock-evidence/cleanup-20261008-evidence.tar.gz` and host
`bench/.tmp/cleanup-20261008/guest-evidence.tar.gz`. The final whitespace check
repeated affected unit/runner checks and rebuilt both TCLock modules; it is at guest
`/root/kdlock-evidence/cleanup-20261008-whitespace-evidence.tar.gz` and host
`bench/.tmp/cleanup-20261008/whitespace-guest-evidence.tar.gz`. It includes the initial
archive's identity and reuses only its unchanged baseline/KD modules. Final archive SHA256:
`44555fd71e080c6140da7061cb95a73b9996ed2132f2e1a8a36bfe59520600bf`.
The final verification text is a documentation-only follow-up to those frozen inputs.

The earlier cleanup's missing-file failure and retry remain in its fixed
[record](https://github.com/hailongeric/kdlock/blob/e533214/tests/README.md).
Other results remain tied to their versions in [VALIDATION](../docs/VALIDATION.md)
and [benchmark history](../bench/tclock_compare/results/HISTORY.md). Retain original
ignored/guest archives and failed candidates; known failures and deferrals remain in
[TODO](../docs/TODO.md).
