# Pipe cost and admission observations

The combined change improves fresh plain pipe throughput by **19.39% at eight
workers and 20.72% at 60**, while retaining the 32-byte, 8-byte-aligned public
object. It remains **22.42% and 22.57% below old256**, respectively. These are
medians of three 2000 ms measurements per source and worker count; they are not
confidence intervals. Source blocks ran embedded32, old256, then candidate.
The six instrumented sessions are separate diagnostics.

| Workers | Embedded32 Mops/s, median [range] | Candidate Mops/s, median [range] | Old256 Mops/s, median [range] |
|---:|---:|---:|---:|
| 8 | 4.498 [4.107, 4.597] | 5.370 [4.927, 5.552] | 6.922 [6.626, 7.111] |
| 60 | 3.456 [3.408, 3.456] | 4.171 [4.001, 4.191] | 5.387 [5.343, 5.401] |

The inputs are [comparison.json](comparison.json), the retained raw records,
and the independent [arithmetic review](statistics-review.json), which passed
34,386 checks with zero issues. Embedded32 is `cb0e8e6`,
candidate is `35718f5`, and old256 is `0324e60`. The candidate's production
change was already present at `c2f0d9c`; `35718f5` fixes a fixture typedef.
The failed first check attempt remains retained, as described in
[OPERATIONS.md](OPERATIONS.md).

## What changed in the acquisition path

Embedded32 stored the gate phase and exact waiter count in the same word.
Each queued origin added/subtracted 256 with a lock-wide atomic RMW. Updating
an occupied gate phase used a masked CAS loop to preserve concurrent count
changes. The candidate moves the exact waiter record into each already
reserved CPU node. Its origin writes a nonwrapping sequence and lock key;
occupied phase changes use ordered stores. Claiming a free gate still uses
CAS, and queue tail exchange/CAS still provide the existing queue protocol.
There is no new shared reference count, registry lock or RCU mechanism.

The cold count diagnostic uses a bounded double collect to obtain a consistent
snapshot, with explicit allocation/retry failure. That scan/allocation is not
part of lock acquisition or release. Idle checks and node records retain
exact ownership/lifetime checks rather than substituting approximate totals.

The retained ELFs confirm the intended machine-code difference. In the
baseline `__kd_mutex_lock_slowpath`, count entry has `lock xadd` at `+0x53`,
completed-body count exit at `+0x1e6`, and COMBINER publication has a masked
`lock cmpxchg` loop at `+0x12b`. In the candidate, node sequence/key updates
are ordinary stores, and COMBINER publication is a store at `+0x13b`.
This experiment changes both count updates and phase publication together;
it does not separate their individual contributions to the improvement.

## Measured delegation and whole-session batching

Returned-JIT shares below are sums of measured returned bodies divided by
measured completed operations across each three-repeat cohort. Body-entry and
returned-body counts agree in every plain session. Bodies per combiner is a
median of whole-session `jit_success / combiner` ratios, including warmup and
the two redirected checks. It is not a measured-phase batch distribution.

| Workers | Arm | Measured returned JIT | Whole-session bodies/combiner, median [range] |
|---:|---|---:|---:|
| 8 | Embedded32 | 93.946% | 120.498 [69.504, 153.113] |
| 8 | Candidate | 93.289% | 129.415 [126.756, 131.006] |
| 8 | Old256 | 97.097% | 338.793 [184.007, 375.366] |
| 60 | Embedded32 | 96.051% | 128.007 [127.967, 129.591] |
| 60 | Candidate | 95.414% | 128.050 [127.995, 128.055] |
| 60 | Old256 | 95.011% | 127.514 [127.472, 127.755] |

The candidate improves throughput even though its measured returned share is
slightly lower than embedded32 at both worker counts. At 60 workers its share
is higher than old256's and the whole-session batch ratios are nearly equal,
so a uniform loss of delegation does not explain the remaining gap. At eight
workers old256 has both a higher measured returned share and larger whole-
session batches. These observations warrant investigating service and queue
arrival timing; they do not establish which phase caused each difference.

All 18 plain sessions report balanced physical acquisitions/releases, zero
active waiters, reserved nodes and tasks at final drain, and zero handoff,
JIT-not-ready, JIT-failure, context-busy, node-overflow and frame-failure counts.
Those are whole-session checks. All 18 plain logs contain every worker's ratio
row. Their diagnostic residual
`sum(1024 * checks + contentions) - jit_success - origin_acquires - 2047 * workers`
is zero in this round. The heat ratios remain approximate admission accounting;
this reconstruction cannot replace exact lifetime checks or establish ownership.
The arithmetic review preserves missing suppressed rows as unknown rather than
zero when they occur. The residual is not an extra correctness invariant.

## Sampled work is predominantly polling

The flat 199 Hz kernel-cycle profiles contain 82,268 parsed samples, with no
reported lost samples or unparsed records. The percentages below use only
`sc_worker` weighted periods. The polling subset comprises the notification
loop's PAUSE, byte load and TEST; it is included in the slowpath total.

| Workers | Arm | Slowpath periods | Notification-poll periods | Profile returned JIT minus plain, points |
|---:|---|---:|---:|---:|
| 8 | Embedded32 | 61.258% | 46.773% | -0.332 |
| 8 | Candidate | 57.149% | 47.877% | +0.372 |
| 8 | Old256 | 54.795% | 41.631% | -5.680 |
| 60 | Embedded32 | 94.261% | 92.261% | -0.309 |
| 60 | Candidate | 94.033% | 92.913% | -0.523 |
| 60 | Old256 | 93.464% | 91.100% | -0.430 |

The roughly 94% slowpath result at 60 workers mostly represents waiting for
notification; it does not mean the gate or count instructions directly consume
94% of cycles. In the baseline, the instruction immediately after the completed-
body count XADD has 6.719%/0.920% of worker periods at 8/60 workers. The candidate
instead has 4.504%/0.462% at a node sequence guard after its sequence load.
These locations execute different code and samples can skid, so subtracting
their percentages would not measure the cost saved by removing the RMW.

The old256 eight-worker profile is particularly perturbed: it returns JIT for
91.417% of measured operations, versus 97.097% in its plain cohort. Its sample
mix cannot be assumed to represent the uninstrumented timings. The exact ELF,
sample and instruction-offset bindings are retained in
[baseline-offset-review.json](baseline-offset-review.json),
[candidate-offset-review.json](candidate-offset-review.json), and
[old256-offset-review.json](old256-offset-review.json). The complete denominator
and admission comparisons are in [profile-analysis.json](profile-analysis.json).

## Remaining cacheline placement

All six plain and both diagnostic sessions in each 32-byte arm record the
private workload lock at `0xffffffffc07984e0`, offset 32 within a 64-byte line.
Thus owner at +0, gate at +24 and delegation tail at +28 actually share that
line in this experiment. Old256 records `0xffffffffc0798580`; its owner +0,
gate +72, tail +128 and count +192 occupy separate 64-byte lines. The archive
and record hashes and field-address calculations are in
[placement-review.json](placement-review.json). The workload uses its private
KD object, not the native pipe object's mutex.

The candidate removes two sources of lock-word modification while physical
ownership, gate traffic and queue-tail traffic still use the same line here.
That placement is a concrete remaining difference worth isolating, but these
profiles contain no direct HITM, cache-transfer or CAS-retry counts. Native
8-byte alignment alone also does not guarantee the same placement for every
caller. The current results support the combined optimization under this
captured configuration, not a measured causal breakdown of the remaining gap.
