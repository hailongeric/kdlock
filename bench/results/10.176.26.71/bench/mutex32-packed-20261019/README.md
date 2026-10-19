# Pipe after removing shared mutex waiter-count updates

The 32-byte candidate improves fresh pipe medians by **19.4% at eight workers**
and **20.7% at sixty workers**, while retaining native 8-byte alignment and the
current KD protocol. It still trails the old 256-byte version by **22.4% and
22.6%**. These are three-repeat, sequential source blocks in the same 64-vCPU
recovery VM, not confidence intervals or a full workload grid.

| Workers | Previous 32-byte Mops/s | Current 32-byte Mops/s | Old 256-byte Mops/s | Current / previous | Current / old |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 4.498 [4.107–4.597] | 5.370 [4.927–5.552] | 6.922 [6.626–7.111] | 1.194× | 0.776× |
| 60 | 3.456 [3.408–3.456] | 4.171 [4.001–4.191] | 5.387 [5.343–5.401] | 1.207× | 0.774× |

Values are whole-measurement median [minimum–maximum]. The timed workload is
`pipebytes/query`, 16 entries, the outer clobber caller, workers 0 through N−1,
collector 63, 2000 ms measurement, and the existing 48000-operation/1000 ms
warmup. NUMA is enabled, batch limit 1024, entry ratio limit 2, prefetch 2 and
provider UBSAN off. No result is pooled with earlier rounds or profiles.
Collection order was previous 32-byte, old 256-byte, then candidate; each block
ran six plain timings before two separate diagnostic profiles.

| Arm | Frozen source | Production identity |
| --- | --- | --- |
| `embedded32` | `cb0e8e6` | `372be89`, packed phase and exact waiter count |
| `old256` | `0324e60d6791948e9762a9916a50e8e026f073b0` | Original 256-byte object with separated fields |
| `candidate` | `35718f5` | `c2f0d9c596cc4cdd9ce765a89e4e75c37b688cc9`, versioned node records |

## Change and findings

The previous compact layout put the phase and exact waiter count in one atomic
word beside the encoded queue tail. Every published request added and subtracted
the shared count. Owner phase changes also used CAS loops to preserve concurrent
count writes. The candidate stores the exact counted interval and a nonwrapping
version in existing node padding, eliminating both shared count RMWs per request.
Gate acquisition retains its CAS; owner-only phase changes use release stores.
The public object remains 32 bytes and each node remains 320 bytes.

The cold diagnostic count validates a common snapshot across the exact node
records, returning `-EAGAIN` after bounded interference or `-ENOMEM` if its
temporary storage is unavailable. Neither error becomes an estimated count.
Acquisition and retirement allocate no auxiliary state and add no caller cleanup.
There is no auxiliary hash, shared lock refcount, registry lock or auxiliary RCU
mechanism. Existing task routing and physical wait/ACK serialization remain.
Ownership, source leases, immutable images, frame retirement, native ACKs,
admission and queue/batching rules are preserved. See the
[source review](source-review.md) and
[current implementation](../../../../../docs/design/mutex_implementation.md#current-storage-and-lookup).

The measured returned-JIT fractions, weighted by measured operations, are:

| Workers | Previous 32-byte | Current 32-byte | Old 256-byte |
| ---: | ---: | ---: | ---: |
| 8 | 93.946% | 93.289% | 97.097% |
| 60 | 96.051% | 95.414% | 95.011% |

Throughput improves while returned-JIT share falls slightly. At sixty workers,
whole-session bodies-per-combiner ratios remain near 128 for all three arms;
larger batches or increased delegation do not explain the improvement there.
These whole-session counters include warmup and checks, so they are not
measured-phase batch distributions or fallback fractions.

The candidate removes two kinds of shared-word traffic together; this experiment
does not isolate their individual contributions. Notification polling dominates
the `cycles:k` profiles, which do not measure atomic retries or cache-line
transfer costs. The old256 eight-worker profile also changes returned-JIT share
by −5.68 percentage points versus its plain runs. Profiles remain unscored.
The remaining gap and placement evidence are discussed in
[diagnostics](diagnostics.md); no performance parity is claimed.

## Validation and preserved evidence

The successful `checks-candidate-r2` snapshot passed dependencies, provider and
daemon builds, **two basic tests plus thirteen affected drivers (15/15)**, and
live ordinary-mutex, rwsem and instruction-exit probes. The local probe verifies
32-byte size, 8-byte alignment, containing-object offsets, 160000 operations,
2048 reused objects without destroy, cancellation/handoff, sleeping owners and
drain. State, snapshot, resources and balances detect 17, 12, 27 and seven
negative controls. The provider build retains 48 warning lines.

The initial `checks-candidate` attempt is preserved as a failure: 14/15 unit
checks passed and the shadow-stack harness failed to compile due to a missing
`u64` typedef. Test-only commit `35718f5` fixes it. The initial attempt did not
reach live probes; its failure is not counted as a pass.

All **18 plain timings and six profiles** passed their results/progress checks,
returned JIT bodies and drained. Every session's measured body entries equal its
matching returned completions. Twenty-seven retained kernel logs have no matched
runtime faults. Kernel Build ID, boot identity, recovery snapshot, 64-vCPU/2-NUMA
placement, host pinning and frequency policy remained unchanged. The VM retains
the checked candidate and is idle; no guest kernel changes or reboot occurred.

The independent [archive/source audit](archive-review.json) passed over 6175
members, 5342 regular files, 12 source manifests, 62 binary-manifest entries and
49 JIT binaries, with zero exceptions/issues. The independent
[arithmetic/profile audit](statistics-review.json) passed **34386 checks**, with
24 reconstructed windows and 82268 parsed samples, zero issues.

The immutable guest tree is
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-packed-20261019`.
Its grouped archives are preserved under
`bench/results/10.176.26.71/raw/bench/mutex32-packed-20261019/`, with hashes in
[archives.json](archives.json). Compact results are in
[comparison.json](comparison.json), [profile-analysis.json](profile-analysis.json),
[validation.json](validation.json) and [health.json](health.json).
[Operations](OPERATIONS.md) records commands, bounds and source mappings.
This README and the diagnostic narrative are source-host postprocessing of the
frozen evidence. No full suite, other workload grid, whole-kernel replacement,
RT/ww_mutex, lockdep or oversubscription validation is claimed.
