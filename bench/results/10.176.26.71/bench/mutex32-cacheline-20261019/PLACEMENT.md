# Placement-only diagnostic method

Commit `09ebd8f` adds a separate workload placement diagnostic. Its provider
bytes are identical to baseline `0987358`; the ordinary private lock declaration
is unchanged when no placement option is supplied. This document defines the
method; command receipts and result JSON establish whether execution passed.

The previous private workload object began at offset 32 in its actual 64-byte
line. Owner +0, gate +24 and tail +28 therefore shared that line. The runner's
`--mutex-lock-offset {0,32,40,56}` compiles the same 32-byte, naturally
8-byte-aligned type into dedicated 128-byte storage aligned to 64 bytes:

| Object offset | Owner line/offset | Gate line/offset | Tail line/offset |
| ---: | --- | --- | --- |
| 0 | 0 / 0 | 0 / 24 | 0 / 28 |
| 32 | 0 / 32 | 0 / 56 | 0 / 60 |
| 40 | 0 / 40 | 1 / 0 | 1 / 4 |
| 56 | 0 / 56 | 1 / 16 | 1 / 20 |

The planned round uses offsets 32 then 40. Offset 40 separates the owner's
modifications from gate/tail modification and polling while preserving field
offsets and public alignment. It also changes physical wait-field placement
relative to the gate. A throughput difference demonstrates placement
sensitivity, not a pure count of cache transfers or a causal fraction of the
old256 gap. The dedicated padding also differs from the standard workload's
neighboring data, so this pair remains a separate diagnostic cohort.

`RB_MUTEX_LOCK_OFFSET` selects the build option. Static assertions check the
public size/alignment and private storage geometry. Module metadata records
the compiled offset; the runner checks it and rejects mismatched reused builds.
Each loaded session also checks `lock_addr % 64` against the requested offset
and records the actual address and storage geometry. The two offsets use one
immutable source revision with separate compile options and ELF hashes.
The old256 object does not fit this diagnostic wrapper and is not supported.

`run-placement.py --commit 09ebd8f --base RUN` requires the completed
`packed32` baseline. It compares all current production-provider paths/hashes
with that baseline, retains full input hashes and verifies unchanged sources
before and after each command. Each offset runs the same pipebytes/query,
16-entry, 8/60-worker, three-repeat, 2000 ms settings as the main run. The
script requires successful placement, measured body-entry/return equality,
returned JIT, source retirement and drain for every session. Both runner test
programs execute first with their own command receipts.

Every placement record is `diagnostic=true`, and ordinary report tools exclude
it from timing medians and reject pooling with other offsets. The main summary
also explicitly rejects a non-null placement option. Preserve all twelve
diagnostic sessions under their own `placement` archive group and use
`--extra-source placement=09ebd8f` in the independent source audit.

No diagnostic source is edited in a running guest or existing frozen snapshot.
Source edits happen on 380G10, source transitions only after drain, and all
builds/timing happen in the VM. If either arm fails to drain, retain its evidence
and diagnose rather than proceeding to the next placement.
