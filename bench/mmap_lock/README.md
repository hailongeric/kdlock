# Built-in mmap lock performance

Current work is throughput only. The explicit
`plain-v1` plan selects **12 plain sessions**. It is prepared and mock-tested;
its authorized October 25 attempt [stopped before boot](../results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
at **68 QEMU tasks versus 67**. One full capture ran; all 12 measurements and
six unscored checks remain unrun. The historical 24-case plain/sampled plan
is `paired-v1`; omitted plan fields retain that historical meaning. Never obtain
a 12-case campaign by skipping sampled rows or relabelling old receipts.

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
The separate [QEMU diagnostic](DIAGNOSTIC.md) has passed 43 focused mocked tests;
its exact live cycle remains unapproved and cannot qualify a benchmark.

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

## Plain throughput plan

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
for the five unchanged payload/clients' source files. Preparation retains it and
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
