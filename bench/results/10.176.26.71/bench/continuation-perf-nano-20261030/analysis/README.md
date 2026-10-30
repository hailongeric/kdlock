# Finalized f7 nano comparison: losses retained, candidate unaccepted

Current source is `f7a84065e84474380faa37eeadfdf534abd72a68`. The corrected
postprocess owner is COMPLETE with completed=true and validated=true. All 210
KD points are retained, each measured once. The two comparisons remain separate:
`8617e97c02432a7c0b931aa8263d5edd0f6eb5b8` and
`acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f`. No Native/TCLock observations are
relabelled as current, no versions or topologies are pooled, and no negative is
removed as noise or by a significance threshold.

**Performance acceptance remains false.** The user explicitly authorized
continuing the remaining isolated syscall/MM comparisons while keeping the
candidate unaccepted. These nano losses prevent acceptance/promotion; they do
not cancel that authorized continuation.

## Whole and peak losses

| Separate comparison | Coordinates | Whole losses | Peak losses | Either metric |
| --- | ---: | ---: | ---: | ---: |
| f7 versus 8617 | 210 | 106 | 110 | 111 |
| f7 versus acfa | 210 | 114 | 118 | 122 |

By family, whole/peak/either losses are 22/24/24 of 42 mutex,47/48/48 of 84 rwsem,
and37/38/39 of 84 rwlock against 8617. Againstacfa they are 24/27/27,
44/45/45 and46/46/50 respectively. Current execution classifications are
133 RETURNED_JIT and 77 NO_JIT. Of current NO_JIT points, 38 lose either metric
against 8617 and 49 against acfa. Among 47 read-heavy w1 points with NO_JIT in both
versions, 26 lose either metric versus 8617 and 30 versus acfa. These remain scored.

Largest whole losses against 8617:

| Workload | Workers | Current whole Mops/s | Whole change | Peak change | Current class |
| --- | ---: | ---: | ---: | ---: | --- |
| rwlock c16 w1 | 6 | 8.469719 | −16.030% | −15.905% | NO_JIT |
| rwsem c01 w1 | 48 | 6.5386 | −12.856% | −12.858% | RETURNED_JIT |
| rwlock c16 w1 | 52 | 7.608976 | −12.258% | −12.154% | RETURNED_JIT |
| rwlock c01 w1 | 8 | 8.667300 | −10.736% | −10.728% | NO_JIT |
| rwsem c01 w20 | 6 | 5.1718 | −8.513% | −8.478% | NO_JIT |

Largest whole losses against acfa:

| Workload | Workers | Current whole Mops/s | Whole change | Peak change |
| --- | ---: | ---: | ---: | ---: |
| rwlock c01 w1 | 7 | 7.808985 | −24.957% | −24.750% |
| mutex c01 w100 | 4 | 3.1363 | −17.770% | −17.739% |
| rwlock c16 w1 | 6 | 8.469719 | −15.934% | −15.832% |
| mutex c01 w100 | 5 | 2.8247 | −13.549% | −13.240% |
| rwsem c01 w1 | 48 | 6.5386 | −12.556% | −12.726% |

Complete exact rates, both metric deltas and JIT shares are in
`all-point-rates-and-changes.csv`; the original complete comparison CSVs remain
under `/tmp/kdlock-nano-f7a84065-comparison-20261030/vs-8617` and `vs-acfa`.

## Did the targeted mutex change help?

The measured candidate recovers some previously weak delegated mutex points,
but does not demonstrate a general recovery. At c16 w100/12, whole throughput
is 4.134Mops/s, +7.379% versus 8617; at 16 it is 4.174M, +3.304%. Returned JIT write
shares stay about 99.4%, so these are comparable heavily delegated observations.
Those points remain slightly below acfa: −0.040% and−0.135% whole; their peak
losses are−0.319% and−0.136% and are retained.

At c16/20 and32, f7 instead loses 2.276% and0.501% versus 8617. C01/32 improves
4.229% to 4.546987M, while c01/12,16,20,60 loses 2.306%,2.657%,0.394%,0.622%.
Twenty-two of 42 mutex points lose whole throughput versus 8617. The previously
observed cold c01/4 deficit versus acfa also remains 17.770%. Therefore the
branch-layout correction has partial measured recovery, not no-regression
acceptance. The single sequential comparison does not isolate the causal
contribution of each of the three source changes.

All 10 actual measured f7 provider ELFs match the previously inspected f7 unit
artifact's allocated sections except build-id and all 8740 allocated relocation
recipes. The unit artifact SHA is
`93a892843297888e1a000d41dcc560de4fd9fabd74d3d90f95ef68406b3b3c6d`.
This connects the recorded normal-wake fallthrough,200B spin batch and guarded
terminal refresh to the actual measured providers. It is byte/relocation
identity, not a runtime placement or causation proof. `measured-elf-proof.json`
binds every profile's actual ELF hash. No inspected ELF was executed on the host.

## The previous rwsem c01 w1/seven-worker loss

| Captured value | acfa | 8617 | f7 |
| --- | ---: | ---: | ---: |
| Whole Mops/s | 10.459416 | 7.407581 | 10.437620 |
| Measured whole wall ms | 2010.299644 | 2010.308220 | 2002.528604 |
| Completed operations | 21,026,560 | 14,891,520 | 20,901,632 |
| Sum worker CPU / (7 × wall) | 99.494684% | 99.492042% | 99.872974% |
| Warmup total operations | 336,000 | 336,000 | 336,000 |
| Warmup wall ms | 32.939945 | 46.013064 | 33.125898 |
| Returned JIT bodies | 0 | 0 | 0 |

F7 whole/peak rises 40.9046%/40.3726% versus 8617 but remains 0.2084%/0.5932%
below acfa. The wall denominator improves only about 0.39%; most recovery is more
completed operations. Fixed-work warmup also improves 38.9036% versus 8617,
remaining 0.5614% below acfa. This is already captured preparation evidence, not
an additional timed round or acceptance score.

F7's exact provider log reports slowpath=0, combiner=0, handoff=0 and zero JIT
successes; it has only one failed mutex CAS across CPUs 0–6 and zero heat checks.
8617 had zero failed CASes and zero checks. Thus the large recovery is not
runtime evidence that the changed delegation wake path fixed this point. Reads
remain local. The lock virtual address is **identical** in 8617 and f7,
`0xffffffffc0ca05c0`, but neither campaign recorded the backing PFNs or page
NUMA nodes. Identical virtual addresses also do not prove identical physical
placement.

The largest remaining cold losses show the same useful-progress problem:
rwlock c16 w1/6 loses 16.030% versus 8617 with 99.5018% worker CPU/whole occupancy;
its warmup loses 18.218%. Rwlock c01 w1/7 loses 24.957% versus acfa with 99.5006%
occupancy, and its warmup loses 24.227%. These are not explained by losing a
quarter of the interval asleep. CPU accounting is not a hardware cycle, host
steal or scheduling trace, and no reader OSQ/phase-wake/park event counts were
captured. Shared-state spin/RMW costs, code/data physical placement and external
execution conditions remain hypotheses. The data do not establish a causal
percentage for any of them.

At rwsem c01 w1/48, only 3.8804% of **writes** complete through JIT, although its
classification is RETURNED_JIT; all reads execute locally. The 12.856% loss there
must not be described as a measurement of fully delegated read execution.

## NUMA transition

Worker 32 uses only node 0; worker 36 adds node 1. The f7 whole-rate step remains:

| Rwsem profile | 32 workers Mops/s | 36 workers Mops/s | f7 change32→36 | 8617 change32→36 |
| --- | ---: | ---: | ---: | ---: |
| c01 w1 | 8.352332 | 6.913302 | −17.229% | −13.883% |
| c01 w20 | 5.099569 | 3.935657 | −22.824% | −22.537% |
| c16 w1 | 11.084365 | 9.730956 | −12.210% | −11.749% |
| c16 w20 | 4.735317 | 3.784350 | −20.082% | −19.087% |

Each profile is compared separately. F7 is lower than8617 at 36 by 6.610%,2.896%,
1.846%,1.051% respectively. Againstacfa the 36-worker changes are−4.008%,
−1.564%,−1.054%,+0.968%. Cross-NUMA throughput decline remains; it is not newly
introduced uniformly across all profiles. The matched provider policy is still
1024 total/1024 NUMA boundary in every compared point, so this is not evidence
of the removed 768 count cutoff. The records establish worker NUMA geometry,
not the physical residency of every lock/data page. No placement diagnostic or
new measurement has been added.

## Current rates at 20, 32, 60 workers

Whole throughput, million operations/s; exact whole and peak rates are retained
in the complete CSV rather than combined into a cross-workload score.

| Workload | 20 | 32 | 60 |
| --- | ---: | ---: | ---: |
| mutex c01 w100 | 4.472154 | 4.546987 | 4.332423 |
| mutex c16 w100 | 4.141186 | 3.933595 | 4.013629 |
| rwsem c01 w1 | 8.712081 | 8.352332 | 7.125653 |
| rwsem c01 w20 | 5.341530 | 5.099569 | 3.740778 |
| rwsem c16 w1 | 10.751281 | 11.084365 | 9.826674 |
| rwsem c16 w20 | 4.898460 | 4.735317 | 3.571480 |
| rwlock c01 w1 | 8.370569 | 8.494290 | 7.548977 |
| rwlock c01 w20 | 5.170215 | 5.439240 | 3.545405 |
| rwlock c16 w1 | 10.326691 | 10.313987 | 8.043189 |
| rwlock c16 w20 | 4.180691 | 4.174444 | 2.430488 |

## Evidence and limits

`summary.json` retains per-profile loss counts, every negative whole point,
selected exact warmup/measure records and both independent boundary comparisons.
`point-provenance.json` binds copied point records to the finalized audited
archives and the original point hashes. `analyze.py` reproduces these derived
records without importing captured source. One initial summary script attempt
used a guessed rwlock member prefix; it stopped before producing a summary and
was corrected to the actual finalized point names. The failed draft and note
are retained; no measurement, audit or source input changed.

The earlier local postprocess watcher stopped on its preserved FAILED receipt
before fetch because its archive prefix omitted `kdlock-`. The corrected r2
owner is the completed/validated one used here, SHA
`d24710105272310e15f5679986bfe36427491266248c064e27afe7659ed0f056`.
That transport failure is not erased or relabelled as a completed first attempt.
All this analysis ran offline on 380G10; it initiated no VM calls, build, test,
fetch, audit rerun or timing.
