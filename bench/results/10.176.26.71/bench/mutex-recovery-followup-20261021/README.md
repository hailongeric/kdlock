# Recovery-kernel regression follow-up, 2026-10-21

Status: **84/84 valid, drained sessions completed; strict host endpoint failed
at 100 versus 67 threads. All seven causes remain unresolved. Performance
acceptance remains open.**

The actual mmap-lock [focused correctness stage](../../tests/mmap-kd-kernel-20261021/README.md)
completed in both experimental modes and was committed as `b8b31a7`. This
follow-up returns the same VM to its preserved recovery kernel under the user's
existing kernel/reboot approval. It keeps QEMU PID 257489, the original CPU/NUMA
placement, host frequency policy and recovery snapshot. A fresh boot is recorded
explicitly; it must not be represented as the original `b65f0205` boot.

The fixed plan contains 84 serial sessions: c08 at 3/4/5 workers, pipebytes at
3/5, pipecap at 5 and RCUHT at 2; three repetitions and the original four arms
(OUTER, public DIRECT, Native, TCLock). The original provider, workload, client,
daemon, translator and collector bytes from `mutex-public-20261020-r2` remain
frozen. The selection preserves original arm rotation, warmups, two-second
measurements, 300 ms peak/settling windows, 10 ms samples, n16, post64 and all
provider settings. No timing instrumentation or candidate optimization is added.
Unsupported TCLock MM bodies are outside this plan.

Before timing, require the exact original recovery kernel/source/config/ELF,
the original runtime-module set, voluntary preemption, original dependencies,
the real snapshot and exact original 67 host threads with their identities and
affinities. An explicit transition receipt binds the new boot; every other
environment check remains exact. Basic and affected tests run first in the VM.
Do not change the old runner's default boot guard or rewrite old receipts.

Retain immediate endpoint checks, all failures, each repetition and execution
class, range/CV, worker/business results, exact source retirement, final idle and
archives. No favorable-class replacement repetitions or parallel tests are
allowed. A strict endpoint mismatch prevents acceptance even if every session
drains. This run alone cannot isolate causes, acquisition latency or background
host interference; these remain explicit limits.

The first read-only host-preflight request timed out in automatic approval
review before execution. Its permitted retry succeeded without host changes.

`recovery-boot-1` stopped before changing boot state because its supervisor used
a nonexistent JSON helper; the failure is retained. `recovery-boot-2` completed
the approved one-shot recovery boot. `transition-1` verified the exact original
source/configuration/build/live identity and original 73 runtime modules on
boot `88449cfc-cea9-4647-a294-bc601e372146`; only the previously loaded `nfnetlink`
and `tls` needed restoration. The transition receipt SHA-256 is
`81280a1655854fead9e64c4ee752275a32eef3c3f30ce09d27b71a89621a1ca1`.

Driver revision `0d65f89` passed `checks-1`: dependency validation, both basic
programs and **19 tests** in the two directly affected replay drivers, with unchanged frozen
source and final idle. The fresh `host-before-run-1.json` receipt matches all
67 original QEMU thread identities/affinities, command, frequency and NUMA
settings and lists the real recovery snapshot. `run-1` uses this driver and
the separately preserved original benchmark inputs; no code correction is
substituted into the measured providers.

## Results and variance

`run-1` completed all 84 sessions, **1,108,310,016 operations**, 42 exact KD
source retirements, 46,231,358 generated-entry witnesses and 10,094,766 returned
API bodies. Entries and returns are different metrics. All workers progressed,
business checks passed, and no session log matched the retained kernel-fault
patterns. The [health summary](health-summary.json) confirms final idle and the
same runtime-module set. The VM remains on the preserved recovery kernel.

The following are whole-run DIRECT/OUTER median ratios, each based on three
repetitions. Collections are separate; no samples are pooled across boots.
Higher ratios favor DIRECT. A missing ratio means the execution classes differ.
These are descriptive results under a failed host endpoint, not accepted fixes.

| Point | Original ratio | Follow-up ratio | DIRECT CV | OUTER CV | Follow-up class |
| --- | ---: | ---: | ---: | ---: | --- |
| c08 / 3 | 0.81246 | 0.71235 | 2.94% | 13.92% | Both WITNESSED_JIT |
| c08 / 4 | 0.70664 | 0.70532 | 6.66% | 4.84% | Both WITNESSED_JIT |
| c08 / 5 | 0.78900 | 0.70734 | 1.43% | 13.62% | Both WITNESSED_JIT |
| pipebytes / 3 | 0.84054 | 0.97217 | 2.17% | 2.94% | Both NO_JIT |
| pipebytes / 5 | 0.87407 | 0.94536 | 6.31% | 3.10% | Both RETURNED_JIT |
| pipecap / 5 | 0.59768 | — | 7.24% | 1.19% | DIRECT RETURNED_JIT; OUTER NO_JIT |
| RCUHT / 2 | 0.91932 | 0.90932 | 1.76% | 1.49% | Both WITNESSED_JIT |

The pipecap OUTER image was published and remained stable in all three runs,
but neither entry nor completion was observed; DIRECT recorded positive returns
in each run. Publication alone cannot close this class gap. No replacement
repetitions were selected. RCUHT has three matching entry-witnessed repetitions
in this follow-up, which does not change its earlier split-class collection or
prove returned synthetic JIT bodies.

Across complete three-repeat groups, maximum whole-rate spreads were OUTER
28.21%, DIRECT 13.22%, Native 23.01% and TCLock 33.85%; corresponding maximum
sample CVs were 13.92%, 7.24%, 12.01% and 18.08%. Spread is
`(maximum − minimum) / median`; CV is sample standard deviation divided by mean.
Three repetitions are observed variation, not confidence intervals.
[Every repetition](review-1/per-repeat.csv), [class-separated groups and ranges](review-1/groups.json)
and [original/follow-up comparisons](review-1/comparisons.json) are retained.

The immediate endpoint at `2026-10-21T09:25:06.881411+00:00` had **100 threads**
instead of the original 67. QEMU identity, command, frequency policy, NUMA
bindings and guest configuration still match, but that does not waive the thread
failure. No host configuration changed, no parallel test ran and no active
call was interrupted. The [run receipt](run-1.json) records session completion;
the [final status](final-status.json) additionally includes this failed endpoint.

## Preservation and unresolved scope

The four-group [archive manifest](archives.json) has SHA-256
`a57c35c0a11df0812b6a621a688c50229e5cc6c9fdde60868e1799640cf281d1`.
Complete archives are in
`/root/kdlock-evidence/10.176.26.71/bench/mutex-recovery-followup-20261021-archives-1/`
and [local raw storage](../../raw/bench/mutex-recovery-followup-20261021/archives-1/archives.json).
They preserve the failed first reboot supervisor, successful transition,
correctness checks, every measurement, exact source references and host receipts.
The original archive remains separately bound by SHA-256
`7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4`.

The [inert review](review-1/review.json) passed **851,872 integrity checks**,
covering 68,976 original and 3,728 follow-up members, cross-archive links,
4,088 exact original input files, 336 collector files, recorded settings,
business/worker checks, all 84 reconstructed peak windows, published image
hashes and exact retirements. It executed no archived code. It separately
reports the strict host endpoint failure; evidence integrity is not performance
acceptance.

All seven points remain `UNRESOLVED_CAUSE`. Six have lower DIRECT medians in
matching classes in this follow-up; pipecap has a new class mismatch. This does
not isolate call overhead, ownership duration, queue behavior, host interference
or a code correction. The prior uncalibrated one-worker
[owner observation](../pipecap-owner-20261021/README.md) remains separate.
Acquisition-only latency, earlier c08/2 and pipebytes/4 class gaps, strict
low-count rwlock execution failures and broader shared-lock performance gaps
remain unresolved. Full MM-body delegation, whole-kernel replacement, RT,
ww_mutex, lockdep and oversubscription redesign remain outside validated scope.
No admission, exact ownership, ACK or retirement check was weakened.
