# Fresh Native versus merged master campaign

Status: Nano complete (420 points); mmap1 and original-body syscall comparisons in progress.

The requested candidate `66c68c17457c0ae60d09ff1f3d89b5fff16a500c` was merged
as `1f10e050b204eb3ee747b5682211343213e3fb16`. Nano uses that frozen merge.
The MM/syscall harness is `e97e218fb087093b31a9c65944622c32db09784e`; its
production lock sources are identical. The existing scoped kernel retains its
original recipe `9f9fb90e9de861fddeb498e068c0c31122919337` and Build ID
`a3bd8cda22af4c668b952472822188c6f3708440`. Fresh validation must establish
source correspondence and each boot identity before any MM result is accepted.

Compare Linux Native and KD only, one round per point. Worker counts are
1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60.
Retain all positive and negative results without replacement measurements.

Planned coverage: 420 Nano points (ten workloads), 84 mmap1 points (threads
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
`kdlock-builddisk-clean-20261031`. The final report must record restoration
of the ordinary kernel and temporary pool settings separately from performance.

Source-host coordinators are retained under `tools/`. Measurements and builds
run only in the designated VM. Historical scores are not reused.

## Nano: fresh Native versus KD

Exactly one round at all 21 counts completed for every workload and backend.
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
correspondence to the compiled scoped-kernel recipe also passed; new same-boot
functional receipts and measurements remain required for the remaining suites.
