# Validation index

Validation applies to the recorded inputs and scope. Publication, returned JIT
execution, correctness, drain and performance parity are distinct observations.
Basic plus affected checks are the default; an old pass is not a current full pass.

## Rwsem writer delegation, 2026-10-18

The [delegation receipt](../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
records the new phase admission around the unchanged selected mutex protocol.
The final sleeping/API probe passed same-CPU reader progress, ordinary downgrade
before outer publication, ten cancellation cases and complete drain. Twenty-four
Native/KD c01/c08/RCUHT functional sessions passed; they recorded zero JIT and are
kept separate from four successful strict acceptance runs at 16 workers.
Those c08/RCUHT runs returned 3,174,269/3,178,872 JIT bodies at 100% writes and
404,874/163,345 at 80% writes, with matching completion counts, correct data and
complete drain. The mixed c08 case had zero reader consistency errors.
Five additional c08 local/read-only controls passed with zero JIT and full drain,
bringing the focused workload checks to 33 successful sessions.

Basic and affected checks passed individually or after the documented fixture
corrections. The receipt preserves the obsolete ABI fixture, unexported probe
accessor and Python import-setup failures. It also preserves the strict
20%-write/32-worker c08 attempt: correct and drained, but no returned JIT bodies;
its following RCUHT plan item was not run. The separate
[standard performance grid](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
completed all 756 sessions correctly and drained. Final health recorded an idle
guest, unchanged boot ID, verified source/binary inputs, no Linux mutex imports
and no new faults in the retained kernel log. Per-session fault captures remain
separate from the possibly rotated final ring. These checks do not establish
whole-kernel mmap replacement or oversubscription safety.

## Feature reintegration, 2026-10-18

The [reintegration receipt](../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
records ordinary sleeping rwsem, proc snapshots and independent benchmark tools.
Basic/affected tests, two rwsem scheduler probes and 61 workload sessions passed;
two failed delegation-acceptance attempts remain visible. Timed argbounds and a
rwlock writer check have fresh complete-body evidence. Taskname delegation did
not pass preparation; its explicit local controls passed. The accepted mutex
source is unchanged. This is neither whole-kernel mmap integration nor a new
full performance matrix.

## Main consolidation, 2026-10-18

The [consolidation receipt](../bench/results/10.176.26.71/tests/main-consolidation-20261018/README.md)
records checks for branch integration, moved files, benchmark tooling and docs.
The selected provider, headers, translator, daemon, TCLock implementation and
kernel payloads are compared byte-for-byte with `d2a2304`. No lock protocol is
changed and no new performance matrix is claimed for this organization pass.

## Accepted KD-only mutex, 2026-10-17

The [acceptance receipt](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/validation.json)
records the provider W=1 build, ordinary-alias probe, two basic checks, affected
fixtures and 504 complete/drained benchmark sessions. The live probe checks
8 workers, 160,000 operations and 2,048 independent objects, plus sleeping/nested
owners, interruptible/killable cancellation, I/O accounting and trylock.

The [benchmark report](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
records 6,043,578,112 operations across four arms. Its archive has 150,984 files
and 3,916 symlinks; 143 numeric outputs were independently reproduced. These
observations do not establish whole-kernel replacement, RT/ww_mutex/lockdep,
oversubscription safety, or a full test-suite pass.

## Historical evidence

- [Compatibility backport](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md): instruction refusal and immutable mutex images with legacy delegation.
- [Recovered legacy grid](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md): 378 c01/pipebytes sessions before the backport.
- [Rwlock c01](../bench/results/10.176.26.71/bench/rwlock/20261015-c01/README.md): 378 sessions, with separate JIT statuses and parity limits.
- [Earlier validation index](https://github.com/hailongeric/kdlock/blob/d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761/docs/VALIDATION.md): fixed baseline, wrapper, protocol and cleanup receipts.
- [Results by machine](../bench/results/README.md): retained raw archive paths and compact reports.

### Mutex oversubscription assessment

The historical mode4 pinned-waiter soft-lock and mode5 lack of actual JIT remain
open limitations. See the [fixed assessment](https://github.com/hailongeric/kdlock/blob/d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761/docs/VALIDATION.md)
and [known failures](TODO.md). Removing obsolete trace-only harnesses does not
resolve those failures.

### Main-plan acceptance audit

Acceptance requires matching generated/published identities, returned JIT bodies
where required, correct effects, exact owner ACKs and complete retirement. Current
selected checks cannot be combined with historical passes to claim whole-project
acceptance. See [tests](../tests/README.md) for commands and scope.
