# One-round mmap and page-fault extension

This is the explicitly requested MM extension to the
[51-configuration lock/API screen](../catalog-single-20261026/README.md).
Every measured point has one plain round, on the standard 21 worker counts
(1–8, then 12–60 by four), workers on CPUs 0..N−1 and collector on CPU 63.
Strict host timing qualification remains failed. The user authorized exploratory
measurements with observed auxiliary QEMU workers pinned to host CPU 63.
There is no repeat variability estimate, sampled latency, or pooled result across
these distinct workloads and kernels. Private-backing host captures bracket each
whole workload; shared-mm captures bracket each point. These are endpoint
observations, not continuous timing qualification.

| Workload | Arms | Measured points | Table and chart |
| --- | --- | ---: | --- |
| Independent-mm mmap/munmap, without page access | Native | 21/21, passed and drained | [Results](mmap/README.md) |
| CPU fault cycles with private backing: MADV_DONTNEED plus checked read | Native, KD, TCLock | 63/63, passed and drained | [Results](fault/README.md) |
| Actual shared-mm mmap/munmap | Native, KD | 42/42, passed and drained | [Results](shared-mm/README.md) |

The private-backing suites use recovery kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, and committed source
`e74223c8c0d0a1f72f2c7d87560b37c3125a23f5`. Before timing, all 18 split
correctness cases, eight timed-client validation controls, nine negative receipt
oracles, two basic C programs and four targeted plan/peak-policy Python checks
passed in the VM. The validation controls are prerequisites and are excluded
from the measured one-round tables. Fault readers execute locally; the private
backing workload does not establish full Linux mmap-lock replacement or
operation-specific page-fault delegation.

The shared-mm suite uses the already installed `6.1.159-kdmm31` image, Build ID
`ef5179e8def44f0255adcd62585f62f118fee30f`, with `kd_mmap=off` for Native and
`kd_mmap=on` for KD. It reuses hash-verified prepared payload/client binaries
and actual-API correctness receipts, with fresh readiness and kernel verification
on each boot. The unchanged timed client has SHA-256
`5962210671ac238ae4df8dcca442b3cb7407efb2b5b2edb42ae637ac4902083f`.
Every point retains the 90-second post-setup interval. Native MM bodies execute
on the original task. These are explicitly separate aggregate controls, not
completion or qualification of any historical three-round paired matrix.

Only the exact absence of a positive full-cohort peak window is optional in
this aggregate screen. Worker identities, affinity, complete operation counts,
joined state, callback and ownership accounting, source lifetime, kernel faults,
and drain remain checked. No timed point is repeated after a failure.

Raw evidence is retained under
`../../raw/bench/catalog-mmap-single-20261026/` and
`../../raw/bench/catalog-sharedmm-single-20261026/` on the source host and in
matching `/root/kdlock-evidence/10.176.26.71/bench/` directories in the VM.
The generic full process-inspection and later page-fault throughput proposals,
and the planned 64-node list, remain unimplemented and supply no fabricated data.

All **126/126** measured MM points completed and drained, with no repeated timed
point. Six shared-mm KD observations (40, 44, 48, 52, 56 and 60 workers) lacked a
positive full-cohort peak window; their exact whole-run rates remain available
and the CSV marks the optional peak unavailable.

At 60 workers, the private-backing CPU-fault workload measured 5.772332 Native,
8.184430 KD and 7.233381 TCLock million cycles/s. Actual shared-mm mmap/munmap
measured 70,350.82 Native versus 6,752.42 KD cycles/s (KD about 0.096× Native).
These are different workloads and kernels, each with only one observation per
point; the private-reader result does not establish shared-mm writer performance.

The [private archive audit](evidence/private-audit.json) replayed all 84 receipts
and checked 1,811 frozen input hashes. The [shared-mm audit](evidence/shared-audit.json)
replayed all 42 receipts, 783 committed source hashes and 88 host captures.
Every published CSV rate matched its raw complete-operation count and wall time.
[Preservation hashes](evidence/preservation.json) cover the audit records and
[orchestration snapshots](evidence/orchestration/README.md). Raw archives remain
in the locations above; both backend archives were retained before recovery.

[Final recovery](evidence/recovery.json) passed with boot ID
`afe3a8d8-0c07-475b-89b4-163b822484b0`, the expected recovery kernel Build ID,
73 original modules, zero taint, no pending GRUB entry and no active project work.
No kernel image was built, modified or installed for this screen.
