# Recursive fixture: offline module build

The frozen fixture at `69ba6b030c1eb7e5f1c3f9461b70f5fef6791309`
passed its VM-only runner syntax check and external module build against
`7.0.0-38-kdrebuild3`. The build returned 0 in 2.502383818 seconds. This receipt
establishes compilation and linked module identity; it contains no module load,
generated-code execution, protected-episode completion or recursive delegation
result. The prepared live controller has only passed an AST check.

The fixture adds a finite scalar trace collector and five ordinary task roles
for a later fixed-image completion check. Its assertions require exact protected
root/child completion and return bindings, plus physical release and final slot
retirement observations. Those assertions have not run in this receipt. Full C
function epilogues remain outside the protected-episode completion scope.

## Inputs and actual commands

The guest leaf was
`/mnt/kdlock-builds/kdlock-main-work/module4-69ba6b03-01a1bc4f`.
[The preparation receipt](guest/receipts/preparation.json) records the original
copy/extraction, all 109 source files before and after runner AST, and all 66
kernel package inputs. The source archive was 1,382,400 bytes, SHA-256
`75c45d74697862b9d4fe527b1be7f41d0a9a7a5f679f28b9c4217ef904a47e57`;
[the source state](guest/kdlock-main-69ba6b03-state.json),
[full manifest](guest/kdlock-main-69ba6b03-manifest.json) and
[three fixture inputs](guest/kdlock-main-69ba6b03-fixture-inputs.json) retain
its exact scope, including the private `.inc` file.

The fixture source commit is `69ba6b03`; the core tracepoint/event commit is
`1b50e37382d2c739b16953027c47d7e2388562f0`. The build used the existing separate
candidate source/output trees under
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`.
The [66-input overlay](guest/kdlock-main-69ba6b03-build-inputs.json) records the
base and exact changed paths. The [six output pins](guest/kernel3-six-pins.json)
were derived from the completed kernel-3 linked identity, including actual ELF
SHA-256 `c099d66949ba99bc0ec200ef1570cc2917e7b8a3eb0acdd97811333247d2a43d`.

The [reviewed helper](guest/module4-build.py), SHA-256
`778207b4ec618e10b63f553c58fdfebec35ea2696f50a4c24ff12a191a00435d`,
performed AST and then the exact command in
[command.json](guest/build-receipts/command.json):

```text
make -C <candidate>/source O=<candidate>/build \
 M=<leaf>/input/tests/kernel/payload MO=<leaf>/module-build \
 KERNELRELEASE=7.0.0-38-kdrebuild3 -j8 V=1 modules
```

The observer bound was 180 seconds, and the caller selected a 1,073,741,824-byte
free-space floor on the module output filesystem. No compiler, assembler or
linker environment overrides were supplied. The explicit release selects the
offline candidate output while the VM runs the normal kernel; no candidate
module was loaded for compilation.

## Returned build and limits

[The raw result](guest/build-receipts/result.json) records actual return code 0,
unchanged 109 source files, unchanged 66 package inputs and the same six linked
kernel output hashes after the build. The normal boot stayed
`ca0b717b-c19d-4027-b598-6a1cf58b93d2`, release
`7.0.0-38-kdlock1`, with taint 0 before and after. The
[idle readback](guest/build-receipts/idle-after.json) found no compiler/build or
fixture runner, no loaded fixture module and no fixture devices.

The actual module is 580,336 bytes, SHA-256
`2be5cd04f9b7e5aa570c56dd1e940619e03696b33ef8d14bbc4262d2ac11a2a3`;
[modinfo](guest/build-receipts/modinfo.txt) records kernel-3 vermagic, and
[symbols.txt](guest/build-receipts/symbols.txt) retains the actual linked symbol
readback. The module binary stays at the recorded guest output path.

[The complete build log](guest/build-receipts/build.log), SHA-256
`64c29a6e03bb78d8823fdb2d1559d135cc77091bd12971277390b0796fa464b7`,
retains one compiler warning: `runtime_fixture.c:468` has a 2,264-byte frame,
exceeding the configured 1,024-byte warning threshold. This is the ordinary
status-read function with a 2,048-byte text buffer. The warning is not hidden or
a support result for auxiliary stack unwinding.

The [live5 controller](guest/live5-controller.py), SHA-256
`ce7ce07c512a5f0c158225fea378163d292f05208fad45c29e7890e6fe6ce6a1`,
was copied to persistent guest storage and
[parsed only](guest/live5-controller-ast.json). It requires the actual kernel-3
postboot identity and GS proof before loading, and passes explicit 65,536 event
records, four dependency pages, 262,144 source bytes and a 134,217,728-byte wire
log bound. Its 600-second observer retains a still-running child without a drain
claim. It was not executed in this receipt.

[The guest file index](guest-file-index.json) and
[collection result](collection.json) verify all 17 copied files (142,055 bytes)
against the guest bytes. `SHA256SUMS` covers the retained local record. Raw
compiler commands and symbol output are retained without whitespace edits.

The staged whitespace check reports three trailing-space lines in raw
`build.log` and two in raw `modinfo.txt`. These captured command/output bytes
remain unchanged; authored metadata and this summary pass the whitespace check.
