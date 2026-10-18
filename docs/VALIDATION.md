# Validation index

Validation applies to the recorded inputs and scope. Publication, returned JIT
execution, correctness, drain and performance parity are distinct observations.
Basic plus affected checks are the default; an old pass is not a current full pass.

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
