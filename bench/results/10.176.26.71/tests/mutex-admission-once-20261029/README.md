# Consolidate mutex admission proofs

Candidate `99f383624faa872a76521d1b5be7faea586591c1` remains isolated on
`work/mutex-admission-once-20261029`. Documentation-first commit
`300071ad9684d41606c775d5abf33277cdc63728` precedes the implementation.
Scoped correctness passed; nine of ten contended mutex points still regress
against the saved pinned baseline. The no-regression gate remains open.

## Change and correctness

Only `kernel_module/mutex/pin_window.inc` and `kernel_module/mutex/combiner.inc`
change production behavior relative to `a46bf63c44bc81a32901dfd55e3c88a16954e262`.
The uninterrupted admission chain validates the private epoch, unreleased outer,
exact physical owner excluding PICKUP, COMBINER phase, different CPU, acquire
READY and stable counted key/generation once before borrowed preparation.
Generation capture is followed by a fresh key/generation reread. Two immediate
caller assertions and successful-path duplicate CPU checks are consolidated;
the initial checks across image/context work and every completion, cold, role
and tail boundary retain their fresh proofs.

The 65,536-PAUSE initial budget, early ordinary READY publication, one exact
current descriptor, cold CLAIMED promotion, 32-byte mutex, 320-byte node and
1024/1024 delegation limits are unchanged. OSQ physical acquisition and
proxy-wait delegation remain distinct memberships. The ordinary combiner body loop does not wait for queue replies. There is no
new parked-producer protocol, fairness change or oversubscription redesign.
Expiry-driven self-withdrawal requires exact withdrawal outside the owned proxy
epoch; explicit cancellation separately releases an unstarted current. Elapsed
time alone never permits unpinning while a combiner can still access the origin.

Nine selected unit drivers and both W=1 ordinary/mode2 provider builds passed
on their first attempts. The affected admission fixture uses the real owner
predicate, including valid owner flags and PICKUP refusal; it checks read counts,
post-READY generation/key mutation and wrong-current rejection before borrowing.
Parent publication and other unaffected drivers are not claimed as rerun.
[Unit/build receipts](unit-builds.json) retain exact commands.

[Independent ELF inspection](elf-independent.json) covers both entry ABIs in
both actual builds. All logical admission predicates remain, with two key and
generation reads; no call, fentry or RMW crosses the final proof-to-borrow window.
The expected-node condition is enforced by register/descriptor identity rather
than a separate emitted comparison. Cold generic fallback retains its strict
CLAIMED proof. Epoch-end bytes/relocations match the parent; run_combiner and
slowpath normalized instructions match, with changed addresses. Ordinary text
shrinks 239 bytes and execute_cs 255 bytes; size alone proves no speedup.

All eight live blocks passed: mutex/rwsem basic, queued scheduling, five local
role cases and true C2/node0-to-W33/node1 transfer. Each basic run completed
1,600,000 operations, with 1,589,050/1,589,636 returned mutex/rwsem JIT bodies.
All 74 context rows balance preemption, migration and IRQ state. The six role
cases preserve expected ownership, native/JIT continuation, early-inner behavior,
zero theft and exact source/frame retirement. [Live verification](live-verification.json)
records that scope; arbitrary nesting and unchanged local APIs are not newly validated.

## Spin and admission counters

Optional mode2/schema4; c01/post256, one two-second observation per point:

| Workers | Helper episodes | Within initial budget / pin retained | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: | ---: |
| 20 | 8,020,615 | 100% / 100% | 7,852 | 7,828 (99.6943%) |
| 36 | 7,690,812 | 100% / 100% | 14,977 | 14,928 (99.6728%) |

Claims and exact retirements match at 8,012,781/7,675,871; retained-current calls
are 14/17. Both points record zero expiry checks, withdrawals, forced/cancelled
claims, FULL resumes, unavailable/self selections and admission refusals.
[Independent verification](diagnostic-verification.json) checks complete
before/after subtraction and all conservation identities. These are helper-entry
episodes, including already-zero entries, not CPU spinning time or elapsed time
since READY. READY cohorts are sampled once at admission, never awaited.
The scoped spin target is met; no universal percentage or performance score follows.

## Single-round nano results

Mode0, c01/c16, post256, two seconds, workers 1/8/20/32/36/60. Exactly one
observation per point; no real-world API benchmark. All 36 mutex/rwsem points
have correct data, no worker/collector errors and exact drain. The saved pinned
baseline is `1c86d6d1a15d96d75c09504f1041772247707804`. Both arms' 72 raw sessions,
recomputed rates, CPU/NUMA/call-shell identities, workload bytes, non-build runner
AST and actual provider defaults were verified. Baseline blocks started 10.08/10.15
hours earlier in the same boot; this is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | Candidate Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916955 | +0.03% |
| c01 | 8 | 3.678105 | 3.644086 | -0.92% |
| c01 | 20 | 4.590029 | 4.054040 | -11.68% |
| c01 | 32 | 4.486160 | 4.129414 | -7.95% |
| c01 | 36 | 4.209552 | 3.923558 | -6.79% |
| c01 | 60 | 4.335256 | 3.937974 | -9.16% |
| c16 | 1 | 1.916744 | 1.916190 | -0.03% |
| c16 | 8 | 3.548560 | 3.586109 | +1.06% |
| c16 | 20 | 4.227567 | 3.960872 | -6.31% |
| c16 | 32 | 4.188997 | 3.965644 | -5.33% |
| c16 | 36 | 3.853043 | 3.746203 | -2.77% |
| c16 | 60 | 3.946234 | 3.798963 | -3.73% |

Contended mutex changes span -11.68% to +1.06%; nine of ten points are negative.
Rwsem spans -6.51% to +1.65% with 1% writes and -4.31% to +3.06% with 20% writes.
[Every point](comparison.json) retains its JIT status and single observation.
No variance estimate or performance-neutrality claim is available. Default
`complete:false`/`expected_rounds:3` summary fields remain unchanged; one valid
round and score eligibility do not establish strict timing qualification.

The optional counters show no withdrawal or readiness stall in their separate
instrumented observations. They do not support attributing this loss to parking,
but they are not measurements of every uninstrumented execution. Further small
source simplifications have not closed the gap. Focused c01/20 PMU and flat-IP
profiling, with unchanged runtime bytes and a tools-only Linux 7 baseline overlay,
is the next diagnostic step. Instrumented results must stay outside nano scores.

Kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. All timing remains exploratory.
No kernel modification or reboot ran in this candidate's validation.

## Preservation

Four trees, eight archives and 8,957 paths passed compressed SHA256 and complete
path/type/size/mode/owner/link inventory checks. Raw copies are under
`bench/results/10.176.26.71/raw/tests/mutex-admission-once-20261029/`.
[Archive verification](archive-verification.json) covers unit/build, live,
diagnostic and nano evidence. No archived code was executed on the source host.
