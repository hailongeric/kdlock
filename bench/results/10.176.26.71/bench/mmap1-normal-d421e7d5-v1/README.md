# Bounded mmap1 validation after batched source discovery

The single normal campaign completed a stable eight-process point. Mmap's
retained root returned on all 336,042 JIT entries in the drained fixed
application. Munmap completed 336,037 native handbacks and had zero retained
returns. Required publication, fixed-point stability, exact retirement and
normal-kernel recovery passed. The measured rate was **20,970.8 pairs per
nominal second**, with selected service counters enabled; the campaign and
point remain unscored and quiet performance remains unaccepted.

Candidate: `d421e7d5da83675be7b409e584b44f4f662b98b1`, on
`codex/release-unit-boundaries`. This candidate restores batched source discovery
before strict release-unit emission, including release-only callees. Existing
source-trust policy, release boundaries, return routing and resource bounds
remain in effect. This record adds evidence only.

## Execution and settlement

The unchanged `bench/mmap1/settled.py` workflow used the existing 128-image
diagnostic profile and the unchanged will-it-scale userspace syscall workload.
No build or unit-test rerun was needed: existing provider and daemon inputs
matched the candidate's relevant production inputs, and all five changed
source/test files matched the retained focused-test manifest. Frozen source
remained unchanged through the campaign.

One fresh campaign ran the 730-sample preparation, bounded continuations only
while learning advanced, and one fixed point. All applications exited zero and
drained. The existing learning deadline was 1,800 seconds; each continuation
had a 30-second application bound. The fixed point had six warmup samples,
ten measured samples and a 30-second bound.

| Stage | mmap / munmap generations | Application | Stable |
| --- | --- | --- | --- |
| Long preparation | fresh -> g5 / g5 | Passed, drained | No |
| Continuation 1 | g5 / g5 -> g6 / g6 | Passed, drained | No |
| Continuation 2 | g6 / g6 -> g7 / g7 | Passed, drained | No |
| Continuation 3 | g7 / g7 -> g7 / g7 | Passed, drained | Yes |
| Fixed point | g7 / g7 unchanged | Passed, drained | Yes |

The final point retained the same image pointers, generations, learning state
and completed compiler records. Whole-application conservation passed. There
was no local/no-image fallback, cancellation or invalid clock count in the
point. Its full process lifetime was 16,055,069,460 ns.

The publication gate passed for mmap entry `0xffffffff817b6f68`, learned CALL
target `mas_wr_bnode` at `0xffffffff826c1df0`, and exact STD source frontier
`0xffffffff826f0777`. Historically reached target, translated target, exact
terminal and leased direction compiler checks were true. The receipt's claim
is a **source-derived immutable ABI2 upload association**. Its explicit limits
remain: no kernel digest, exact kernel acknowledgment, complete batch-record
membership, complete cumulative history, or execution proof from publication
alone. See [required-publication.json](required-publication.json).

## Returned bodies and native continuation

These are deltas over the **whole drained fixed application**, including all
six warmups and ten measured samples:

| Root | Submitted / JIT entered | Retained returns | Completed native handbacks | Local, no image |
| --- | ---: | ---: | ---: | ---: |
| mmap, `0xffffffff817b6f68` | 336,042 / 336,042 | 336,042 | 0 | 0 |
| munmap, `0xffffffff8181c73b` | 336,037 / 336,037 | 0 | 336,037 | 0 |

Selected, bound, dispatch-sample and shadow-sample counts equal each root's
whole-application JIT-entry count. These counters establish returned retained
execution for mmap and finished native continuation for munmap. Munmap's zero
returns do not identify its exit PC/reason or demonstrate a nesting failure.
Separate child-image activation and delegated execution are not established
by this run; `delegation_proved=false` and
`physical_batch_length_measured=false` remain in the receipt.

The final ten selected samples contained 209,708 completed pairs, divided by
ten nominal seconds. Their concurrently observed service-counter deltas were:

| Root | Submitted / JIT entered | Retained returns | Completed native handbacks |
| --- | ---: | ---: | ---: |
| mmap | 209,702 / 209,703 | 209,707 | 0 |
| munmap | 209,702 / 209,703 | 0 | 209,705 |

Application sample lines and service counters are not read atomically.
Transport/callback latency and requests in flight cross these boundaries;
the exact conservation result belongs to the whole drained application.
The nested application receipt says `scored=true`, but both enclosing point
and campaign say `scored=false`; `quiet_performance_accepted=false` controls
the performance conclusion. No quiet qualification or measured gain follows
from this rate, and no comparison against another source/topology is made.

## Source and binary identity

[preflight.json](preflight.json) records the byte joins, idle/disk gates,
standard guest identity checks and immutable input paths. The provider's build
source and daemon's build source are distinct from the Python candidate:

| Artifact | Existing build source | SHA-256 |
| --- | --- | --- |
| Provider, 128 images | `40edde00525b71207246bbde4935767cbcb21fb7` | `594c4dbd8180a0b1e4ac1b80ded1b281445e8263d25bb1dbc29a29cbfe50865c` |
| Daemon | `76b0147cfbb58246b4a3a0f371434cd758032588` | `0a0db51b9c35dc894027d0e347a1be5abb68e7467c7c941717f7bcb39c73c9d2` |
| Identity probe | Retained standard probe | `1f5ea76cbaf6c1b0918769300bd4a827578675284d29a47bd0d00f805c177c78` |
| Workload preparation inputs | Retained userspace workload | `beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0` |

The KD kernel was `7.0.0-38-kdscope5`, Build ID
`357a7115d21941960b90262ac1165bf70d1b398e`, boot
`c0a76487-f2e8-4d51-a404-3a2db2703191`, with `preempt=lazy` and `kd_mmap=on`.
The existing host qualification gate passed with the same task set and a
configured 2,000,000 kHz frequency; this does not establish quiet performance.

The reused focused VM checks passed two basic drivers, 19 release-unit,
four direct-depth and 86 text-region tests: five drivers passed, zero failed.
The 617-file test manifest SHA-256 is
`857fa0f1993ffa1628383503340a90e6d853d81ad92ed7affdf46c3daa712853`.
[focused-result.json](focused-result.json),
[focused-source-manifest.json](focused-source-manifest.json) and
[focused.stdout](focused.stdout) retain that earlier check. The failed earlier
check at `/tmp/kdlock-discovery-batching-80a9bf40b7` remains separate; it is not
reclassified as a pass. No tests, provider build or kernel build ran again for
this normal campaign.

## Retirement, recovery and retained receipts

[original-result.json](original-result.json) is preserved byte-for-byte with
`state=MEASURED_RETIREMENT_PENDING`, `stable_point_passed=true`, and its original
`passed=false`, `drained=false`, `accepted=false`. Its SHA-256 is
`48a4880252d5775b5dbf93d4be1884faf0919abd1a5202b541e83def4ff25a0b`.
[finalization.json](finalization.json) separately confirms completed retirement,
`passed=true`, `drained=true`, state 2, zero modules/frames/writers and final idle.
The controller and recovery each returned zero, with one live campaign attempt.

[normal-control.json](normal-control.json) verifies the final normal kernel:
`7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`e36f9aec-0ae6-46a5-ac96-c8de74bf7b62`, idle. No force unload, timeout-based
drain inference, or `/root/host_fs` clearing was used.

The earlier stopped targeted handback capture was not attempted or retried.
Service tracing stayed off. No denial was observed for the independently
reviewed normal preflight, launch or completed-run evidence collection.
`official_backend_clearance_verified=false` remains explicit in the outer
receipt; this record does not claim general clearance for other actions.

The full guest evidence remains at:

```text
/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/kdlock-normal-d421-run-gvfl_nb8/processes/kd
```

The read-only collection retained 466 files, 446,922,728 content bytes, in a
447,969,280-byte archive with SHA-256
`60c3b59d3d6bd03fce405f6da8ab453ce3562c1b7fbc30ae0f315d1cacf41ae3`.
[collection-index.json](collection-index.json) records every file hash and
literal symlink target. The archive and normal orchestration receipts are
retained on the source host at:

```text
/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/bench/mmap1-normal-d421e7d5-v1/
```

[summary.json](summary.json) binds the copied receipts, counters, stage outcomes
and archive identity. Historical rejected, failed and stopped runs remain
unchanged. No second campaign or targeted observation was performed.
