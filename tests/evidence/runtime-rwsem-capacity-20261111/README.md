# Rwsem first image staging capacity failure

The rwsem runner returned 1 after 2.007284320 seconds. Its source-host observer returned 1 after 3.626404691 seconds. The attempt used fixture `e990fde36cd5089fdb7a58d9d96d977a002f8c7b`, core `1114b41ea0f6ecf92f2c9af2904a4218bb344829` and module SHA256 `ad0caa3a6de4ea0decc6498bb23a11d408b024cfd41c64e66cae09e5977e19fb`. It ran on `7.0.0-38-kdrebuild5`, boot `6f99fdb9-8d47-46dd-9e72-dfa6ecd774f4`, with entry taint 0. This is a failed attempt. [Runner result](collection/payload/attempt/result.json), [guest controller result](collection/payload/controller/result.json), [source-host observer](source-host/live-controller/controller-result.json), [frozen source state](source-host/fixture/source-state.json).

Native-local execution completed eight iterations. The concurrent-reader, writer-first-reader, real native downgrade and repeated-read checks completed before first image staging. The saved observation buffer has 287 records and zero overflow. No generated JIT entry or image publication occurred. These earlier checks do not complete the rwsem generated-execution validation. [Raw observations](collection/payload/attempt/observations-failure.bin), [actual runner command](collection/payload/controller/command.json).

## Exact failure

The actual `STAGE_LOAD` response for sequence 4 has status `-28` (`ENOSPC`) and an empty reply. Its 643,258-byte request has SHA256 `7b2f9996d028c1ca10a0fec265f18849a5ca7ce3a89c625d35cc46149345e7e6`. The loader's combined text reservation was 524,288 bytes. Assembly, C metadata and manifest totaled 582,630 bytes, exceeding that reservation by 58,342 bytes. The loader checks this limit before accepting metadata or copying machine code. [Raw request](collection/payload/attempt/wire/attempt-00000005/request.bin), [actual response](collection/payload/attempt/wire/attempt-00000005/result.json), [independent saved-byte inspection](analysis/diagnosis.json).

| Retained blob | Actual bytes | Declared extent |
| --- | --- | --- |
| Assembly | 208,162 | Host per-text-blob limit 524,288 |
| C metadata | 232,613 | Host per-text-blob limit 524,288 |
| Manifest | 141,855 | Host per-text-blob limit 524,288 |
| Machine code | 37,785 | 131,072 |
| Flat metadata | 22,763 | 262,144 |

Flat metadata contains 24 entries, 607 decoded source sites and zero observations, within the respective 64/4,096/4,096 limits. The channel frame extent is 2 MiB. The exact source bounds were 16 dependency spans and 131,072 copied bytes. The invocation supplied 65,536 event records, a 268,435,456-byte wire log bound, 16,000,000 runtime block visits, a 20,000 ms holder bound and 1,000,000 source coordination iterations. The later capacity correction `68a2e5ed` raises only reader fixtures' combined text reservation to `3 * 512 KiB`, matching the existing per-blob host limits. [Recorded limits](collection/payload/attempt/result.json), [source snapshot manifest](source-host/fixture/source-manifest.json).

## Ordinary recovery

The retained recovery controller returned 0. Its actual stdout records exact adoption of cached sequence 4, then ABORT5, END6, SHUTDOWN7, ARCHIVE8, SETTLE9 and END10 with status 0. The zero-fact archive was fsynced and rehashed before settlement. It contains 4,187,139 bytes with SHA256 `2bf0ad97e9055bbbcf1ed7998571f8471d91a14464c32add8beeeaef1237f8c0`. The helper then reports ordinary destroy/unload, no remaining module/devices/workers, unchanged dmesg and unchanged boot/taint 12288. Recovery completion is separate from the failed attempt. [Actual recovery stdout](source-host/recovery-controller/stdout.log), [outer return code](source-host/recovery-controller/controller-result.json), [matching staged helper](source-host/recovery-helper.py.txt), [copied final stdout object](analysis/recovery-stdout-final.json).

The complete guest recovery directory and archive bytes have not been copied in this offline retention slice. Their recorded guest paths, sizes and hashes are retained for later collection. Recovery claims here are bounded by the actual local controller output and reviewed helper. [Missing inputs](missing-inputs.json).

## Retention and limits

The original collection contains 54 guest files totaling 2,077,767 bytes. All copied payload sizes and hashes match the original index. The before/copy/after inventories retain original file identities. The original collection tar is stored losslessly as `copy.tar.gz`; decompression reproduces its recorded hash. The 121-file source tar was read without extraction and every member matched its manifest. Source-host staging and module-build observer records returned 0 and are retained separately from the failed live result. [Original guest index](collection/copy-index.json), [source-host copy index](source-host-copy-index.json), [source archive](source-host/fixture/source.tar), [module-build observer](source-host/fixture/module-build-controller-result.json), [retention summary](retention-summary.json).

Raw compiler/disassembly/log bytes retain their original whitespace. This retention performed source-host offline copying, hashing and archive inspection only. No project imports, AST checks, tests, builds, guest commands or retries ran during retention. The fixture remains mechanism evidence with its native C epilogue and declared physical-context limits. This failure establishes no reader-family runtime support, general progress or performance result.
