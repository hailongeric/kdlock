# Known limitations and deferred work

The [roadmap](ROADMAP.md) owns the three-stage plan. This page records unresolved
implementation and evidence gaps; [validation](VALIDATION.md) owns outcomes and
[performance](PERFORMANCE.md) owns measurements.

## Current checkpoint

Ubuntu 26.04.1 / Linux `7.0.0-38-kdlock1` is the normal platform. The separate
`kdmm1` image supports the measured Native/KD shared-MM modes. Linux 6.1 is
recovery/history only. Fresh four-family functional checks and the selected
[3,402-point catalog](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
are complete within their separate frozen scopes. All timing is exploratory,
with one round per point and failed strict qualification.

## Correctness and integration limits

| Area | Remaining limit |
| --- | --- |
| Whole-kernel replacement | Loading the provider does not convert kernel objects; each object and all its users require one protocol and lifecycle integration |
| Pinned delegation waiters | Published mutex producers poll with preemption disabled; broad oversubscription/progress redesign is deferred |
| Origin context | Hardware task/GS, IRQ/RCU, accounting and address-space state remain the executor's; trusting source does not switch them |
| Native recovery | Generic FULL exits do not restore arbitrary flags or SIMD/FPU state; only the documented instruction-exit paths preserve their declared arithmetic flags |
| Mitigations | Active call-depth tracking is rejected; complete mitigation coverage of handwritten/generated returns remains unvalidated |
| Image replacement | Mutex images are immutable; ordinary spin/rwlock entries may still replace code in place until an immutable transition |
| Source and object lifetime | Session source pins and image leases do not retain arbitrary data/lock allocations; stop/join, exact owners, ACKs and frame drain remain required |
| Fairness | Bounded batching and NUMA grouping do not establish starvation freedom or a maximum acquisition latency |
| API coverage | RT, ww_mutex, lockdep, general non-owner/cancellation nesting and unsupported IRQ/BH forms remain outside the declared support |
| Decoder/backend coverage | Source trust bypasses semantic proofs, not missing instruction lowering, text, return routing or runtime protocol support |

Production uses `trusted_source=True`, including kernel and module loops and
ordinary string callees. Earlier context/value/input proofs and string models
are optional checked regression or historical compatibility code, not pending
production admission work. Do not restore those checks as an implicit default.
See [translation policy](design/admission.md) and [register ABI](JIT_REGISTER_ABI.md).

## MM and performance gaps

The ordinary `kdlock1` kernel keeps the mmap adapter disabled. The separate
actual shared-MM comparison completed 42 points; Native was faster at all 21
worker counts. At 60 workers KD achieved 0.0436× Native throughput. A measured
cause or accepted optimization has not been established on the Linux 7 cohort.

The next scoped tasks are an exact actual-backend `mmap1_threads` runner, its
independent-process control, and a generic actual-backend minor-fault throughput
driver. Existing independent-mm device mappings and private-backing fault cycles
are different workloads. Preserve native MM bodies and original-task execution;
operation-specific delegation and prepared teardown remain retired.

Favorable nano points do not establish a universal gain. Current repeated
confirmation, uncertainty estimates and performance-neutral integration remain
open. The October 28 user-selected KD mutex default is 1024/1024, removing the
earlier count-based local cutoff. Recorded 768-boundary observations remain
separate; performance under the new default needs measurement. New tail-latency
collection remains deferred.

## Retained failures

The old checked taskname preparation, the original trusted mixed-taskname timed
failure, zero-point telemetry preflight, initial enabled-MM contention witness,
and strict unscored taskname `NO_JIT` control remain failed. Later prepared,
diagnostic or timed cohorts do not change their verdicts. Their exact counts,
causes and cleanup receipts are linked from [validation](VALIDATION.md).

Linux 6.1 performance regressions, stopped three-repeat matrices and rejected
protocol experiments remain in [history](history/README.md) and frozen results.
They are not an instruction to resume old-kernel adaptation or repeat expired
campaign plans. Use [basic plus affected checks](../tests/README.md) for a concrete
change; full suites and new performance campaigns need their own requested scope.
