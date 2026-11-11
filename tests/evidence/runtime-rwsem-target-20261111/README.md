# Rwsem warm reader path coverage failure

The capacity-corrected rwsem runner returned 1 after 4.513404890 seconds. Its source-host observer returned 1 after 6.184116688 seconds. Fixture `68a2e5ede135429e63cb6547055f310152118917` retained core `1114b41ea0f6ecf92f2c9af2904a4218bb344829`. Module SHA256 is `f452008acbec7f691535134e648e517134b93d924271230c7cad59738a3c1f41`. This attempt ran on `7.0.0-38-kdrebuild5`, boot `9336b735-78f0-4f9c-9d9e-f04677f8d6bc`, with entry taint 0. The overall result remains failed/incomplete. [Runner result](collection/payload/attempt/result.json), [guest controller result](collection/payload/controller/result.json), [source-host observer](source-host/live-controller/controller-result.json), [frozen source state](source-host/fixture/source-state.json).

Image staging succeeded. Ten compiler cycles produced seven publications and seven coverage ACKs, with publication ACK counts 0/1/2/1/1/1/1. Native checks, training and the earlier warm plain/writer-recursion cases completed before the first warm shared-B reader assertion failed. The buffer contains 9,241 records and zero overflow. Those completed cases and publications do not establish the failed reader continuation check. [Cycle summaries and earlier checks](collection/payload/attempt/result.json), [raw observations](collection/payload/attempt/observations-failure.bin).

## Actual source continuation

The fixed image is `0xff11000106f63138`. The final image has no emitted ordinary edge for the reached CALL at `0xffffffffc000cff5` to helper `0xffffffffc000b010`. The source bytes are `2e 2e 2e ff d0`, printed by objdump as `cs cs cs call *%rax`, with next IP `0xffffffffc000cffa`. The original compiler correctly retained this five-byte CALL and emitted its unresolved-target exit. The fixture's CALL scanner omitted the prefixed mnemonic from its diagnostic CALL table. [Final construction manifest](collection/payload/attempt/cycle-10/manifest.json), [actual emitted assembly](collection/payload/attempt/cycle-10/image.S), [source disassembly](collection/payload/attempt/source-2.disassembly.txt), [independent saved-record diagnosis](analysis/diagnosis.json).

| Raw row | Observed transition |
| --- | --- |
| 9185 | C_A acquired the real B READ credit for W state `0xff11000342275800`, acquisition `0xff110003589807b9` |
| 9186 | The child entered the fixed JIT image at `0xffffffffc000cfe5` |
| 9187 | `COVERAGE_MISS` kind 3, detail 10, `TARGET_READY` phase 1 at `0xffffffffc000cff5`, target `0xffffffffc000b010` |
| 9188 | Current source state forwarded at that same pre-CALL cursor |
| 9189 | Parent received terminal child outcome 4 |
| 9193 | Native W released B's exact same READ acquisition |
| 9194 | Native `UP_READ` operation 7 completed on W |
| 9213 | Native W later released the retained outer writer grant |

No JIT-accepted B `up_read` or parent JIT reentry occurred in that scene. B's actual typed release is the later source CALL at `0xffffffffc000d016`, with post-CALL continuation `0xffffffffc000d01b`. The raw rows show an uncovered ordinary target followed by native handback, while retaining the same canonical state and acquisition. They do not reproduce a parent-return implementation defect. The warm assertion correctly remained unsatisfied. All worker effects completed with zero recorded effect/context errors, and ordinary retirement later left workers and locks clear. [Exact selected rows and producer receipt](analysis/diagnosis.json), [matching source bytes](collection/payload/attempt/source-2.bin).

The declared limits were four workers, eight iterations, 65,536 event records, a 268,435,456-byte wire log, 16 dependency spans, 131,072 source bytes, 16,000,000 runtime block visits, a 20,000 ms holder bound and 1,000,000 coordination iterations. The combined text reservation was `3 * 512 KiB`; machine and flat extents remained 128 KiB and 256 KiB. No core or original backend change was used for this retake. [Actual command](collection/payload/controller/command.json), [recorded source and runtime limits](collection/payload/attempt/result.json).

## Ordinary recovery

The retained recovery controller returned 0. Its stdout records exact adoption of cached END49, then SHUTDOWN50, ARCHIVE51, SETTLE52 and END53 with status 0. One pending fact was archived and SETTLED independently of coverage ACK. The fsynced archive is 46,010,268 bytes with SHA256 `980f532169b1eb5073b2a40a274d7f7385f47f6538e7e5008c500df0e208e9c9`. Ordinary destroy/unload followed, with module/devices/workers absent, unchanged dmesg and unchanged boot/taint 12288 reported by the helper. [Actual recovery stdout](source-host/recovery-controller/stdout.log), [outer return code](source-host/recovery-controller/controller-result.json), [matching staged helper](source-host/recovery-helper.py.txt), [copied final stdout object](analysis/recovery-stdout-final.json).

The full guest recovery directory and 46 MB archive remain uncollected in this source-host slice. Their guest paths and actual recorded hashes/sizes are retained. This directory does not substitute local summary data for those missing raw files. [Missing inputs](missing-inputs.json).

## Retention and limits

The original collection has 361 guest files totaling 22,953,832 bytes. Every payload matches its original copied size/hash, with the before/copy/after inventories retained. The collection tar is preserved losslessly as `copy.tar.gz`. Both its decompressed hash and all 121 source-tar members were checked offline. Source-host module staging/build controller records are retained with the immutable fixture archive and exact source state. [Original guest index](collection/copy-index.json), [source-host copy index](source-host-copy-index.json), [source archive](source-host/fixture/source.tar), [module-build observer](source-host/fixture/module-build-controller-result.json), [retention summary](retention-summary.json).

Raw compiler/disassembly/log whitespace is preserved. Offline retention made no project imports, AST checks, tests, builds, guest calls or source replay. The protected-episode goal remains separate from the native C epilogue, physical numerical context, assembly/unwind limits, general reader-family support and performance. Neither this failed attempt nor its successful ordinary recovery establishes the missing generated reader continuation proof.
