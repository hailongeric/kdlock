# Fresh Native versus merged master campaign

Status: in progress. No completed performance comparison is claimed.

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
