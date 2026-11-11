# Kernel8 affected builds and basic checks

All five affected modules compiled and signed for `7.0.0-38-kdrebuild8`.
Both runner syntax checks passed. A separate checks-only continuation passed
all eight source-boundary checks and five linked GS checks, with no skips.
No module, selected gate or generated MM body ran in these receipts.
[Saved-file audit](audit.json), [linked kernel build](../kernel8-build-20261111/README.md)

The frozen module/host source is `140aecc4f83a6b6ae6f20245234e8a63504f9210`.
All 78 core files match linked core `0d42063e`, Build ID
`a33dd4d11d0f0c6649107507e685b6e86e716c1a`. Compilation used ordinary
external Kbuild with separate M/MO outputs. Five unsigned modules and their
five signed copies are retained: native rwsem APIs, MM provider, managed
killable, private rwsem/query and private mutex fixtures. All metadata readers
returned zero and report candidate8 vermagic and the same sha512 signing key.
[Original result](collection/payload/attempt01/receipts/result.json),
[binaries](collection/payload/binaries)

The original attempt remains failed. Its first 36 commands returned zero:
35 module build/sign/metadata commands and one two-runner AST command.
Command 37 ran eight boundary tests: seven passed and the query case failed
when constructing RuntimeExit with IntEnum values instead of exact integer
wire scalars. No linked GS check ran in that attempt.
[Failure log](collection/payload/attempt01/receipts/source-boundary-eight.log)

Commit `4cc53e09594efbdf9388488bde4fc507717cb260` changes only the two test
arguments to explicit integers. Production validation remains strict.
The continuation uses the unchanged compiler snapshot and that standalone
corrected test. Its two commands returned zero: boundary8 and linked-GS5.
It repeats no module build, signing, AST check or syscall baseline. Original
inputs and failed receipts remain unchanged.
[Corrected source](collection/payload/checks-input/test_source_boundaries.py),
[continuation](collection/payload/checks/result.json),
[GS target](collection/payload/checks/gs-target.json)

The userspace client is byte-exact reuse of SHA256
`bae90760f57f3930e1ff48443140eb096ea316c1fed00ae1840127f6985a4cd2`.
The helper verifies its C, ABI and include bytes against the original compiled
manifest before comparing the new snapshot. The retained unselected 2x8
baseline is the earlier normal-kernel result, not a new candidate8 run.
[Prior client/baseline provenance](../kernel7-affected-build-20261111/README.md),
[explicit reuse record](collection/payload/attempt01/receipts/result.json)

Four compiler warnings remain in the raw logs: MM frame 1912 bytes, private
rwsem frame 4352 bytes and missing checkpoint prototype, private mutex frame
2264 bytes. Compilation does not establish general stack or context coverage.
The GS tests decode and lower the actual linked candidate8 witness and derived
byte cases; they execute no generated machine code and supply no running-image
proof. [Warning rows](audit.json), [actual GS results](collection/payload/checks/linked-gs-five.log)

The VM stayed on normal `7.0.0-38-kdlock1`, boot
`afb0c5cd-96b7-488b-bcb4-4a31cbb4e50e`, taint 0. All sixteen kernel outputs,
core/native source, prior kernel/source and installed-file maps retained their
pins. The final strict activity and D-state lists were empty.
[Final checks and identity](collection/payload/checks/result.json)

The collection contains 216 guest payload files with 10,061,323 bytes.
All original collection metadata, before/copy/after inventories and raw transport
archive are retained. The offline standard-library audit verifies those saved
bytes, all 39 command logs, module/client hashes, both 140-member manifests and
the exact two-scalar correction. It is an archival check, not another test run.
[Copy index](collection/copy-index.json), [collection closure](collection/collection.json),
[audit source](audit.py), [checksums](SHA256SUMS)
