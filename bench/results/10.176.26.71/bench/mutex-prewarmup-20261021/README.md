# Pre-warmup quiescence control, 2026-10-21

Status: focused validation passed; live diagnostic pending. No timing permitted.
The source checkout started clean at `e477c86`. The same VM is drained on boot
`88449cfc-cea9-4647-a294-bc601e372146`, kernel `6.1.159-kdclobber2`, with the
original 73 modules. Only the main agent edits files or executes VM checks.
Helpers review read-only and report no files touched. A read-only preflight
initially used the wrong runtime import directory and failed before inspection;
the corrected import completed the existing idle and exact-module checks.

This separate diagnostic retains the prepared client, provider, source and host
observer connections. After original check-before and translator shutdown, wait
for the unchanged full host gate and fresh guest comparison **before** releasing
one original warmup. The exact original 67 TIDs/names/affinities remain required.
Accounting scans only select capture opportunities; the existing bounded
sample-trigger policy, freshness checks, maximum four candidate captures and
120-second terminal capture remain unchanged.

After the one original warmup reply, take the required exact drained-state
snapshot and request **one immediate full post-warmup capture**. Do not wait for
another quiet sample, add a cooldown, retry a refusal or send a measurement
command. Use distinct ordered stages and fresh nonces. Check loaded placement
before warmup. Compare physical/publication state and exact counters within each
hold; across warmup permit only its exact operation and matched returned-body
counter deltas. A fully observed pre-gate refusal skips warmup and retires
normally. Coordination or lifetime uncertainty retains resources.

Record snapshot start/end, pre-capture, guest revalidation, warmup command/reply,
immediate post-request/capture, validation, cleanup and endpoint chronology.
The frozen reply reader writes `warmup.json` before returning. State snapshots,
fresh validation, control messages and guest background I/O can also cause host
activity. The pre-gate receipt stays in guest memory until the post observation;
the source supervisor retains it independently. No phase-end acknowledgement or
ordinary preparation save precedes the post request. The reused warmup-begin
host marker is only a causal lower bound, never a simultaneous clock reading.
Report actual delays/observer overhead, non-atomic reads, missed worker lifetimes
and departed accounting tails without attributing all activity to warmup.

Frozen provider, workload, client, translator and old evidence stay unchanged.
The [fixed-capture refusals](../mutex-boundary-20261021/README.md) and the
[triggered pass with failed 70-task endpoint](../mutex-boundary-trigger-20261021/README.md)
remain separate. Waiting changes admission clock history; it does not reset
heat or establish original preparation parity. All seven regression causes and
acquisition latency remain unresolved. Complete-operation p95 is separate.
Readers stay local/concurrent; mmap and page-fault tasks remain separate;
unsupported TCLock critical sections remain excluded.

## Focused validation

Implementation `7682076` synchronized while idle and verified all 3,975 tracked
file hashes. Guest `checks-1` passed serially: two rebuilt basic programs,
nine trigger tests, four reply-protocol tests, twelve pre-warmup ordering and
failure-path tests, and six unchanged recovery-gate tests. Tests ran from 104
frozen committed source files; current and retained hashes matched afterward
and final idle passed. The new integration tests exercise the actual runner
methods with a fake client, including safe pre-refusal, malformed replies,
invalid joined work, wrong placement and immediate post-capture ordering.

Read-only review caught and corrected unsafe handling of malformed warmup
replies before this test run. Such replies now retain resources as `UNDRAINED`;
they cannot cause ordinary unbind/unload. Original-reply and in-memory-validation
timestamps are recorded separately. The `client-warmup` phase marker brackets
the pre-wait plus warmup; actual command timestamps define the work interval.
