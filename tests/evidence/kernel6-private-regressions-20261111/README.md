# Kernel6 private rwsem and mutex regressions

Both private runtime controllers and runners returned 0 on the exact kernel6
image, after the [native API and real syscall checks](../kernel6-native-api-mm-20261111/README.md).
The guest later [returned to the normal kernel](../kernel6-boot-20261111/README.md).
These are bounded generated-episode mechanisms, separate from real MM syscalls.

Fixture source is `80c272e5`, core `532b68a6`, package `3512f5dd` with all 77
kernel files matched. The frozen snapshot contains 117 files, including both
private `.inc` files and the original compiler/backend. Both runs used boot
`4400eea1-c8fc-40e1-b6b7-f7a99ecc1364`, release `7.0.0-38-kdrebuild6`, Build ID
`5ed6cd8cffed6960ce901261dfab3bb019a0442d` and configuration SHA
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
Exact preparation, command, source, module, postboot and predecessor pins remain
in the saved records and [copy index](copy-index.json).

The [two-module build](collection/payload/module-build/result.json) returned 0.
Actual warnings remain in its logs: rwsem missing prototype and a 4,352-byte
frame exceeding 1,024 bytes, plus a 2,264-byte mutex frame warning. These are
successful builds with retained warnings, not general stack coverage.
The [GS check](collection/payload/gs5/result.json) passed all five existing
actual-target cases without skips. It reads and lowers kernel6 instruction
bytes through the original backend; it does not execute generated code.

Each private family used four workers and eight iterations, a 600-second runner
deadline and 660-second outer bound. Source, image, event and wire capacities
were explicit. No compiler/backend change, replay or repeated live run occurred.

| Actual result | Private rwsem | Private mutex |
| --- | --- | --- |
| Runner verdict | protected_rwsem_jit_reader_mechanism_pass | protected_jit_recursive_mechanism_pass |
| Scalar events / overflow | 7,147 / 0 | 4,691 / 0 |
| Publications / ACKs | 13 / 14 | 4 / 8 |
| Wire exchanges, all status 0 | 90 | 32 |
| Shutdown settlements | 4 | 0 |

The [rwsem result](collection/payload/rwsem/result.json) verifies native reader
credits, exclusion, real downgrade, repeated read identities, fixed-image nested
read/write execution, shared-B return and retained-writer downgrade handback.
Its deliberate native miss retains the physical write grant until the matching
read release. The warm baseline contains two existing facts and stays unchanged;
it is not an empty claim. Four deliberate misses are archived and settled at
shutdown. Sixteen coordinator cycles include refused/empty learning outcomes;
thirteen actual candidates were published.

The [mutex result](collection/payload/mutex/result.json) verifies native/fork
checks, fixed-image plain execution and both recursive CA -> CB -> CA scenes.
One canonical state retains distinct acquisition identities, exact current-state
return endpoints, responsible physical release and final retirement. The second
scene includes exact return/notifier closure. Five coordinator cycles include
the final empty claim; four actual images were published. Warm/pending claims
finish empty, with no shutdown settlement required.

The [independent full raw audit](audit/full-raw-audit.json), SHA
`e8d2d025947c4c16fb08113086278e4160784a11455a69d232ab66296bb12b69`,
checks all 900 original files, both binary observation buffers against JSON,
455 embedded proof rows, 24 exact read-credit lifetimes, recursive release and
retirement joins, all 122 wire exchanges, generated code against actual ELF
text/source bytes, publication/eligible ACK bindings and durable archive/END
closure. It processes saved data only. All 17 GNU image objects are retained.

Both fixtures completed ordinary destroy/unload with no remaining controls or
workers and only the NLS module loaded. The signed native predecessor had taint
4,096; the unsigned private modules produced the expected final taint 12,288.
The original task's unprotected C epilogue remains native. Full generated C-function
return, general progress/same-object reacquisition, broader context/mitigation,
auxiliary-stack unwinding, full T01-T56 acceptance and performance are outside
these checks. No MM JIT result follows from them.

The complete original transport, source-host records, preparation and independent
audits are retained. The five [module/client binaries](module-artifacts/)
match their actual build hashes; their original collection metadata is included.
The binary-appendix metadata precheck stopped before writes on a mislabeled
inventory hash, then used the verified copy-index hash; this is retained in
[preservation.json](preservation.json), not reported as a runtime failure.
Every stored member is covered by [SHA256SUMS](SHA256SUMS).
