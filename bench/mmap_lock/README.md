# Built-in mmap lock performance

Current work is throughput only. The prospective `plain-scaling-v1` plan selects
**126 plain sessions** across 21 worker counts, Native/KD and three repetitions.
It has [41 focused mocked test passes](../results/10.176.26.71/tests/mmap-scaling-plan-20261026/README.md);
no expanded live campaign has run or is authorized by this guide.
The [prepared-window interface](#prepared-window-interface) passed offline
tooling checks. Its [small live attempt](../results/10.176.26.71/bench/mmap-window-screen-20261026/README.md)
stopped after the Native boot: admission captured 82 QEMU tasks, which the
empty reviewed role manifest could not admit. Readiness, payloads and timing
never started; recovery was restored. The attempt also omitted post-idle
settling: the earlier procedure required 60 seconds and the later user
instruction requires 90 seconds. It supplies no current throughput and
cannot reclassify any rejected historical run.
The separately versioned [QEMU worker policy](QEMU_WORKERS.md),
`qemu-workers-v1`, now admits verified QEMU auxiliary lifetimes and records
their activity. Its [focused VM fixtures](../results/10.176.26.71/tests/mmap-worker-admission-20261026/README.md)
pass; the corrected two-arm validation is still pending. Extra workers alone
are not a rejection under this explicit policy.
The earlier 12-session `plain-v1` attempt [stopped before boot](../results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
at **68 QEMU tasks versus 67**. One full capture ran; all 12 measurements and
six unscored checks remain unrun. The historical 24-case plain/sampled plan
is `paired-v1`; omitted plan fields retain that historical meaning. Never obtain
a different campaign by skipping or relabelling old receipts.

The prepared comparison uses the unchanged shared-mm
[writer workload](../mmap_writer/README.md), with Native and KD selected by
`kd_mmap=off/on` in the **same** `6.1.159-kdmm31` image. Each live cycle requires
exact approval and fresh admission; preparation alone does not authorize it.
The earlier authorized October 25 attempt [stopped at first admission](../results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
with 73 QEMU tasks versus 67. It consumed one host capture and no boots or
payload checks; all 24 measured sessions remain unrun. The stop remains in force.
No current qualified rate or optimization gain has been established.
The [audit and preparation receipt](../results/10.176.26.71/bench/mmap-perf-prep-20261025/README.md)
records the remaining limits and retained failures.
The separate [QEMU diagnostic](DIAGNOSTIC.md) cannot qualify a benchmark.
Its first authorized attempt stopped during initial observation; the guide
tracks the separate timing correction and execution boundary.

Private reconstruction and build-3 preparation have passed, including all 16
payload import CRCs and base/split BTF parsing with existing pahole 1.25. The
two basic programs and 30 mocked tooling tests passed: 16 capture and 14
paired/report, including the four latest review fixes. Preparation has loaded
no module or booted a kernel; it is not runtime
readiness or performance acceptance.

`plain.py`, `serial.py` and the older
[comparison plan](../../kernel_integration/mmap_lock/COMPARISON_PLAN.md) bind
historical kdmm1 inputs. Preserve them; do not relabel their output as kdmm31.
The maintained `paired.py` binds [kdmm31.json](kdmm31.json) and supplies a mode
label only after checking the actual image, boot arguments and module set.

## Prepared-window interface

Select `--measurement-policy mmap-window-v2` explicitly at `paired.py ready`
and at the source controller. Missing policy means the original
`mmap-transport-v1`, including its exact 67-task gate. The campaign identifier
remains `plain-scaling-v1`; its 21 counts and 126 sessions do not change.
Runner and report replay reject mixed policies, sources, builds and readiness.
The [offline validation receipt](../results/10.176.26.71/tests/mmap-window-20261026/README.md)
records the tests and their limits. No live window has been qualified.

The workload remains real userspace `mmap()`/`munmap()` syscall throughput:
`timed_client.c::worker()` maps one **4 KiB**, `PROT_READ`, `MAP_SHARED` range
through the device file, never touches it, and counts one completed pair.
Pthreads share one mm and mmap lock. `MW_ID`/`MW_STATS` ioctls obtain identity
and counters outside the loop; they do not execute the measured mappings.
The payload's mmap/VMA callbacks retain exact accounting and add overhead.
This is distinct from will-it-scale's larger anonymous private mappings and
from a map/touch/unmap or `MAP_POPULATE` workload. Native MM/fault bodies and
the originating task remain unchanged.

All guest SSH setup, input verification, payload loading, descriptor/worker
allocation and readiness complete before `PREPARED`. The guest bridge holds
client output in bounded memory. An explicit `GO` releases the existing
100 ms scheduled delay and two-second workload. After joins and final close,
`FINISHED` supplies a fresh completion token. The controller captures the host
measurement endpoint before sending `EXPORT` with that token and the endpoint
hash. Receipt files and bulk output follow. The later SSH-exit/full-capture
endpoint remains separate. A failed exchange cannot authorize unload;
`finish` still requires normal completion, exact business counts and drain.

One prospective guard requires at least two seconds and five complete scans,
nominally 500 ms apart, within ten seconds. Scan/start gaps above one second
fail the attempt. Observation continues through the completion endpoint;
there is no restart of a failed quiet interval. These are versioned engineering
bounds, not timing constants established by the old diagnostic. Causal message
ordering encloses the workload; host and guest monotonic clocks are not directly
subtracted. Control traffic is included in this conservative enclosure.

The original 64 vCPU identities/pins and three service tasks remain exact.
Admission policy is separate from the unchanged `mmap-window-v2` control
protocol. A manifest without `admission_policy` selects `fixed-aux-v1` and
retains the original rules below. The explicit `qemu-workers-v1` policy uses
[qemu_worker_roles.json](qemu_worker_roles.json), bound to
[its reviewed scope](QEMU_WORKERS.md). It verifies `Pid`/`Tgid` membership in
the bound QEMU process, permits CPU63 `worker` creation/retirement between
complete scans and records counters separately for each `(tid,start_ticks)`.
Neither sleep state nor nonzero activity alone decides acceptance. Partial
scans still fail; observed deltas do not cover whole departed lifetimes or
tasks missed between scans. Both arms must bind the same policy and manifest.

Under `fixed-aux-v1`:
Additional tasks must match an explicitly reviewed role manifest, then their
`(tid,start_ticks)` identities and affinity are frozen at the first guard scan.
An `inactive_auxiliary` must remain sleeping with no increase in any recorded
CPU, scheduling, queue-wait or I/O counter. Sleeping alone never suffices.
Expected vCPU/service activity is recorded rather than required to be zero;
an additional `expected_service` role needs evidence explaining why its activity
belongs in this workload/control path. Unknown or ambiguous roles, partial reads,
counter regression, identity churn and affinity drift reject the window.

The role manifest has `roles` and `evidence` keys and may explicitly select
`admission_policy`. Each role has `comm`,
`affinity: [63]`, `class`, a nonempty `reason`, and `evidence` equal to a SHA-256
in the manifest's `{ "evidence-file-path": "sha256" }` map. It does not list
prospective TIDs; the observer resolves those once after setup. Both arms bind
the same manifest. A `worker` name or CPU63 pin alone does not justify a role.
The diagnostic's TID 553662 and that incomplete run remain rejected. The new
manifest is prospective; it cannot replace missing historical window evidence
and does not attribute the origin of individual I/O operations.

Only the host observer is placed on spare CPU62; QEMU and guest pins remain
unchanged. Receipts retain observer CPU/elapsed time, bytes, gaps and task-counter
deltas. Polling can miss an entire short-lived task between scans and cannot
exclude delayed device effects. This policy does not assert zero interference.

### Small matched validation screen

After review of this exact scope and recovery plan, use the installed kdmm31
Native and KD entries in that order, then return to recovery. Reuse build-3's
payload and fixed client. In the idle recovery VM, rebuild only timed userspace
from the synchronized, committed source manifest:

```sh
python3 bench/mmap_lock/prepare.py \
  --reuse-payload /root/kdlock-evidence/10.176.26.71/bench/mmap-kdmm31-prep-20261025/build-3/result.json \
  --source-manifest COMMITTED-SOURCE.json --output WINDOW-BUILD
```

For each candidate boot, verify guest idle, then capture fresh host admission using
`controller.py --output LOCAL-ADMISSION`. The worker policy enforces the single
user-required 90-second interval after timed-payload setup, before launching
the unchanged client; it records guest monotonic start/end timestamps. The
client's existing 30-second control timeout is unaffected. This scheduled
interval is never repeated until a capture passes, and never delays measurement
or transport endpoints. Copy the admitted JSON and exact role manifest to the
guest before preparation. With the pinned Python/environment and actual boot
ID, run the following in the guest, substituting `native/0` then `kd/1` for
`MODE/BLOCK`. `PRIOR` is the retained `mmap-kdmm31-prep-20261025/prior` directory;
all output paths must be new and absolute:

```sh
python3 bench/mmap_lock/paired.py ready --plan plain-scaling-v1 \
  --measurement-policy mmap-window-v2 --prepared WINDOW-BUILD/result.json \
  --window-roles GUEST-ROLES.json \
  --native-api PRIOR/actual-native-1.json --kd-api PRIOR/actual-kd-1.json \
  --mode MODE --block BLOCK --boot-id ACTUAL-BOOT-ID \
  --host-state GUEST-ADMISSION.json --output GUEST-READY
```

On 380G10, use the same reviewed role manifest for both arms. The existing guest
connection carries all start/completion/export messages:

```sh
python3 bench/mmap_lock/controller.py --measurement-policy mmap-window-v2 \
  --window-roles REVIEWED-ROLES.json --output LOCAL-CASE \
  --admission LOCAL-ADMISSION/host-endpoint.json \
  --receipt GUEST-CASE/client-result.json \
  --remote-command 'cd /root/host_fs/kdlock && env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z /root/kdlock-translation-venv-20261019/bin/python3 bench/mmap_lock/paired.py screen --ready GUEST-READY/result.json --host-state GUEST-ADMISSION.json --output GUEST-CASE'
```

Copy the controller directory unchanged to a new guest evidence path only after
transport completes. In the guest, finalize that case before another workload:

```sh
python3 bench/mmap_lock/paired.py finish --output GUEST-CASE --controller GUEST-CONTROLLER
python3 bench/mmap_lock/report.py --screen NATIVE-CASE/result.json KD-CASE/result.json
```

`screen` executes one 16-worker/5,000-iteration fixed writer proof, unloads,
then runs one controlled 16-worker plain case. Report replay requires both
qualified/drained arms with the same build and role policy. It reports the two
rates and their ratio as **one unscored harness-validation pair**, with no
variability estimate or optimization claim. Screen receipts cannot enter the
126-case report. Stop on the first failure; no quiet retry, provider diagnostic,
new workload, kernel build or installation is included.

| Bounded screen scope | Count/limit |
| --- | --- |
| Timed sessions / fixed proofs / payload cycles | 2 / 2 / 4; no warmup or retry |
| Boots | 3: Native, KD, recovery; exact installed hashes and recovery entry required |
| Full host captures | 8: initial recovery, then admission/window endpoint/transport endpoint per arm, final recovery |
| Window observations | At most 97 per arm including final sample, 194 total; separate from full captures |
| Timed targets / scheduled delays / minimum guards | 4 s / 0.2 s / 4 s; none proves completion |
| Worker-policy post-setup settling | One recorded 90 s interval per arm; 180 s total |
| Control bounds | 240 s preparation; 30 s each controller guard, measurement, endpoint and publication phase; 30 s each later capture, observer wait and fetch |
| Other command bounds | Fixed proof 120 s; ordinary guest commands 30 s; client-only compile 60 s |
| Accepted output limits per case | Client 1 MiB; each error channel 64 KiB; host stream 16 MiB; endpoint frame 4 MiB |
| Storage planning | Reserve 256 MiB per retention filesystem for raw plus archive, before execution |

The storage allowance assumes eight 1 MiB full captures, twelve 256 KiB dmesg
logs, two 1 MiB fixed receipts, bounded streams/results and 16 MiB shared
inputs, then two retained copies plus headroom. Legacy full-capture and dmesg
sizes are planning assumptions, not enforced byte caps. Recheck free space and
actual retained sizes. Deadline expiry records uncertain completion, never
permission to signal workers, force unload or reboot. After proven drain and
idle, recover through the preserved recovery entry and recheck the original
73 modules, taint, boot policy and empty pending-boot entry. No live execution
is authorized by these commands alone.

## Plain throughput plan

Select **`--plan plain-scaling-v1`** on every `paired.py ready` call for the
expanded comparison. Cases 0–20 are exactly, in order:

```text
1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60
```

Each count has Native and KD arms with three paired repetitions, giving
21 × 2 × 3 = **126 measured sessions per workload**. This runner currently
implements only the existing shared-mm writer workload. Applying that arithmetic
to another workload does not supply its driver, equivalence or live approval.
All cases are plain, with zero latency samples; existing 10 ms progress and exact
correctness/lifetime checks remain. The same image/configuration, payload and
clients are used for both backends, with `kd_mmap=off/on` selecting the backend.

Workers use CPUs 0..N−1, with collector CPU 63 separate; there is no 64-worker
case. Counts through 32 occupy guest node 0; higher counts span nodes 0 and 1
(32/28 workers at 60). Collector-first-touch buffers are not per-worker-local
allocations. This sweep changes contention and NUMA placement together and
does not isolate a NUMA effect. No memory policy changes are implied. The
unchanged client still allocates 30 MiB of unused latency arrays at 60 workers,
about 248 KiB of progress storage and pthread stacks; plain output still contains
zero latency observations.

| Boot block | Work in `plain-scaling-v1` |
| --- | --- |
| 0, Native | One 16-worker fixed proof, then 21 unscored plain controls |
| 1, KD | Same validation, then repeat 0: cases 0–20 |
| 2, Native | Repeats 0 and 1: cases 0–20 each |
| 3, KD | Repeats 1 and 2: cases 0–20 each |
| 4, Native | Repeat 2: cases 0–20 |
| Recovery | Return to preserved recovery after proven drain |

There are **44 unscored checks, 170 payload cycles, 259 full host captures and
six boots including recovery**. These are maxima without retries. No dedicated
warmup is added. Fixed observed writer-chain proofs remain at 16 workers;
unobserved timed controls cover every count but do not establish observed chains
at every count. Adjacent repetitions share boots. Report every rate, paired
KD/Native ratio, median, range and sample coefficient of variation; retain losses
and rejected cases. Exact plan, source, readiness, predecessor and boot bindings
are checked at run and replay. No mixed/partial plan can be scored.

Run the pure estimate command in the VM; it does not launch a workload or capture:

```sh
PYTHONDONTWRITEBYTECODE=1 /root/kdlock-translation-venv-20261019/bin/python3 \
  bench/mmap_lock/paired.py describe --plan plain-scaling-v1
```

The derived timed targets total **336 seconds**, plus **16.8 seconds** scheduled
start delays. Neither is a completion bound. Default planning assumptions add
120 seconds per boot, 2 seconds per host capture, 5 seconds per timed-case setup,
drain and saved validation replay, 30 seconds per fixed check, 10 seconds per
readiness/recovery check and 1 second per final report case. The resulting
estimate is **2,676.8 seconds (44 min 36.8 s)**, not a measured duration.

The estimate counts **639 dmesg dumps**: five readiness, four fixed-proof,
126 timed-control and 504 measurement logs. Each measurement replays 42 saved
timed controls and two fixed proofs before launch: 5,292/252 saved replays over
the campaign, repeated again by final reporting. These are reads/validation,
not additional payload cycles. With 2 MiB per payload cycle, 1 MiB per capture,
256 KiB per dmesg dump, 2 MiB per readiness/recovery and 16 MiB shared overhead,
one retained copy is **786.75 MiB**. Raw plus archive with 25% headroom is
**1,966.875 MiB**, rounded to **2 GiB on each retention filesystem** with no
compression credit. Recheck actual log sizes, filesystem space and scope before
requesting execution; build/install storage is excluded. Do not reuse the older
512 MiB campaign allowance for this plan.

These older planning estimates exclude the worker policy's 90-second interval
per timed-client preparation; they are not duration estimates for that policy.
The command sequence below remains `ready`, `validate`, `run`, `finish`, `report`;
use `--plan plain-scaling-v1` at each ready, cases 0–20 and the block order above.
Later commands inherit the bound plan. Synchronize reviewed inputs only while
idle before any separately approved live campaign. Default legacy admission
retains the exact original **67-QEMU-task** rule, unrelated to workload worker
count. The explicit prepared-window policy is described separately above.

## Retained smaller plain plan

Select `--plan plain-v1` on **each** `paired.py ready` invocation. Its bound
readiness selects the plan for validation, run, finish and report; those actions
reject a new `--plan` override. New receipts carry `plan: plain-v1`. Reports
reject mixed/unknown plans, missing or duplicate cases, mismatched validation
and readiness, changed instrumentation, predecessor gaps and rejected endpoints.
Historical 24-case reports retain their existing output and validation shape.

| Setting | `plain-v1` |
| --- | --- |
| Image/backend | Same installed `6.1.159-kdmm31`, `kd_mmap=off/on`; Native/KD local |
| Cases per trial | Case 0: 1 worker, plain; case 1: 16 workers, plain |
| Placement | CPUs 0..N-1 on node 0; collector 63; existing host/guest topology |
| Work | Untouched shared-mm mmap/munmap cycles, original-task native MM bodies |
| Timing | Existing two-second client, 10 ms progress accounting, 32-operation stop checks; no latency samples |
| Repetitions | K0/N0, N1/K1, K2/N2; two cases per arm, 12 measured sessions |
| Validation | Per backend: one fixed 16-worker writer-proof check plus two plain timed-client checks |
| Maximum cycle | 6 boots, 18 payload load/run/unload checks, 31 full host captures |

Boot order is unchanged: initial Native validation (block 0), KD validation/K0
(1), N0/N1 (2), K1/K2 (3), N2 (4), then recovery. Four blocks contain measurements;
adjacent repetitions share boots and are not independent boot replications.
Six unscored checks plus twelve measurements give 18 payload cycles. Captures
are one initial, five boot-readiness, two per measurement and one recovery check:
1 + 5 + 24 + 1 = 31. Stop on the first failure; these are maxima, not retry budgets.
Only the existing writer payload is loaded. No provider diagnostic is repeated.

After exact cycle/recovery approval and successful fresh admission, the ready
interface is, with actual paths/mode/block/boot ID:

```sh
python3 bench/mmap_lock/paired.py ready --plan plain-v1 \
  --prepared BUILD/result.json --native-api PRIOR/actual-native-1.json \
  --kd-api PRIOR/actual-kd-1.json --mode native --block 0 \
  --boot-id ACTUAL-BOOT-ID --host-state ADMISSION.json --output BOOT/ready
python3 bench/mmap_lock/paired.py validate \
  --ready BOOT/ready/result.json --output BOOT/validation
```

Use the same controller/run/finish transport shown below, with case indices
**0 and 1 only**, the bound plain readiness, both plain validation receipts and
the exact preceding qualified case. Report exactly the twelve saved final
receipts using `report.py`; it derives the plan from bound receipts, not a flag.
The report retains every session rate, paired KD/Native throughput ratio,
median, min/max and sample CV. Throughput is completed whole cycles divided by
actual elapsed time. It publishes no latency or sampled/plain comparison.
Progress, callbacks, business correctness, exact mm/VMA drain and immediate
endpoint checks remain mandatory. Three pairs are exploratory.

The [25 focused mocked checks](../results/10.176.26.71/tests/mmap-plain-plan-20261025/README.md)
passed: 11 new plain-plan fixtures and 14 directly affected historical tests.
Prepared binaries are reused; this is not new actual mmap validation, a boot
approval or a measured performance result. The prior admission stop still applies.

## Work and measurements in the stopped plan

Pthreads share the exact originating mm, mmap lock and payload object. They map
and unmap one untouched page. Creating/removing VMAs uses writer ownership;
munmap can downgrade. This does not measure sustained concurrent-reader scaling.
A zero fault count means zero **payload mapping callbacks**, not zero incidental
process/kernel faults. Native MM bodies and original-task execution are unchanged.

| Setting | Fixed value |
|---|---|
| Backend | Native, KD local; no delegation/provider/JIT/TCLock arm |
| Workers | 1 and 16, CPUs 0..N-1, guest NUMA node 0 |
| Collector | CPU 63; both guest nodes retain their original mapping |
| Duration | 2 seconds per session |
| Observation | Plain or sampled, reported separately; payload `observe=0` |
| Latency samples | Every 64th whole mmap/munmap cycle, staggered by worker |
| Progress | 10 ms sampling, 256-operation publication checkpoints |
| Stop clock | Every 32 operations in both observation modes |
| Peak | Existing conservative 300 ms window after 300 ms settling |
| Repetition | Three pairs per worker count and observation: 24 measured sessions |

Retain raw per-worker cycle samples, progress, CPU time, callbacks, identities,
joins and health. Report whole-cycle throughput, each session's p50/p95/p99,
paired KD/Native throughput ratios, median, range and sample coefficient of
variation (`sample_cv` is a fraction, not a percentage). Retain the sample count
for each session. The report also gives sampled/plain throughput ratios; their
fixed observation order prevents treating them as a causal overhead estimate.
With only three pairs, do not imply precise confidence intervals.
Never pool latency samples between observations, repetitions, builds or workloads.
Cycle latency is not isolated acquisition, mmap or munmap latency. Counters,
progress and clock checks remain overhead. These cases are a bounded subset of
the broader [mmap-churn proposal](../../docs/BENCHMARK_WORKLOADS.md).

TCLock comparisons belong in supported ordinary mutex/rwsem microbenchmarks with
identical caller shells and workload semantics. Its restricted rwsem port has
no equivalent killable/downgrade mmap interface. The separate private-mm backing
lock/fault workload is not a substitute for actual mmap-lock measurements.

## Retained boot and validation proposal

No new kernel image, initramfs, module installation or kernel build is required.
The installed Native/KD entries use Build ID
`ef5179e8def44f0255adcd62585f62f118fee30f`. Before a live cycle, recheck their
hashes, the recovery default and actual snapshot availability.

| Boot | `--mode` / `--block` | Entry / work |
|---|---|---|
| 1 | `native` / `0` | `kd-mmap-native-kdmm31`: validate the prepared payload and clients |
| 2 | `kd` / `1` | `kd-mmap-kd-kdmm31`: validate, then K0 |
| 3 | `native` / `2` | `kd-mmap-native-kdmm31`: N0 then N1 |
| 4 | `kd` / `3` | `kd-mmap-kd-kdmm31`: K1 then K2 |
| 5 | `native` / `4` | `kd-mmap-native-kdmm31`: N2 |
| 6 | Not a measured block | Existing `6.1.159-kdclobber2` recovery entry |

Each N/K trial runs 1/plain, 1/sampled, 16/plain, 16/sampled in that order.
Measured pair order is K0/N0, N1/K1, K2/N2. Adjacent repetitions share a boot;
they are not independent boot replications. Both validations must finish before
K0. Each validation is one `observe=1` 16-worker, 5,000-cycle-per-worker run,
including the exact ELF writer-chain proof and existing negative proof mutations,
then four unscored two-second timed-client checks. This is ten unscored checks
plus 24 measured sessions, not a full correctness matrix. Reuse the preserved
137-Native/161-KD actual mmap API results; standalone 352 assertions and two basic
programs are separate evidence.

The proposed upper bounds are six boots, 34 writer-payload load/run/unload
checks and 55 read-only host captures: one before the cycle, five for boot
readiness, 48 measurement boundaries and one recovery check. Stop at the first
failed gate; these are maxima, not permission to fill rejected cases with retries.
Recovery may normally load only recorded original modules that are absent;
an unexpected module set requires investigation. No snapshot restore or new
provider diagnostic is included.

Each check/session loads only `kd_mmap_writer_native`, then requires exact
business counters and `files=0 mm_refs=0 destroyed=1 release_errors=0` before a
normal unload. There is no provider load or rerun of its one-attempt diagnostic.

Stop on any identity/policy mismatch, missing correctness proof, kernel fault,
client timeout, drain failure or rejected endpoint. Retain failed inputs and
receipts. Never retry until quiet, force unload, signal blocked workers, or
interpret SSH completion as drain. After proven idle, return using the existing
recovery entry; otherwise inspect the outstanding process/ownership state before
any recovery action. No snapshot restore, VM restart, unrelated unload or settings
change is included in this proposal.

## Reconstruct and build before requesting live approval

Follow [VM operations](../../docs/operations/VM.md). Only source edits and static
inspection run on 380G10; compilation and tests run in the idle recovery VM.
Synchronize tracked files with `tools/vm/sync_to_vm.py`. Record source hashes,
including private `.inc` files used by the collectors. The original controller
is preserved on `archive/host-capture-control-before-audit-20261025`.

The corrected build links point into vanished tmpfs. A source-only identity
bundle cannot build compatible external modules. Use the retained base, exact
delta and post-install module index as described in the
[reconstruction guide](../../kernel_integration/mmap_lock/README.md#reusing-the-corrected-build).
A fresh private reconstruction command in the guest is:

```sh
cd /root/host_fs/kdlock
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
KDLOCK_BUILD_DIR=/dev/shm/NEW-kdmm31-build
python3 kernel_integration/mmap_lock/restore_build.py \
  --delta /dev/shm/kdmm31-perf-prep-20261025-inputs/kdmm31-delta.tar.gz \
  --output "$KDLOCK_BUILD_DIR"
```

Outputs must be new. Do not remove existing trees or evidence to rerun this.
The preparation command builds the unchanged payload and clients, verifies
vermagic, every imported CRC, the exact base BTF and split-BTF parsing:

```sh
python3 bench/mmap_lock/prepare.py \
  --kernel-source "$KDLOCK_BUILD_DIR/linux" \
  --source-manifest /dev/shm/kdmm31-perf-prep-20261025-inputs/source-manifest.json \
  --output /root/kdlock-evidence/10.176.26.71/bench/mmap-kdmm31-prep-20261025/NEW-build
make -C tests/unit run PYTHON=python3 \
  PY_TESTS='bench/test_mmap_capture.py bench/test_mmap_paired.py'
```

The source manifest is `{ "commit": "...", "files": { "relative/path": "sha256", ... } }`
for the six payload/client source files, including `control.h`. Preparation retains it and
all copied bytes. Freeze the collector source after its focused tests; readiness
binds its Python/C/header/`.inc`/JSON inputs before any measurements.
The existing `/usr/bin/pahole` 1.25 parses both the base ELF and split module
BTF, exactly as in the preserved candidate installation check. Its hash and
command results belong in the preparation receipt. The guest's older system
libbpf failed parsing this base BTF; that failure remains retained. A privately
copied bpftool was preserved unused; no package/system installation or BPF load
occurred.

## Retained transport and historical execution interface

The following examples retain the historical 24-case defaults. For `plain-v1`,
select the plan at every ready step as above, use only cases 0/1 and report 12
receipts. The controller and finish transport are shared; old receipts are not
changed. These commands describe interfaces; run them only after the exact
cycle and root host capture are approved and no stop condition is active.
The October 25 admission failure does not authorize another attempt after
waiting for quiet. Set `KDLOCK_RECOVERY_CONFIRMED=1` and
`KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z` only after an actual
successful snapshot listing. Flags alone are not recovery proof.

On 380G10, the following captures one host state, using a new output directory:

```sh
python3 bench/mmap_lock/controller.py --output NEW-local-admission
```

The reviewed helper reads `/proc/257489/numa_maps`, process/thread identity,
affinity, CPU policy and `info snapshots`; root access is required for the denied
metadata read. It changes no settings or processes. Do not retry a denied access
with another privilege route without authorization. The controller uses host SSH
port 22 and `sudo -n` for that approved capture; guest commands use port 2222.
Copy `NEW-local-admission/host-endpoint.json` unchanged to the guest and use its
guest path as `--host-state`. Pass the original local file to `--admission`.
The capture expires after 300 seconds; each measured case needs fresh admission.

In the guest, use fresh evidence paths and the actual boot ID:

```sh
python3 bench/mmap_lock/paired.py ready --prepared BUILD/result.json \
  --native-api PRIOR/actual-native-1.json --kd-api PRIOR/actual-kd-1.json \
  --mode native --block 0 --boot-id ACTUAL-BOOT-ID \
  --host-state ADMISSION.json --output BOOT/ready
python3 bench/mmap_lock/paired.py validate \
  --ready BOOT/ready/result.json --output BOOT/validation
```

Run `ready` on each candidate boot with the table's mode/block. Run `validate`
only in blocks 0 and 1; both retained validation receipts are required for all
measurements. Cases 0–3 are 1/plain, 1/sampled, 16/plain and 16/sampled. For each measured case, the
source controller runs `paired.py run`, captures the endpoint immediately after
SSH returns, then fetches the result. It never unloads before the capture:

```sh
python3 bench/mmap_lock/controller.py --output NEW-local-case \
  --admission FRESH-LOCAL-ADMISSION.json \
  --receipt /root/kdlock-evidence/CASE/client-result.json \
  --remote-command 'cd /root/host_fs/kdlock && env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z /root/kdlock-translation-venv-20261019/bin/python3 bench/mmap_lock/paired.py run --ready BOOT/ready/result.json --native-validation NATIVE/validation/result.json --kd-validation KD/validation/result.json --repeat 0 --case 0 --host-state ADMISSION.json --output /root/kdlock-evidence/CASE'
```

The remote command carries the pinned Python and confirmed-recovery variables;
the local shell's exported values do not automatically cross SSH. After the
first case, add `--previous PRECEDING-CASE/result.json` to the inner `paired.py run`
command; it must be the
immediately preceding **qualified and drained** case in the fixed sequence.
Transfer the controller directory into the guest, retaining every partial file,
then finish independently of endpoint readability:

```sh
python3 bench/mmap_lock/paired.py finish --output /root/kdlock-evidence/CASE \
  --controller /root/kdlock-evidence/CASE/controller-capture
python3 bench/mmap_lock/report.py CASE-00/result.json CASE-01/result.json \
  OTHER-EXACT-22-RESULT-PATHS > NEW-summary.json
```

Paths in these examples are placeholders for the preserved build, same-boot
readiness and exact case directories. The tools bind absolute paths and hashes;
retain the full receipt/raw-evidence tree, including prior API checks, validation
inputs and controller partial files. Reporting replays saved qualification and
measurements and requires exactly 24 cases, their full specifications, four
measured boot blocks and chronological predecessor chain. The 14 focused
paired/report tests cover the latest replay and admission corrections; they do
not replace live validation of both modes.

`finish` rejects missing/malformed/mismatched endpoint evidence even if business
validation and normal drain succeed. The unchanged gate requires the exact
original 67 QEMU tasks/affinities, matching configuration and NUMA bindings;
additional start-time checks reject observed PID/TID reuse. Non-atomic captures
cannot prove absence of intervening thread lifetimes. Request latency from SSH
completion must remain under one second. Guest receipt writes precede that
completion; this is not an instantaneous worker-exit snapshot. Later quiet
captures cannot validate a failed immediate endpoint.

Archive raw cases, controller partial receipts, source/binary hashes and the
summary before recovery. Recheck recovery image/boot, original 73 modules,
known taint bits, idle state and empty `next_entry`. Preserving failures takes
precedence over completing the planned session count.
