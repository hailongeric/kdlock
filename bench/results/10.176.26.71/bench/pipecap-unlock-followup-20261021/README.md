# Unlock-route paired timing follow-up, 2026-10-21

Status: **all six planned sessions complete and drained; immediate host endpoint
failed; no acceptance.** The completed
[correctness stage](../pipecap-unlock-20261021/README.md) and its sealed archives
remain immutable. The main agent is the only writer and VM executor; helpers
perform read-only source/evidence review and report no files touched.

Fresh ownership checks found clean `master` at `2fb3cf0`, no writable project
descriptors or Git lock, and the same idle recovery VM with its original 73
modules and boot `88449cfc-cea9-4647-a294-bc601e372146`. No kernel or host setting
changes are part of this follow-up.

Observation 0 at `10:53:29.631645 UTC` found 71 QEMU threads with correct pins
and the actual recovery snapshot present. The later lifetime capture at
`10:54:13.875169 UTC` found 67 threads and no workers. Those extra identities
exited before their activity accounting was captured; no departed activity or
historical interference can be reconstructed. This later diagnostic snapshot
does not repair the first rejected observation or qualify as a full timing gate.

Observations use bounded read-only commands, at least 60 seconds apart, with
longer backoff if the same gate continues to fail. Extra-worker lifetime,
scheduler and I/O evidence is collected when present. Sleeping snapshots or
zero observed tick deltas are not proof of no work. Earlier 100-, 74- and
68-thread failures remain intact.

The full original gate passed on observation 1, admitting exactly three serial
pairs with the validated derivative and fresh original OUTER control:
OUTER/general, general/OUTER, OUTER/general. The original frozen provider,
source/ELF bindings, five workers on CPUs 0–4, collector 63, n16, two-second measurement,
48,000 plus one-second warmup, 300-ms peak/settle, 10-ms samples, and
`jit_timing=0` remained unchanged. Actual mutex offset was 32 modulo 64. The
supervisor captured the immediate post-run host endpoint outside the guest
runner. All sessions and failed attempts are retained; no replacement repetition
was selected.

The four completed syscall correctness sessions remain separate. New rates
compare the whole unlock-route transformation, including 15 removed cookie
routing bytes and changed layout/control flow. Report every rate, paired ratio,
execution class and returned fraction, plus sample variance. Mixed execution
classes or fractions do not isolate provider-call overhead. All seven causal
regressions and acquisition latency remain unresolved. Concurrent local readers,
separate mmap/page-fault tasks and exclusion of unsupported TCLock bodies stay
unchanged.

## Observation sequence and endpoint

| Observation | UTC | QEMU tasks | Outcome |
| --- | --- | ---: | --- |
| Full gate 0 | 10:53:29.631645 | 71 | Blocked; pins and recovery snapshot valid |
| Later lifetime capture 0 | 10:54:13.875169 | 67 | Extra identities already absent; not a full gate |
| Full gate 1 | 10:56:11.405935 | 67 | Exact original identities/placement and every other existing gate passed |
| Immediate post-run endpoint | 10:56:48.395256 | 120 | Failed strict identity/count condition; 53 extra workers on CPU 63 |
| Later endpoint lifetime 0 | 10:57:43.908157 | 76 | Nine TIDs matching the endpoint remained |
| Later endpoint lifetime 1 | 10:58:49.072141 | 68 | None of those nine remained; one new worker appeared |

The two full gate observations were 161.774290 seconds apart. The archived
supervisor starts the endpoint capture immediately after the guest command
returns, with no intervening remote inspection or model round trip. The nominal
endpoint timestamp minus the guest result's completion timestamp is 0.403116 s;
cross-host clock offset was not calibrated, so this is not a proven elapsed-time
bound. The original 67 TID/name/affinity rows remain unchanged at the endpoint.

The nine later workers have TIDs `447037`, `447041`, `447054`, `447060`, `447071`,
`447072`, `447074`, `447078`, `447090`. Their recorded start ticks are `96730497`
for the first two and `96733441` for the other seven. They cumulatively account
for 19,114,946 ns scheduler runtime, 475,136 read bytes and 7,065,600 write bytes.
Their user/system tick fields are zero; coarse tick counts therefore cannot be
used to infer no CPU work. These are lifetime totals observed after measurement,
not activity assigned to the timed windows. Matching the earlier endpoint is
TID-based because that receipt does not contain start ticks.

The next capture contains only new worker `447214`, start ticks `96743271`,
38,054 ns cumulative runtime and zero recorded I/O bytes. Thus 76→68 reflects
nine observed departures plus one new identity, not eight departures. No worker
identity survives between these two captures for a cross-capture activity delta.
Within each brief snapshot, identities and accounting counters are unchanged;
that does not prove inactivity between snapshots. Departed activity and effects
on individual measured sessions remain unbounded. No process was killed or
retuned, and these later observations do not repair any failed endpoint.

## Six paired results

Run `timing-1` used the validated runner at `2fb3cf0` (byte-identical to the
correctness runner at `574545b`), orchestrated by `5301e0f`. Every frozen
prerequisite receipt matches the prior stage, including derivative manifest
`daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae`.
No build, production edit, replacement repetition or additional correctness
workload was needed. Each provider load explicitly retains `jit_timing=0` and
the original collection parameters.

Whole rates are completed operations divided by the complete measured interval.
All values below are **descriptive diagnostic observations**, not accepted
performance scores. All six sessions use five workers; names are
`timing-pipecap-t05-r{repeat}-{outer|general}`.

| Repeat | Arm | Operations | Whole Mops/s | Peak Mops/s | JIT entries | Returned bodies | Returned fraction |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | OUTER | 28,371,968 | 14.185727 | 20.168573 | 62,665 | 62,665 | 0.220869% |
| 0 | General unlock | 10,861,056 | 5.430311 | 5.443754 | 671,239 | 671,239 | 6.180237% |
| 1 | General unlock | 12,391,424 | 6.195419 | 6.233584 | 538,537 | 538,537 | 4.346046% |
| 1 | OUTER | 15,070,464 | 7.534989 | 7.583371 | 261,520 | 261,520 | 1.735315% |
| 2 | OUTER | 39,390,976 | 19.694987 | 19.953422 | 0 | 0 | 0% |
| 2 | General unlock | 11,022,336 | 5.510820 | 5.525654 | 1,074,187 | 1,074,187 | 9.745548% |

Entry and returned fractions happen to agree in these six sessions; the two
counters remain distinct. OUTER repeat 2 is `NO_JIT`; all other sessions are
`RETURNED_JIT`. Zero entries alone do not prove zero queue activity.

| Pair | General/OUTER whole-rate ratio | Observed change | Execution-class condition |
| --- | ---: | ---: | --- |
| 0 | 0.382801 | −61.7199% | Both returned bodies, different fractions |
| 1 | 0.822220 | −17.7780% | Both returned bodies, different fractions |
| 2 | 0.279808 | −72.0192% | NO_JIT versus RETURNED_JIT; class mismatch |

The median paired ratio is 0.382801. The separate ratio of arm medians is
0.388476. Neither is a matched-path overhead estimate or an accepted regression
estimate. Peak-window paired ratios are secondary: 0.269913, 0.822007, 0.276928.

| Arm, three repetitions | Minimum / median / maximum Mops/s | Sample SD Mops/s | Sample CV | Range/median |
| --- | --- | ---: | ---: | ---: |
| OUTER, mixed execution classes | 7.534989 / 14.185727 / 19.694987 | 6.088922 | 44.1059% | 85.7199% |
| General unlock, returned bodies | 5.430311 / 5.510820 / 6.195419 | 0.420425 | 7.3602% | 13.8837% |

Sample variances are 37.074969 and 0.176758 (Mops/s)², respectively. OUTER's two
returned-body repetitions alone have a 43.3023% sample CV; this n=2 subset does
not establish a stable matched path. Three repetitions describe observed
variability and support no confidence or generalization claim here.

All sessions passed business results, protected-call accounting, worker/collector
placement, stable publication and exact retirement to state 2 with zero modules,
frames and writers. All mutex addresses have offset 32 modulo 64. Totals are
117,108,224 operations, 2,608,148 entries and 2,608,148 returned bodies, separate
from the four prior correctness sessions. No per-session kernel fault was
detected. Final verification found the VM idle with its original 73 modules,
unchanged frozen inputs and preserved recovery kernel.

## Interpretation and remaining work

This round establishes that the isolated caller is executable and drains with
the original provider. Its three repetitions returned bodies at five workers.
Fresh original OUTER controls returned bodies in two repetitions, so the prior
all-NO_JIT OUTER cohort is not a universal property of that interface. The
derivative's observed rates are lower in every pair; there is no measured win.

The failed host endpoint, changing delegation fractions and one class-mismatched
pair prevent attribution to provider-call cost or resolution of the original
DIRECT regressions. Both arms still acquire through OUTER. Their difference is
the complete unlock transformation, including removed cookie routing and changed
compiled layout/control flow. No production performance fix is selected.

All seven points remain `UNRESOLVED_CAUSE`: c08 at 3/4/5 workers, pipebytes at
3/5, pipecap at 5 and rcuht at 2. Acquisition latency remains unresolved; existing
complete-operation p95 is separate evidence. Further timing needs the unchanged
environment requirements to hold through the endpoint, with all attempts retained.
The original 100-, 74-, 68-thread failures and this 120-thread failure remain
fixed evidence; later observations cannot retrospectively validate them.

## Evidence

The [archive manifest](../../raw/bench/pipecap-unlock-followup-20261021/archives-1/archives.json)
has SHA256 `08fc223e20341d1bae01aff178bb36aca5a415fe7d262a876f8f216126d0a788`.

| Archive | Contents | SHA256 |
| --- | --- | --- |
| [timing.tar.gz](../../raw/bench/pipecap-unlock-followup-20261021/archives-1/timing.tar.gz) | All six sessions, runner, prerequisite bindings, generated images, oracles and retirement logs | `4435d1ca196230ca2dbd6032dc515f4de04c59455e96cdd2a9a670e50284f4e6` |
| [metadata.tar.gz](../../raw/bench/pipecap-unlock-followup-20261021/archives-1/metadata.tar.gz) | Observation sequence, supervisors, exact command receipts, failed endpoint, later worker accounting and final health | `e2f1d722a76cc890ad7798cbe53d60085a6499b252c756404dd883bb5a19fa97` |

The [inert review](review.py) and its [receipt](review.json) validate archive
membership/hashes, linked retained inputs, exact prior prerequisites, source
identity, all session arithmetic, original parameters and the failed endpoint.
It passed **3,521 checks**, with no archived code execution. Both read-only
helpers reported zero files touched and independently checked the source,
prerequisites, rates, classes and worker-lifetime limits. The main agent remained
the sole writer and test executor throughout.
