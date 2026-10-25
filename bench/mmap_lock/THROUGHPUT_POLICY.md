# Throughput eligibility and writer observation

**Implemented; the authorized continuation stopped during KD validation.**
The explicit `mmap-functional-v1` policy separates functional completion from
the sleeping-writer observation. Missing selection retains `mmap-writer-proof-v1`
strict behavior. [Focused validation](../results/10.176.26.71/tests/mmap-functional-eligibility-20261026/README.md)
records 99 Python test passes, two basic programs, fixed-client compilation and
replay of the saved Native controls. These are not new actual-mmap runtime tests.
The sweep closed at `b8d9137` remains failed under its original policy, with
**0/126 measured cases**. Its failed KD observation, completed Native controls
and the separate accepted small pair retain their original outcomes.

The [subsequent live continuation](../results/10.176.26.71/bench/mmap-functional-scaling-20261026/README.md)
completed 80,000 KD cycles with `writer_observation=inconclusive`, then passed
15 unscored controls through 36 workers. The 40-worker control failed the
unchanged positive full-cohort peak-window requirement. All 126 measurements
remain unrun. Drain was verified separately and recovery restored 73 modules,
zero taint and no pending boot. This guide authorizes no restart or acceptance
change; review the retained progress samples before proposing another cycle.

## Decision and source evidence

Make the sleeping-writer snapshot a separate integration observation under an
explicit prospective eligibility policy. It is not intrinsic to completed
syscall throughput. Apply the same functional requirements and observation
rules to Native and KD; retain strict correctness-mode behavior and verification
of every claimed positive proof.

[`client.c::writer_contention`](../mmap_writer/client.c) requires exact
ELF-derived return offsets, state `D` before and after, matching expected wait
channels and unchanged nonempty `schedstat`. Sampling continues until a proof
is found or all workers finish. Only raw logging is capped at four rows per
worker. Both backends face that logical bracket, but their different wait paths
make observation sensitivity backend-dependent. Failure to capture the bracket
does not demonstrate an ownership defect or prove the absence of contention.

The independent review agrees with this source assessment at `4b76cad`;
reviewed client SHA-256:
`0685b4f79a0cf178af2807593b69903fe169d7a8845cc9785df77139452bad07`.

| Evidence | Requirement retained for both backends |
| --- | --- |
| Backend | `paired.py::check_kernel/ready`: exact image, Build ID, configuration, boot arguments, module set, source/artifact hashes and prior API receipts. The adapter initializes an immutable backend per mm. `MW_ID` gives addresses and task/object identities, not a backend flag. |
| Prior ownership/API checks | Preserve the 137 Native / 161 KD prerequisites. The explicit probe in `tests/kernel/mmap_lock/payload/module.c` checks writer ownership and overlapping reader/writer counters. These are focused prior evidence, not a fresh proof of every timed acquisition or full Native equivalence. |
| Functional work | Successful mmap/munmap calls; exact worker mm/lock/object/TGID identities, unique TIDs and CPU placement; successful joins; positive per-worker completion; exact operation and callback totals; zero worker/context/fault errors. |
| Lifetime | Native VFS/VMA references and `mmgrab/mmdrop` retain ownership of storage. Preserve zero residual files/mm references/VMAs, exact destruction and release-error counters, fault checks, normal unload and idle verification. Counters do not replace references or lock ownership. |
| Timing | Keep `mmap-window-v2`, `qemu-workers-v1`, settling, workload/instrumentation identity, progress accounting, endpoint ordering, drain and replay. Timed runs require `observe=0`, including zero contention-counter activity. |
| Observation | Preserve `mapping.py::chain_proof` and its corruption checks for positive proofs. A queue-presence count is neither a sleeping-writer proof nor comparable lock latency. |

The candidate config SHA-256 is
`67d4c96cfd29f657d642c5ffe969a9215892c0209125dfe83f283873b366ae01`.
`CONFIG_DEBUG_VM` and `CONFIG_PROVE_LOCKING` are disabled:
`mmap_assert_write_locked()` in the mapping callback is **not a live ownership
assertion**. Bound image/config/boot selection, unchanged integration and the
prior explicit API probes provide separate evidence. Addresses and queue
counters alone cannot establish all lock semantics.

## Eligibility contract

Select `--eligibility-policy mmap-functional-v1` at `paired.py ready`, alongside
`--plan plain-scaling-v1 --measurement-policy mmap-window-v2`. The preparation
receipt must bind a fixed client built for that policy. Later actions inherit
the selection. Client completion, fixed validation, readiness, run receipts,
replay and reporting carry it; mixed, missing or unknown versions fail. Historical
receipts without the field keep strict behavior, and `screen` remains strict.

Record functional completion separately from
`writer_observation=observed|inconclusive`. Under the new policy only, normal
functional completion with no captured bracket may report `inconclusive` and
exit successfully; runner eligibility still requires all remaining checks and
drain. Strict correctness mode continues to fail on the missing proof. An
`observed` result must pass the existing complete verifier. Malformed positive
proofs, read/command errors, failed syscalls, incomplete joins, timeouts and
uncertain drain remain failures, never `inconclusive`. Do not catch arbitrary
nonzero exits or reinterpret the stopped KD client's exit 1 as success.

The change belongs in userspace completion/validation/reporting, with kernel,
payload, MM algorithms and timed workload unchanged. Additional rejection
diagnostics are unnecessary to justify the separation; they could only identify
which bracket predicate rejected a sample. No such diagnostic is proposed here.

## Reuse the completed Native controls

Reuse must be an explicit compatibility import, not a replacement old receipt.
The original guest receipt is
`/root/kdlock-evidence/10.176.26.71/bench/mmap-worker-scaling-20261026/native-validation/result.json`,
SHA-256 `b6294fdebad0ab45d7715204cc2f8687470d879771e2cee563ba88a681d39da6`.

1. Verify that receipt and every bound readiness, preparation, prior API and
   raw fixed/timed record against retained bytes. Replay its original strict
   fixed proof and all 21 controls with their original semantics. Require
   passed/drained validation, the exact ordered worker grid, callback/lifetime
   checks and the same saved per-case measurements. It remains unscored.
2. Compare the proposed target's kernel image/Build ID/configuration, backend,
   payload and timed-client binaries, syscall workload, CPU/NUMA placement,
   timing parameters and instrumentation against those originals. Preserve the
   original fixed-client hash and positive-proof evidence. Any changed fixed
   completion schema or validator/report tooling must have an explicit reviewed
   compatibility rule binding old/new source hashes; equality must not be
   fabricated by overwriting a hash. Workload or correctness changes are not
   covered by a reporting-policy-only compatibility rule.
3. Write a **new** compatibility receipt binding the original receipt/raw hashes,
   target policy and artifacts, importer/version hashes and each compatibility
   verdict. Preserve original boot IDs, timestamps, source hashes and outcomes.
   Do not mark the historical controls as new-policy executions or measurements.
4. Require future readiness, run and report replay to verify that compatibility
   receipt and its dependencies. Fresh same-boot readiness, host admission and
   measurement endpoints remain mandatory. An old control receipt cannot supply
   a new boot's live health or an endpoint.
5. Missing evidence or an unreviewed difference rejects reuse; it does not
   automatically schedule replacement controls. With successful verification,
   reuse all 21 Native controls without executing them again. KD's 21 controls
   remain unrun, and its old failed fixed proof remains failed. Any later live
   plan must account for the remaining work and obtain its own bounded approval.

[`reuse.py`](reuse.py) implements this import only for the pinned successful
Native receipt. [`reuse_native_v1.json`](reuse_native_v1.json) binds 137 original
control sources, 140 original source inputs and eight exact target source hashes.
It is not a general importer for arbitrary receipts or changed workloads.
Both the retained importer/rules and executing code must match by hash; identical
code may move from the private snapshot to the maintained checkout without
rewriting its provenance. New code differences require a reviewed compatibility
rule. Fresh compatible readiness on a different boot remains mandatory at run
and report replay; the old receipt supplies neither admission nor endpoints.

## Offline preparation and a bounded future continuation

Keep the original sources in a separate, hash-verified `PRIOR-SOURCE` directory.
The fixed-only build remaps historical source dependencies there, leaving the
old receipts and frozen builds unchanged. In the idle recovery VM, with the
pinned Python and a reviewed source snapshot, the interfaces are:

```sh
/root/kdlock-translation-venv-20261019/bin/python3 SOURCE/bench/mmap_lock/prepare.py \
  --reuse-payload ORIGINAL-BUILD/result.json --fixed-client-only \
  --prior-source PRIOR-SOURCE --source-manifest SOURCE-MANIFEST.json \
  --output NEW-FIXED-BUILD
/root/kdlock-translation-venv-20261019/bin/python3 SOURCE/bench/mmap_lock/reuse.py \
  --original ORIGINAL-NATIVE-VALIDATION/result.json \
  --prepared NEW-FIXED-BUILD/result.json --prior-source PRIOR-SOURCE \
  --output NEW-NATIVE-COMPATIBILITY.json
```

Use new output paths. No command above loads a module, changes a kernel or
reboots. The fixed client is the only compiled binary; payload and timed client
are reused exactly. The validation receipt gives the completed build/import
paths, hashes and runnable saved-evidence replay command, so repeating that
preparation is unnecessary for unchanged inputs.

After independent review and separate approval of the exact live cycle, select
the same policy at **every** fresh readiness. Start with KD block 1, using the
verified Native compatibility receipt as `--native-validation`. Run one new KD
fixed check and all 21 KD timed controls under the new policy; use that result as
`--kd-validation`. Continue the existing block order 1, 2, 3, 4, then recovery.
The 126 measurements, per-case workload, three paired repetitions, placement,
90-second settling interval, window observers and endpoints are unchanged.
Do not rerun the Native controls or the small screen. The old failed KD proof
remains failed even if a future fixed check returns `inconclusive`.

The following bounds describe that stopped continuation's original authorization,
not remaining permission to relaunch it. It consumed 17 payload cycles, two
boots and three full captures; the result receipt reconciles partial validation.

| Original continuation maximum, conditional on approved reuse | Bound |
| --- | ---: |
| New fixed check / unscored timed controls | 1 KD / 21 KD |
| Measured cases / payload cycles | 126 / 148 |
| Boots including recovery | 5: KD, Native, KD, Native, recovery |
| Full host captures | 384: initial + 4 readiness + 3 × 126 + recovery |
| Window observers / scans | 126 / at most 12,222 |
| Timed setup waits | 147 × 90 s = 13,230 s |
| Kernel-log captures | 573 |

Using the existing [planning assumptions](README.md#plain-throughput-plan),
estimated remaining time is **16,099.7 seconds (4 h 28 min 19.7 s)**: 294 seconds
of timed targets, 14.7 seconds of scheduled starts, 13,230 seconds of setup waits,
30 seconds for the fixed check, 735 seconds of timed-case overhead, 768 seconds
of captures, 600 seconds for boots, 50 seconds of readiness/recovery checks,
252 seconds of minimum guards and 126 seconds of report replay. These are not
measured costs or hard completion limits.

One new retained copy is estimated at **1,101.25 MiB**; raw plus archive and 25%
headroom is **2,753.125 MiB**, rounded to **3 GiB per retention filesystem**.
Retain the existing control evidence and snapshots in addition to that reserve.
Check actual free space and log growth before live approval; no cleanup is
implied. Stop on the first identity, functional, command, admission, endpoint or
drain failure. A timeout does not prove drain; recovery is permitted only after
proven drain under the separately approved recovery plan. This document starts
no live action.

The resulting claim would be aggregate throughput for the unchanged untouched
4 KiB shared-mm mmap/munmap workload. It would not establish a sleeping wait in
every run, fairness, isolated lock latency, reader scaling, page-fault throughput,
delegation, TCLock equivalence or full Native semantics.

Sources: [fixed client](../mmap_writer/client.c),
[paired runner](paired.py), [timed validation](../mmap_writer/timing.py),
[positive-proof verifier](../../tests/kernel/mmap_lock/mapping.py),
[explicit API probe](../../tests/kernel/mmap_lock/payload/module.c),
[ELF-bound writer sites](../../tests/kernel/mmap_lock/writer_sites_kdmm31.json),
[payload lifetime/accounting](../../workload_modules/mmap_writer/mapping.c),
[backend adapter](../../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c).
