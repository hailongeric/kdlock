# KD protocol simplification: isolated screens

The screens admitted terminal metadata proof and cold-path lazy backing to combined validation. That combination was later rejected after a repeated mutex/hash regression, and the terminal change was reverted. The memory-only candidate was also rejected after its full matrix and protected-point recheck repeated a mutex/cacheline-16 peak loss above 3%. Dead-read removal, paired traversal budgets and the first lazy-backing implementation were not promoted. These 612 samples describe screen eligibility, not final acceptance or hash parity.

The screen uses three rounds at 16 and 36 workers, fixed 2.5 GHz, NUMA enabled, KD-provider UBSAN disabled, 48,000 warmup operations per worker and two measured seconds. Peak is the highest valid 300 ms window after 300 ms settling. Sixteen workers use node 0; 36 use 20 node-0 and 16 node-1 CPUs.

All 612 trials are retained and pass business results, warmup, selected-window reconstruction, worker progress and drain checks. All 204 KD trials have returned-body JIT evidence; all 96 TCLock mutex trials have measured delegation. These are raw-evidence checks; complete source/ELF/JIT identity requires the separate final archive audit.

Every pair below is **median peak / median whole-run**. Rates are Mops/s; percentage changes compare independent three-round medians. Opening and closing baselines are never pooled.

## Decisions and controls

| Candidate | Measured result | Decision |
|---|---|---|
| Dead packet read | One load instruction/four code bytes removed per hash request. Mutex/hash-16 changes −1.93%/−2.77%; recheck −3.04%/−4.22% versus opening. Against closing, neither exceeds a 3% loss. | No consistent benefit; do not promote. |
| Terminal suffix proof | Seven instructions removed per request. Spin/hash gains +0.45%/+0.38% at 16 and +0.43%/+0.56% at 36 versus opening. No screen point loses over 3% against either baseline. | Eligible at screen; later combined candidate rejected and terminal change reverted. |
| Paired traversal budget | Destination-chain mismatch iteration drops from nine to seven executed instructions; cold recovery adds seven static instructions/37 bytes. Spin/hash medians are slightly slower in both runs. | No measured gain for the added complexity. |
| Initial lazy backing | Spin/cacheline-16 changes −3.33%/−3.33%; recheck −3.64%/−3.65% versus opening. Both also lose over 3% against closing. | Reject this implementation. |
| Cold-path lazy backing | Spin/cacheline changes +0.33%/+0.19% at 16 and −0.12%/−0.20% at 36 versus opening. Mutex/cacheline-36 initially regresses, but its recheck does not reproduce the loss. | Eligible at screen; later memory-only matrix and recheck failed the protected-point guardrail. |

The destination-budget change leaves source-chain traversal unchanged; a destination match/exit also executes a refund. Instruction counts therefore describe a specific path, not every traversal iteration or hardware micro-ops.

The first cold mutex/cacheline-36 result must remain visible:

| Run | KD rate | Change vs opening | Change vs closing |
|---|---:|---:|---:|
| Cold screen | 4.975 / 4.869 | −5.05% / −4.69% | −11.85% / −9.89% |
| Cold recheck | 5.571 / 5.462 | +6.32% / +6.94% | −1.29% / +1.10% |

This screen loss did not repeat; it is not evidence of a stable mutex speedup. The later combined version completed 540 sessions and a separate 36-session mutex recheck. Its mutex/hash-36 whole-run median lost 5.84% and 6.62% against the closing baseline, so that combination was rejected. The cacheline losses did not repeat. Neither combined results nor their rechecks are pooled into these screens.

## Baseline drift limits attribution

| Unchanged KD workload | Opening | Closing | Change |
|---|---:|---:|---:|
| Spin/hash-36 | 2.017 / 2.006 | 2.020 / 2.012 | +0.14% / +0.27% |
| Mutex/cacheline-36 | 5.239 / 5.108 | 5.644 / 5.403 | +7.71% / +5.78% |
| Mutex/hash-36 | 2.308 / 1.628 | 2.683 / 1.882 | +16.27% / +15.58% |

The unchanged mutex/hash baseline moves by nearly as much as the apparent gains in unrelated translator experiments. Budget-pair also moves mutex/cacheline-36 by +9.54%/+10.50% while its published cacheline JIT binary is byte-identical to baseline. These changes cannot all be credited to edited generated instructions. Admission, handoff and scheduling variation need separate route evidence.

For terminal mutex/hash-36, the apparent +18.05%/+22.13% against opening becomes +1.53%/+5.66% against closing. This was sufficient to continue validation, but did not establish that the large opening-baseline mutex gain was caused by the simplification. The later combined regression prevented promotion.

## Hash remains below the stronger comparator

These are contemporaneous controls from the isolated terminal stage, not the later combined version.

| Workload | KD | TCLock | Linux Native | KD / stronger peak / whole |
|---|---:|---:|---:|---:|
| Spin/hash-16 | 3.929 / 3.917 | 5.083 / 5.065 | 3.727 / 3.698 | 77.30% / 77.34% |
| Spin/hash-36 | 2.026 / 2.018 | 2.778 / 2.767 | 1.695 / 1.670 | 72.92% / 72.92% |
| Mutex/hash-16 | 3.599 / 3.690 | 4.094 / 4.082 | 4.698 / 4.673 | 76.60% / 78.98% |
| Mutex/hash-36 | 2.724 / 1.988 | 2.212 / 2.202 | 2.762 / 2.696 | 98.62% / 73.75% |

Spin/hash returns about 99.9% of measured bodies through JIT and still trails TCLock substantially. High JIT coverage is not sufficient. The dead import and terminal suffix occur once per request; retained packet and traversal-budget work occurs inside loops. The paired-budget experiment did not turn its shorter common path into a throughput gain, so fewer instructions alone do not identify the limiting access or pipeline cost.

Mutex/hash-36 nearly matches Native's selected peak while losing much more over the whole run. Terminal JIT shares are only 18.36% at 16 and 21.25% at 36; native/delegated crossover, service and retirement costs need separate measurements. More delegation is not itself an optimization target.

## Memory, protocol and evidence

The separate eager/lazy diagnostics retain 64 logical image credits while changing backing from 64 × 655,360 bytes (40 MiB) to 655,360 bytes (640 KiB) for one registered image. This excludes metadata, task records and waiter stacks. Cold-path allocation retains that policy; alignment, owner publication and teardown after drain remain required.

The rejected terminal candidate removed only comparisons implied by a contiguous suffix with no interior entry. Its dynamic lock/endpoint, publication, ownership, completion and exact-once FULL recovery checks remained. The separately tested memory-only candidate changed no generated terminal checks; it was also rejected after broader validation. Source leases, native-first acquisition and final owner ACK remain intact.

Every screen worker makes progress, but that is not a starvation guarantee. The separately reported full matrices examine the 24-thread minority node. An allowed zero-body sample in that matrix is a native-route throughput control, never a JIT positive; the analyzers follow the frozen runner's exact acceptance policy.

The [screen samples](screen-samples.csv) retain all 612 trials, raw rates/counts, JIT classification, minimum worker progress, node shares, correctness/drain and exact raw-record/session hashes. The [screen groups](screen-groups.csv) retain all 204 arm/cohort groups with min/median/max/spread and separately named ratios to opening, closing and the stronger comparator. The full [KD comparisons](screen-kd-comparisons.csv) remain available. Full nested records stay in the raw archive; rechecks and failed candidates are never merged away.
