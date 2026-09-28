# 2026-09-28: packed spin continuation and private register packet

The requested core layout is implemented: entry/lock identity, frame state and
RIP/RSP/RBP occupy one aligned 64-byte line. The complete register packet and
continuation remain 168 and 704 bytes. This reduces the default MINIMAL
frame/packet prefetch footprint from four distinct continuation lines to three.

**It did not improve hash throughput.** The independent repeat gives KD/TCLock
peaks of **2.018 / 2.641 Mops/s at 36 threads (76.41%)**. KD's median is 2.03%
below the fresh UBSAN-off baseline. The 16-thread median is 1.01% below baseline.
The layout is retained for the requested consolidation, within the agreed
repeatable 3% median-loss screen; there is no throughput improvement claim and
the contended hash 90% target remains unmet.

## Layout and prefetch

Linux `struct pt_regs` and the existing guest kernel are unchanged. The module
now owns [kd_regs](../../../include/kd_regs.h), used by the wrapper, dispatcher,
spin and mutex recovery paths. It retains all 21 software fields. C offset
assertions and compiler-derived assembly offsets protect the shared layout.

Offsets below are from the aligned spin continuation base, confirmed with
`pahole` on the frozen guest ELF:

| Data | Old layout | New layout |
| --- | --- | --- |
| Frame base | 24 | 0 |
| Entry RIP / outer lock | 32 / 40 | 0 / 8 |
| Entry ABI / packet state | 88 / 92 | 16 / 20 |
| Depth / state / role | 76 / 72 / 74 | 24 / 28 / 30 |
| RIP / RSP / RBP | 224 / 248 / 128 | 40 / 48 / 56 |
| Virtual R15/R14/R13/R12/R11 backing | 96/104/112/120/144 | 64/72/80/88/96 |
| Packet reference / GS / logical task / parent | 24/48/56/64 | 208/216/224/232 |
| Diagnostic / storage pointers | 0 / 8 | 648 / 656 |
| 32-bit result / retired | 16 / 21 | 664 / 668 |
| Frame / continuation / storage stack size | 648 / 704 / 8512 | 648 / 704 / 8512 |

The first line contains the core identity/state and continuation triple. The
five virtual GPR backing slots share the second line. The retained packet,
GS, task and parent pointers share another line. Only the producer-owned
ROOT/VIRTUAL and decoded tags share a byte; exact state, ABI, owner/ACK and
notification widths/order are retained. Cold ledger storage still starts at
frame offset 240 and remains gated by `complex_ready`.

Default `spin_prefetch=2` uses producer-prepared addresses before executing the
current request. For an inline MINIMAL successor it issues three frame/packet
hints: core frame, virtual GPR bank, and provenance pointers. Clobber imports no
incoming full GPR set, but the translated hash still uses those five backing
slots during execution. FULL and borrowed packets retain the range hints;
complex ledgers receive their existing conditional hints. Mode 1 uses the same
new frame geometry with consumer lookup; mode 0 remains disabled.

Caller-stack hints remain `SP-8` and up to four valid upward addresses,
`SP`, `SP+64`, `SP+128`, `SP+192`, bounded by the retained task's stack. The actual
caller stack cannot be moved into the request without changing its addresses,
aliases and native continuation contract. Its authoritative SP is colocated in
the core line. The reusable scheduling node cannot replace the stable request:
node reuse may precede final owner ACK and continuation retirement.

The wrapper's physical stack layout, two-word input ABI, and entry ABI 0/1/2
are unchanged. Packet layout is versioned by **KDWB002 / KDWC002**. Both daemon
and provider require the two new tags, KDAB and exact entry ABI before NORMAL
publication, including legacy FULL bridges. Old or unmarked images are rejected.
Ownership and release/acquire ordering, queue selection, batch limits, source
leases, pinned-waiter policy and caller payload are unchanged; no per-body
hardware fence was added or removed.

The geometry does not establish cache-miss counts or remote-load latency. The
first screen prompted review of the moved result field; ordinary successful
batch completion does not write it, so this alone does not explain the loss.
The remaining cause of the small regression is unisolated. The prior
[36-thread investigation](20260928-spin36-analysis.md) separately measured extra
translated-body/request work and a NUMA effect. This change removes neither
that work nor the hash's payload accesses; fewer hinted lines were insufficient
to improve measured throughput. No new KD PMU/latency attribution is claimed.

## Conditions and measurements

Fresh baseline: `ac9c89f`, immediately before the layout edit. The implementation
is the commit containing this report; exact input and ELF hashes are archived.
All builds, unit executions, modules and measurements ran in the recovery guest,
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. QEMU's 40 vCPUs remained pinned to
matching host CPUs. Workers 0–35 and collector38 retained fixed min/max 2.5 GHz;
unused CPUs36/37/39 are not represented as fixed-frequency workers.

Every scored configuration has three rounds, NUMA-on, 1024 bodies/independent
1024 scan limit, prefetch2, default spin ratio2, 48000 warmup operations **per
worker**, a two-second measurement and the highest valid 300 ms window after
300 ms settling. All KD benchmark providers defaulted to UBSAN off; ELF audits
found no UBSAN imports. The baseline and candidate use the same policy.
Rates are Mops/s; spread is `(max-min)/median`. Whole-run statistics and every
sample are retained. This is a targeted screen at 1/2/16/24/36 threads, not a
new full 15-point matrix.

### Fresh baseline and KD regression screen

Each cell gives peak min / median / max. Rechecks are separate three-round
cohorts, never a best-of-six replacement.

| Workload / threads | Baseline KD | First packed KD | Recheck KD | First median change | Recheck median change |
| --- | --- | --- | --- | --- | --- |
| Hash / 1 | 12.074 / 12.079 / 12.086 | 12.066 / 12.067 / 12.070 | — | -0.10% | — |
| Hash / 2 | 2.406 / 2.471 / 2.659 | 2.402 / 2.404 / 2.416 | 2.377 / 2.447 / 2.551 | -2.72% | -0.98% |
| Hash / 16 | 3.958 / 3.959 / 3.969 | 3.911 / 3.911 / 3.914 | 3.919 / 3.919 / 3.920 | -1.22% | -1.01% |
| Hash / 36 | 2.058 / 2.060 / 2.062 | 2.010 / 2.014 / 2.016 | 2.014 / 2.018 / 2.018 | -2.22% | -2.03% |
| One cacheline / 1 | 40.418 / 40.907 / 40.911 | 40.900 / 42.240 / 42.247 | — | +3.26% | — |
| One cacheline / 2 | 2.584 / 2.672 / 2.792 | 2.520 / 2.547 / 2.781 | 2.580 / 2.642 / 2.852 | -4.69% | -1.13% |
| One cacheline / 16 | 9.641 / 9.829 / 9.832 | 9.750 / 9.796 / 9.864 | — | -0.34% | — |
| One cacheline / 36 | 9.191 / 9.218 / 9.222 | 9.153 / 9.157 / 9.186 | — | -0.66% | — |

The first two-thread cacheline median fell more than 3%; its recheck was 1.13%
below baseline. The hash two-thread recheck was 0.98% below baseline. These
variable cohorts remain visible; none of the protected median losses above 3%
repeated. The 36-thread hash whole-run median fell 3.09% initially and 2.06% in
the recheck, so the slowdown also appears outside the selected peak windows.

### First three-way screens

| Workload | Threads | Backend | Peak min / median / max | Spread | Whole min / median / max |
| --- | --- | --- | --- | --- | --- |
| Hash | 1 | native | 12.815 / 12.827 / 12.831 | 0.13% | 12.806 / 12.814 / 12.820 |
| Hash | 1 | tclock | 11.819 / 11.968 / 12.016 | 1.65% | 11.811 / 11.948 / 12.005 |
| Hash | 1 | kdlock | 12.066 / 12.067 / 12.070 | 0.03% | 12.048 / 12.053 / 12.056 |
| Hash | 2 | native | 2.548 / 2.597 / 2.633 | 3.25% | 2.542 / 2.587 / 2.628 |
| Hash | 2 | tclock | 5.054 / 5.055 / 5.060 | 0.12% | 5.033 / 5.041 / 5.054 |
| Hash | 2 | kdlock | 2.402 / 2.404 / 2.416 | 0.59% | 2.396 / 2.397 / 2.413 |
| Hash | 16 | native | 2.854 / 2.884 / 2.924 | 2.45% | 2.847 / 2.879 / 2.917 |
| Hash | 16 | tclock | 4.669 / 4.675 / 4.707 | 0.80% | 4.653 / 4.664 / 4.690 |
| Hash | 16 | kdlock | 3.911 / 3.911 / 3.914 | 0.09% | 3.897 / 3.901 / 3.908 |
| Hash | 36 | native | 1.980 / 1.995 / 2.049 | 3.45% | 1.852 / 1.872 / 1.927 |
| Hash | 36 | tclock | 2.630 / 2.634 / 2.653 | 0.87% | 2.614 / 2.619 / 2.630 |
| Hash | 36 | kdlock | 2.010 / 2.014 / 2.016 | 0.31% | 1.987 / 1.988 / 1.996 |
| Hash | 24 | native | 1.842 / 1.859 / 2.429 | 31.54% | 1.835 / 1.848 / 2.161 |
| Hash | 24 | tclock | 4.334 / 4.358 / 4.447 | 2.58% | 4.303 / 4.307 / 4.417 |
| Hash | 24 | kdlock | 3.354 / 3.372 / 3.616 | 7.79% | 3.322 / 3.347 / 3.605 |
| One cacheline | 1 | native | 43.806 / 43.813 / 43.816 | 0.02% | 43.594 / 43.779 / 43.800 |
| One cacheline | 1 | tclock | 36.010 / 36.463 / 36.531 | 1.43% | 35.962 / 36.424 / 36.515 |
| One cacheline | 1 | kdlock | 40.900 / 42.240 / 42.247 | 3.19% | 40.895 / 41.398 / 41.510 |
| One cacheline | 2 | native | 2.496 / 2.558 / 2.718 | 8.67% | 2.487 / 2.541 / 2.704 |
| One cacheline | 2 | tclock | 6.094 / 7.163 / 7.253 | 16.18% | 6.069 / 7.140 / 7.223 |
| One cacheline | 2 | kdlock | 2.520 / 2.547 / 2.781 | 10.27% | 2.514 / 2.538 / 2.767 |
| One cacheline | 16 | native | 3.394 / 3.407 / 3.461 | 1.98% | 3.365 / 3.371 / 3.444 |
| One cacheline | 16 | tclock | 5.851 / 5.992 / 5.994 | 2.38% | 5.836 / 5.971 / 5.977 |
| One cacheline | 16 | kdlock | 9.750 / 9.796 / 9.864 | 1.16% | 9.736 / 9.783 / 9.851 |
| One cacheline | 36 | native | 3.978 / 13.240 / 13.386 | 71.06% | 3.754 / 10.391 / 11.973 |
| One cacheline | 36 | tclock | 5.855 / 5.935 / 5.945 | 1.51% | 5.844 / 5.926 / 5.934 |
| One cacheline | 36 | kdlock | 9.153 / 9.157 / 9.186 | 0.36% | 9.123 / 9.143 / 9.162 |

### Independent rechecks

| Workload | Threads | Backend | Peak min / median / max | Spread | Whole min / median / max |
| --- | --- | --- | --- | --- | --- |
| Hash | 16 | tclock | 4.684 / 4.692 / 4.692 | 0.18% | 4.670 / 4.676 / 4.682 |
| Hash | 16 | kdlock | 3.919 / 3.919 / 3.920 | 0.04% | 3.907 / 3.911 / 3.912 |
| Hash | 36 | tclock | 2.633 / 2.635 / 2.641 | 0.32% | 2.620 / 2.621 / 2.627 |
| Hash | 36 | kdlock | 2.014 / 2.018 / 2.018 | 0.21% | 2.006 / 2.009 / 2.012 |
| Hash | 2 | native | 2.419 / 2.463 / 2.555 | 5.52% | 2.412 / 2.457 / 2.543 |
| Hash | 2 | tclock | 4.955 / 4.966 / 5.092 | 2.75% | 4.943 / 4.944 / 5.070 |
| Hash | 2 | kdlock | 2.377 / 2.447 / 2.551 | 7.15% | 2.370 / 2.443 / 2.547 |
| One cacheline | 2 | native | 2.561 / 2.644 / 2.875 | 11.87% | 2.555 / 2.632 / 2.851 |
| One cacheline | 2 | tclock | 6.289 / 7.376 / 7.832 | 20.92% | 6.271 / 7.355 / 7.784 |
| One cacheline | 2 | kdlock | 2.580 / 2.642 / 2.852 | 10.31% | 2.570 / 2.632 / 2.845 |

The hash recheck reaches 83.55% of TCLock's peak at 16 threads and 76.41% at 36;
24 threads reaches 81.33% in its first screen. None meets 90%. Among the measured
points, hash1 and cacheline1/16/36 meet the peak ratio target; two-thread KD
remains far below TCLock. Linux's variable cross-node peaks are preserved.

Every worker progressed in both the whole run and selected windows. At 36-thread
hash recheck, KD node1 received 49.97%–50.02% of whole-run work and every worker
completed at least 99072 operations. At 24 threads, its four minority-node
workers received only **0.86%–1.99%** of whole-run work (peak shares 0.85%–1.90%);
the minimum worker still completed 15104 operations. The bounded queue policy
has no starvation guarantee, and the layout change does not solve that skew.

Contended KD hash returned-body JIT shares were 99.74%–99.75% in the first
36-thread screen and 99.90% in the recheck; 16/24-thread shares were approximately
99.90%/99.80%. The gap is present while delegation executes. Small-thread native
completions are retained as such, not relabelled as JIT.

Spin TCLock exposes no delegation counter in the normal runner, so its rate is
`UNMEASURED`. A separate three-second 36-thread diagnostic used cycles at 499 Hz,
flat IP/TID/TIME/PERIOD records and no lost samples. Exact frozen ELF ranges
identified **68 samples in `komb_context_switch`** and an executing combiner.
The sampled backend ELF matches the three-way screen byte-for-byte. This is
runtime path evidence, not a delegation percentage, remote-memory measurement
or scored throughput sample.

## Correctness and build verification

Two basic programs and 22 directly affected Python drivers passed across the
recorded batches. They cover generated FULL/MINIMAL/COMPLETE and exactly-one-CALL
fallback, all register offsets, GS/task imports, guard refusal, old image
rejection, queue limits, shared/borrowed packets, storage reuse, shadow capacity,
native-peer exclusion, mutex resources and owner/ACK/source retirement.
The real final restoration assembly passed 192 cases, including final unpin
that immediately poisons reusable storage; the wait fixture sampled 96 returns.
No full unit suite was run.

Initial unit batches A/B/C retained failures from old numeric fixture assertions
and a restore-macro extractor. The specific failing drivers were corrected and
rerun; the last legacy-runner check passed in batch D. The first provider build
also stopped before any workload because an observation-patch context still
named the moved kind field. The corrected overlay built and all subsequent
sessions passed. These failures are archived rather than counted as successes.
Both baseline and packed normal builds retain the same 11 objtool warning
categories/counts after normalizing instruction offsets, plus locale warnings.
They are not warning-free builds. The SELFTEST build and ownership probe also
completed on the existing kernel.

Seven separate 36-thread functional sessions passed business/context checks and
clean drains, each completing 3600000 measured operations:

| Scenario | Payload | Returned JIT bodies |
| --- | --- | --- |
| Spin nested, ratio4 | 1 / 16 cachelines | 3043485 / 3064520 |
| Spin early outer release, ratio4 | 1 / 16 cachelines | 1107333 / 1165941 |
| Mutex plain | 1 / 16 cachelines | 271536 / 339757 |
| Mutex hash | 1024 buckets | 506 |

The mutex hash result proves execution of the new packet with the retained
policy; its low JIT count is not a high-delegation performance acceptance.
The independent `run_task_selftest.py` used real Linux mutexes and pinned tasks,
**JIT=0**, two unlock orders, four owner ACKs and two deferred frees. It passed
and drained with no active task records; its ELF also has no UBSAN imports.
This ownership probe is separate from the returned-body JIT checks.

All 141 scored performance sessions (30 baseline, 111 packed/rechecks), seven
functional sessions and one non-scoring TCLock diagnostic passed their runtime
checks. The additional ownership probe passed separately. There were no detected
kernel faults or residual benchmark modules/workers. Source/binary manifests,
UBSAN policy, worker placement/progress and final drain were audited. No new
kernel, oversubscription policy, mutex scheduling policy or source-retirement
semantics were introduced.

## Evidence and reproduction

Host evidence: `bench/.tmp/layout-20260928/`; guest phases use
`/root/kdlock-evidence/numa-20260928-layout-*` and
`numa-20260928-mutex-layout-*`. Their environment files contain exact arguments;
unit command files identify the selected drivers. The archive includes raw
records/windows, frozen inputs/ELFs, build/kernel logs, initial failures,
compiled layouts, disassembly, diagnostic samples and the ownership probe.

Archive: `/root/kdlock-evidence/layout-20260928-evidence.tar.gz`, copied to
`bench/.tmp/layout-20260928/evidence.tar.gz`.
SHA256: `3fb7ba554fd69ad1a98ae62b06d105334e34c6f84463b01b1611219e5b012687`.
Host snapshot confirmation, before/after affinity/frequency, controller logs and
offline `summary.json` live beside it. Failed aggregate-audit attempts are also
preserved: they exposed an unavailable TCLock counter and NOT_RUN placeholders
from the pre-workload build failure; final auditing distinguishes both explicitly.

For performance, use the guest three-way runner with `--threads 16 36
--workload rcuht --duration-ms 2000 --peak-window-ms 300 --collector-cpu 38
--repeats 3`, current kernel source/baseline arguments and a fresh output directory.
The default provider policy is off; no UBSAN option is required. Functional
nested/early runs use `--functional --backends kdlock --repeats 1 --threads 36
--spin-entry-ratio-limit 4`, and mutex runs use `run_mutex.py`. Operational
snapshot, identity and drain rules remain in [AGENTS](../../../docs/AGENTS.md).
