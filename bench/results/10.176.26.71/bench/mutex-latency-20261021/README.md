# Seven-regression operation-latency diagnostic

Status: `run-1` stopped on sample capacity; the separate revised `run-2` is active. No completed latency
result or performance acceptance is claimed. The completed correctness, strict rwlock refusal diagnosis and
earlier mutex results remain in the
[continuation record](../mutex-regression-diagnosis-20261020/README.md).
Only the main agent edits files or operates the VM; all three helpers finished
read-only review and report no files touched.

## Fixed comparison

Use the same recovery VM, boot
`b65f0205-c8f9-4385-8b13-039cbce243a6`, kernel
`6.1.159-kdclobber2` / Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, 64 vCPUs and original host
placement, frequency policy and NUMA configuration. Collector remains CPU 63;
workers remain `0..N-1`. Before live execution require the actual recorded
recovery snapshot and exact original 67-thread QEMU set. Preserve every failed
preflight and the immediate post-run comparison; no endpoint mismatch is waived.

The original immutable collection is
`/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2`:
collection `d21a1e3`, OUTER `752fec1`. Its input and retained-harness manifest
SHA-256 values remain respectively
`df8b56e19893cb2e42d92bad41de8876ff4b1b6a915b2fe67336ba761a99ea73`
and `8081cbed66833c59e0c58f0aa62d9f6ff87e8c28438ac7b1252584881879bf20`.
No candidate provider is substituted.

The fixed seven points are c08/3,4,5 workers; pipebytes/3,5;
pipecap/5; RCUHT/2. Each uses OUTER, public DIRECT, Native and TCLock, three
repetitions and three caller modes: original plain, instrumented with sampling
disabled, instrumented with sampling enabled. This is **252 serial sessions**.
Keep the original arm rotation; rotate mode order by repetition. Retain original
warmups, two-second measurements, 300 ms peak/settling windows, 10 ms progress
sampling, post64, API n16 objects and provider settings. No parallel tests,
favorable-class replacement repetitions or interrupted active calls are allowed.

## Metric and instrumentation

Synthetic observations surround the complete kernel body call through its
return, including lock, body, unlock and any delegation ACK, but excluding
post-work and RCUHT key generation. Pipe observations surround the userspace
query block through checked return, including the syscall. These are different
scopes and are never pooled. Neither is acquisition latency: delegated lock
calls can resume after the corresponding unlock.

Each physical worker chooses one pseudorandom position per 256 operations from
a deterministic independent seed. Storage is preallocated before timing, with
131,072 three-word samples per worker in the follow-up revision (32,768 in
`inputs-1` through `inputs-3`). Record ordinal, start and end in nanoseconds.
Retain raw observations, exact selected/completed counts and overflow counters.
Reject missing/duplicate ordinals, unexpected mode, overflow, unordered clocks,
out-of-worker intervals and changed identities. Publish nearest-rank p95 and
per-worker distributions; flag fewer than 1,000 samples in any worker as
insufficient. Do not estimate latency from throughput or subtract clock overhead.

Only private runner/client copies change. Original providers, API workload
modules, translators and collectors remain byte-identical. Synthetic modules
are rebuilt against matching export metadata in the VM; canonical body bytes
and relocation targets must match the original ELF for every measured backend.
Export-metadata builds are never loaded. Both instrumented modes use the same
binary. Compare disabled/plain and sampled/disabled throughput, returned JIT
counts and execution classes to expose observer effects. A class shift prevents
a same-class latency comparison; all raw results and variance remain visible.

## Required evidence

Before timing: basic plus directly affected VM tests, all caller builds, exact
source transformations, body/relocation audits, frozen input hashes and a fresh
host/snapshot gate. After timing: worker/business oracles, returned JIT evidence,
exact KD source retirement, final idle, kernel logs and immediate host receipt.
Archive complete inputs and session observations, independently verify hashes
and arithmetic, and report each repetition and within-group range/CV.

This diagnostic does not resolve the seven causes by itself. Whole-kernel
replacement, the two remaining execution-class gaps, historic QEMU interference,
shared-lock parity and real mmap/fault integration retain their documented
limits. Acceptance remains open until addressed or explicitly reported unresolved.

## Preparation record

`checks-1`, source `f365e95`, passed dependency validation, both basic programs
and all seven affected latency tests in the original VM, with final idle.
`inputs-1` then stopped before any caller build or live measurement because the
preparer incorrectly assumed a non-MODVERSIONS kernel. The real kernel has
`CONFIG_MODVERSIONS=y`. Preserve that failed tree and `prepare-1.log`.
The correction compares each rebuilt export-metadata CRC with the corresponding
word in the original module's `__kcrctab` section; no original backend is
replaced and no version check is omitted. A new input run will retain its own
identity and validation results.

`checks-2`, source `457ad4c`, passed both basic programs and all eight affected
tests. `inputs-2` completed all caller builds, all three original/export CRC
comparisons and all eight synthetic body/relocation comparisons. Static review
then found that relocating the retained scheduler changes its inferred checkout
root. The driver now explicitly restores the original checkout path for the
collector-origin guard. Recreate inputs with that reviewed driver before timing;
`inputs-2` has no measured sessions and remains separate.

`checks-3` and `inputs-3`, source `0cc479b`, passed the two basic programs,
eight latency tests, 13 original-input/provenance tests, all builds, all three
CRC comparisons and all eight body/relocation comparisons. The final manifest
SHA-256 is `9a6ef21ced0af3171ed7a990ba0acdaffa4bcf4274a32b1dcf87b69d20cf702c`.
The first two host preflights failed with 80 and 68 threads at
20:01:33.865361 and 20:02:27.501002 UTC on 2026-10-20. They started zero sessions.
After natural retirement, the fresh 20:05:13.157212 UTC receipt passed with the
exact original 67-thread set, snapshot and placement. `run-1` then began;
no threshold or host configuration changed.

`run-1` completed eight plain/disabled sessions, then stopped on
`c08-t03-r0-tclock-sampled`. Its ninth timed body measurement completed correctly
with 12,926,464 total operations; worker 2 completed 9,059,840, requiring 35,390
samples at the fixed rate, beyond the 32,768 capacity. The strict reader rejected
chunk metadata/overflow and the original collector labelled the session
`PREPARATION_FAILED`; cleanup drained normally and the VM was independently
confirmed idle. This is a failed diagnostic, not a pass. The first reader did
not retain rejected chunk bytes or the already-read worker samples; that evidence
gap is explicit. All four earlier KD sessions retain exact retirement.

The immediate host receipt at 20:06:11.056569 UTC also fails with 82 threads.
The follow-up increases only preallocated diagnostic capacity to 131,072
(about 192 MiB for 64 slots) and retains rejected chunk bytes on future failure.
Sampling rate, clocks, body identity, original ownership/admission checks and
overflow refusal remain unchanged. Rebuild and revalidate into new inputs, then
run a separately identified full fixed plan. Do not pool `run-1` with its revision.

`checks-4` / `inputs-4`, source `39b9333`, passed the two basic programs and
all nine affected latency tests, caller builds, original CRC checks and eight
body comparisons. The new input manifest is
`5c83db1396330baef1f1ffa553d5bbb1e22e72afd2b94f5e93f87de4a22a6137`.
Host preflight 4 failed with 131 threads at 20:12:53.564271 UTC. After natural
retirement, preflight 5 passed at 20:14:16.584659 UTC with the exact 67-thread
set and snapshot. `run-2` then began the full separate 252-session plan. The
first eight sampled sessions passed sampling/count/clock checks and the
per-worker 1,000-sample sufficiency rule. Final results and archive review remain
pending.
