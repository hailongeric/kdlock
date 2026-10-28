# KD delegation limits: 1024 total and local

The October 28 user-selected KD mutex policy sets both the total cap and NUMA
boundary to 1024. KD spin already had a 1024 total cap; its separate 128-body
cutoff for retrying empty successor links with deferred remote work is removed.
The eight-retry bound, total cap, terminal/native exits, deferred-first handoff
and ownership/retirement rules remain. Native and TCLock are unchanged.

Validation ran only in the designated VM on `7.0.0-38-kdlock1`, boot
`15dc5977-59d3-4471-a196-d71f03f450ed`. Recovery snapshot
`linux70-kdlock1-clean-20261027` was verified through the host monitor. No guest
kernel was modified, built, installed or rebooted.

## Checks

Basic C checks and six affected unit drivers passed: mutex policy and terminal,
spin batch, shadow and outer progress, and nano profiling. The final mutex policy
fixture additionally checks deferred prefixes of one, seven and eight requests
when the boundary equals or exceeds the total cap, preserving exact order,
completion, wake and rejoin obligations. Explicit older 256/768 policies remain
covered. The default 1024/1024 fixture passed 23,620 checks.

The affected nano runner tests passed 12 cases; direct runner tests passed 60.
All four maintained live basic presets passed with sixteen workers and
1,600,000 operations each, correct data and normal drain:

| Family | JIT entries = completions |
| --- | ---: |
| Spin c01 | 1,595,794 |
| Public mutex c01 | 1,588,186 |
| Rwlock c01, 20% writes | 26,695 |
| Rwsem c16, 100% writes | 1,580,391 |

Every session records the provider mutex policy as 1024/1024. The basic runner
verified the running schema-2 kernel identity and fresh host placement/frequency
and snapshot state. Final guest idle was independently checked before archiving.
These are functional checks, not throughput or latency evidence. Live basic uses
one NUMA node; deferred remote order is covered by production-code unit fixtures,
not a new cross-NUMA performance campaign.

## Preserved admission attempts and evidence

The first live launch stopped before loading modules because the outer log under
`/root` triggered the writable-evidence guard. A second launch stopped before
module work because transient QEMU workers on CPU63 exited between reference and
current host captures. Both failures are retained. The successful launch used
an outer log under `/tmp` and a fresh verified host capture selected as both the
explicit hash-bound reference and current state. No admission guard was changed.

[evidence.json](evidence.json) records source hashes, session receipt hashes,
exact completion counts and the complete archive manifests. Retained raw archives
are under [raw/tests/kd-batch1024-20261028](../../raw/tests/kd-batch1024-20261028/).
The source-host offline check verified both archive sizes/SHA256 values, health,
basic result and all four session receipt hashes. Historical performance results
retain their original policy and do not establish a gain for this change.
