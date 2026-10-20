# Seven-regression operation-latency diagnostic

Status: private caller preparation in progress. No latency measurement or performance acceptance
is claimed. The completed correctness, strict rwlock refusal diagnosis and
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
32,768 three-word samples per worker. Record ordinal, start and end in nanoseconds.
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
