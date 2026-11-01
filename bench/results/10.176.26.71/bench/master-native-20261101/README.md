# Fresh Native versus merged master campaign

Status: complete. All 630 requested measurements finished once per point; raw evidence, gains, losses and setup failures are retained.

The requested candidate `66c68c17457c0ae60d09ff1f3d89b5fff16a500c` was merged
as `1f10e050b204eb3ee747b5682211343213e3fb16`. Nano uses that frozen merge.
The MM/syscall harness is `e97e218fb087093b31a9c65944622c32db09784e`; its
production lock sources are identical. The existing scoped kernel retains its
original recipe `9f9fb90e9de861fddeb498e068c0c31122919337` and Build ID
`a3bd8cda22af4c668b952472822188c6f3708440`. Fresh source correspondence,
kernel identity, same-boot functional and host endpoint checks passed for both
MM modes.

Compare Linux Native and KD only, one round per point. Worker counts are
1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60.
Retain all positive and negative results without replacement measurements.

Completed coverage: 420 Nano points (ten workloads), 84 mmap1 points (threads
and processes separately), and 126 original-body syscall points (setfd,
FIONREAD, F_GETPIPE_SZ). Functional invocations are unscored prerequisites.

## Initial correctness and setup

Eight affected unit groups, rwsem, local mutex and the basic suite passed on
the frozen merge, with source hashes unchanged and drain recorded. The first
basic invocation stopped before a workload because the controller affinity
was restricted to CPU63. The second stopped while writing a host-input file
whose parent directory did not exist. Both attempts are retained; the corrected
third basic invocation passed. No measurement point was repeated.

The fresh host cohort uses the existing two-node 64-vCPU topology, fixed
frequency and temporary 64-worker QEMU pool. The actual recovery snapshot is
`kdlock-builddisk-clean-20261031`. The final report records restoration
of the ordinary kernel and temporary pool settings separately from performance.

Source-host coordinators are retained under `tools/`. Measurements and builds
run only in the designated VM. Historical scores are not reused.

## Nano: fresh Native versus KD

`c01` and `c16` mean one and sixteen aligned cachelines. `w1`, `w20` and
`w100` mean 1%, 20% and 100% writes. Exactly one round at all 21 counts completed
for every workload and backend.
The full archive is retained and hash-verified; all ten record-file hashes match
the 420-point summary. The whole-run rate counts all completed operations over
the joined phase wall time. Peak rates remain separate columns in
[nano/points.csv](nano/points.csv). Positive and negative points are retained.

| Workload | Whole-run geometric-mean change | Worst point | At 60 workers |
| --- | ---: | ---: | ---: |
| mutex-c01-w100 | +50.67% | -9.33% at 6 | +145.95% |
| mutex-c16-w100 | +61.42% | -11.71% at 3 | +175.33% |
| rwlock-c01-w1 | +7.59% | -7.05% at 8 | +10.00% |
| rwlock-c01-w20 | +19.77% | -0.07% at 3 | +8.71% |
| rwlock-c16-w1 | -4.26% | -21.24% at 48 | -12.20% |
| rwlock-c16-w20 | +11.17% | +0.12% at 1 | +8.60% |
| rwsem-c01-w1 | +93.44% | -16.80% at 3 | +164.39% |
| rwsem-c01-w20 | +149.92% | -22.95% at 3 | +214.28% |
| rwsem-c16-w1 | +142.45% | -17.60% at 2 | +309.05% |
| rwsem-c16-w20 | +150.27% | -5.78% at 1 | +232.17% |

These are single-round observations against Native, not a repeat of the previous
master-versus-candidate acceptance comparison. In particular, rwlock c16-w1 has
a negative geometric mean; the gains in other rows do not remove that result.
The host endpoint audit passed with unchanged pinned task identities and fixed
frequency configuration; the final capture followed completion by 1.206 seconds.
See [the endpoint receipt](nano/host-endpoints.json) and
[the archive receipt](nano/archive.json).

The six affected MM/syscall harness unit groups subsequently passed. Source
correspondence to the compiled scoped-kernel recipe also passed; same-boot
functional receipts and measurements subsequently passed for both MM arms and
the original-body syscall suite.

## mmap1: unchanged application

Both modes use the same scoped kernel image and unchanged will-it-scale
executables from `75f66e45697e6f5f49c33dd950c4e6b289198f8f`. Native mode
uses Linux rwsem; KD mode replaces its lock backend. Native MM bodies execute
on the originating task. These results do not demonstrate delegated MM bodies.
Each score is the mean of the two original post-marker one-second samples,
in mmap/munmap pairs per nominal second. Threads and processes are separate.

| Model | Geometric-mean change | Worst point | Native at 60 | KD at 60 | Change at 60 |
| --- | ---: | ---: | ---: | ---: | ---: |
| processes | -0.28% | -3.08% at 3 | 1,252,931.0 | 1,254,773.0 | +0.15% |
| threads | +3.35% | -6.40% at 4 | 114,904.0 | 126,258.0 | +9.88% |

All [42 paired model/count rows](comparison/mmap1/points.csv) retain both Native
and KD scores. Actual-MM API/cancellation/rollback/downgrade, mapping, fault,
completed-fault, exact held-writer and application-object identity checks passed
on each selected boot before timing. Both endpoint checks passed.

## Original-body syscall comparison

Both syscall arms ran on the same `kdscope4-native` boot and object layout, with
`api_bind=1`. The original kernel bodies are preserved; the experiment replaces
lock calls and the required object binding/lifetime routing. Setfd counts an
F_SETFD plus F_GETFD pair as one operation; each pipe operation is one syscall.
The pipe has sixteen filled pages. Extracted-body adapters are not included.

| Workload | Geometric-mean change | Worst point | At 60 workers |
| --- | ---: | ---: | ---: |
| setfd | +52.93% | -2.61% at 3 | +149.44% |
| FIONREAD | -15.71% | -38.87% at 5 | +7.10% |
| F_GETPIPE_SZ | +28.25% | -20.01% at 6 | +98.27% |

All [63 paired syscall/count rows](syscall/points.csv) are retained. The six
unscored functional arms passed, including positive returned KD bodies, syscall
oracles, exact object/backend identity and final retirement. Scored sessions
disabled body observations, so those scores do not prove per-point JIT execution.
Strict [before/after host comparisons](syscall/host-endpoints.json) passed.

## Interpretation and retained limits

These are single-round observations, without a variance estimate. The comparison
is fresh Native versus KD within each suite, with exact source/image identities;
no earlier score supplies a baseline. It does not remeasure prior master-relative
losses or establish their recovery. In particular, no previous promotion-policy
gate is declared passed by this Native comparison. The negative rwlock c16-w1
and FIONREAD means and every individual loss remain visible.

Native controls use the scoped image and its routing/object layout for MM and
syscalls. They are not a separate stock-kernel boot. Nano uses the ordinary
`7.0.0-38-kdlock1` image. Results from these distinct suites are not pooled into
one score. Whole-kernel lock replacement remains outside this validation.

## Restoration and reproducibility

The final read-only health receipt confirms idle `7.0.0-38-kdlock1`, boot
`3deecc38-d39f-4966-b1ff-9abecda3f029`, and an unbound source view. Its normal
schema-2 bundle verified. The temporary QEMU settings returned to minimum 0,
maximum 64 workers and aio-max-batch 0. This restores the settings; it does not
claim the old worker task map or QOM absence was restored. All old builds,
snapshots and results remain preserved.

In addition to the two initial basic setup failures, the first post-reboot
source bind stopped because reboot removed a `/tmp` manifest. The manifest
was placed on DATA2 and execution resumed from the already verified Native
boot, before any MM or syscall timing. No scored point was repeated.

[Consolidated numeric summaries](comparison/summary.json),
[raw archive hashes](comparison/archive-sha256.json), the per-arm receipts in
`mm/`, and `provenance/` retain the exact evidence. Full archives are under
`bench/results/10.176.26.71/raw/bench/master-native-20261101/` on the source
host and the recorded DATA/DATA2 paths in the VM. The analysis rechecked all
420 Nano, 84 mmap1 and 126 syscall records, exact grid/round coverage, completion
and drain, and the common mmap1 executable hashes.
