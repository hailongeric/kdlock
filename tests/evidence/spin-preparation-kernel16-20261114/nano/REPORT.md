# Offline spin nano prerequisite implementation

Implemented in isolated source export `/tmp/kdlock-spin-nano-source-7338197a-20261114/source`, based on exact kernel16 commit7338197a587fd84110fe710be63abafde270c02b. Shared checkout remains8e88f001 with unrelated dirty evidence checkers. Multiple active Codex processes prevented establishing exclusive ownership there; the isolated export was newly created and had no preexisting writer.

## Actual change

Eleven paths changed: build.py, run.py, oracle.py, evidence.py and newSPIN.md under bench/nano; Makefile, direct.h, api.h, module.c, runtime.inc under workload_modules/nano; newtests/test_nano_spin.py.

The new explicit spin branch routes Native to spin_lock/spin_unlock and KD to the exact base's kd_spin_lock/kd_spin_unlock, with cold initialization, spin queue/owner snapshots, spin runtime family and typed boundaries. Both retain the unchanged padded-counter body and256post-work rounds. Spin is100%write-only. A same-size snapshot version2 and compiled family/backend metadata distinguish spin from old mutex/rwsem modules. Unsupported TCLock/spin, ambiguous families and mixed spin builds refuse.

The builder selects exactly the Native/KD pair and compares all private include/kernel headers to the selected kernel source before and after building. The runner uses an explicit spin-pair scope, eight worker-vCPU inputs plus a distinct collector,1/2/4/8functional phases, same-build/boot/runner/placement prerequisites and one1-second timing interval per count. Training/compilation remains outside timing. Spin returns raw whole-run throughput without a peak claim. KD recording remains enabled, with overhead explicitly distinct from Native. Non-spin behavior/gates retain their existing defaults.

KD completion validation additionally requires typed spin unlock5; wrong-family unlock witnesses refuse. Existing exact source/request retirement, fixed-image and shutdown checks remain. Pristine spin taint0 is accepted alongside the prior out-of-tree4096 state; fault taints are not accepted, and the final existing4096 check remains. No kernel core/private header edit was made; policy_epoch from newer checkpoints was not imported.

## Executed verification

Explicitly authorized offline tests ran on380G10, without any guest boot:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_nano*.py' -v`:39passed,0failed,0skipped. Includes13new spin tests and26existing nano tests.
- Actual changed direct.h was preprocessed and checked with `cc -fsyntax-only` using minimal mocked dependency types. Tests verify Native/KD call expansion and absence of rwsem/mutex fallback. This is routing/syntax evidence, not compilation against Linux headers.
- Makefile selection tests invoke only a synthetic show target; no module target/build is executed.
- Python AST syntax passed for all five changed Python files.
- `git apply --check changes.patch` passed against the untouched exact base. No whitespace diagnostics were emitted by the no-index diff check.
- Negative tests cover unsupported/mislabeled builds, private-header mismatch, compiled backend metadata, snapshot family/backend mismatch, paired receipt/placement mismatch, wrong typed unlock, and unsupported taint. Raw-only timing still checks payload delta and does not manufacture a peak score.

`offline-tests.log` retains the first36-test pass; `offline-tests-final.log` is the final39-test pass. `checks.json` records final status and patch hash. No test failures occurred.

## ABI and runtime limits

This is kernel16-source-targeted, source-prepared code. Exact kernel/private headers are unchanged, but no Linux module compile, MODPOST, signature/CRC check, live runtime admission, real exclusion/progress, generated body or timing was tested. It is not yet a kernel16-runnable artifact and not a validation of newer8e88f001/9a8801cb behavior.

The small C mocks do not model the full kernel/runtime. The existing recorder observes positive foreign completions but does not establish multiple foreign bodies under one continuous physical spin acquisition. Per-vCPU-to-host placement must still be independently verified within16–19,36–39; process-wide affinity alone is insufficient. At8workers collector/service sharing remains explicit. No40dedicated-core claim.

Remaining work: separately authorized verified recovery point; exact source/output/ELF/config/GS and signed Native/KD module build receipts in a suitable VM build environment; pinned compiler/provider dependencies; reviewed new-guest controller and physical placement; then bounded functional checks before the paired pilot. Recovery gates were not bypassed, and no snapshot approval was inferred.

## Preservation and deliverables

All26captured files comprising the two dirty checker files and existing untracked spin evidence matched their original SHA256 values afterward. Core/private-header trees equal the exact base byte-for-byte. Original ram64 launcher and serial receipt also matched. No other-machine action, VM/profile change, package installation, deletion, commit, merge or push occurred. Super-Server was untouched and not booted; kdclaude was not recreated.

`changes.patch` is the reviewable patch against7338197a; it applies to the isolated base and has not been applied to the shared checkout. `source/bench/nano/SPIN.md` describes usage and evidence boundaries. `identity.json` and `preservation-after.json` bind provenance and preservation checks.
