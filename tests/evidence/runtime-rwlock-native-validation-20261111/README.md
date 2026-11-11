# Rwlock native validator failure and ordinary cleanup

The rwlock runner returned 1 after 1.511829717 seconds, with `failed_or_incomplete`. Its source-host observer returned 1 after 2.723276166 seconds. The actual error is `native spin suffix lacks the original task's synchronous source unlock` in the reused atomic validator. This is a failed native-validation attempt, before source export or generated image construction. [Runner result](collection/payload/attempt/result.json), [controller result](collection/payload/controller/result.json), [source-host failure diagnostic](source-host/live-controller/failure-diagnostic.json).

It used fixture `e5b78520b5098565d1ef9955eb1ed8f9f838bd0f`, core `1114b41ea0f6ecf92f2c9af2904a4218bb344829` and module SHA256 `837b14df2af5ce9185232fa1255f7f3a07a780f3a7f251fae6361626c839b600`. The boot was `b827f92c-254a-4cd3-a989-c6ea32c74605`, kernel `7.0.0-38-kdrebuild5`, with expected existing module taint 12288 after the completed rwsem run. The common module-build result is SHA256 `7c9be0511082f516c057c035e3fb5ec57596d3e11da9f79255369693c694f888`. [Source state](source-host/fixture/source-state.json), [kernel pins](source-host/fixture/kernel-pins.json), [module-build receipt](source-host/fixture/module-result.json).

## Actual native unlock

The observation header is ABI1 with 20 words per row, capacity 65,536, count 653 and overflow 0. There are zero `JIT_ENTER` and zero `SELECT_PROXY` records. The actual enum value 29 is `NATIVE_UNLOCK`. The saved buffer SHA256 is `98081f6dd92907dc09a5d1ad198ebe17f842224b699b47557b81b9ea0ac79fba`. [Raw observations](collection/payload/attempt/observations-failure.bin), [independent saved-byte diagnosis](analysis/diagnosis.json).

| Raw row | Exact native lifetime |
| --- | --- |
| 579 | W enqueues node `0xff1100014e600068`, acquisition `0xff1100014e6002d9`, task/state `0xff11000352378000` / `0xff110001090d7400` |
| 635 | The same node receives its local writer grant |
| 644 | The same original task/state/node reports write unlock operation 14 with action 1, `BATCH_HEAD` |
| 645 | Its physical release callback begins |
| 647 | The physical callback completes |

The validator incorrectly required spin action 3 for this native rwlock path. Native rwlock ownership instead selects its active batch, handles its own writer grant and reports action 1. A foreign writer released after generated handback uses exact SYNC action 4. The source correction at `09834f09` therefore requires action 1 only in the no-image case and action 4 only in the foreign-image case, plus typed write-unlock operation 14. Spin retains action 3 with operation 5. It does not accept an unconditional set of actions. [Actual rows](analysis/diagnosis.json), [frozen failed source archive](source-host/fixture/source.tar).

The failure occurred after the five native workers finished with clear locks. No source channel exchange, compiler cycle or producer image existed. Wire reservations are zero. The available records support the native unlock and validator diagnosis, and establish no rwlock generated-episode pass. [Original failure result](collection/payload/attempt/result.json), [source-host controller traceback](source-host/live-controller/failure-diagnostic.json).

## Ordinary native-only recovery

The local recovery command returned 0. Its stdout records `ORDINARY_NATIVE_ONLY_RECOVERY_COMPLETE`, ordinary stop and destroy, `rmmod_returncode` 0, unchanged dmesg and successful unload. The reviewed helper requires the exact failed result hashes, 653 records, five finished workers, clear locks, no export and zero wire reservations before those operations. Runtime destroy performs its ordinary internal shutdown. No compiler-protocol replay or coverage ACK was needed. [Actual recovery command/result](source-host/recovery-controller/command.json), [recovery stdout](source-host/recovery-controller/stdout.log), [matching helper](source-host/recovery-helper.py.txt).

The full guest native-cleanup directory has not been copied in this source-host retention slice. Its raw statuses, task lists, dmesg and result file remain for later collection. The local command return and stdout are retained without synthesizing those missing raw files. [Missing inputs](missing-inputs.json).

## Retention and scope

All 12 original guest files, totaling 572,238 bytes, match their captured sizes and hashes. Original before/copy/after inventories are preserved. The original collection tar is stored losslessly as `copy.tar.gz`. The same 121-file e5 fixture archive, exact manifest/state, kernel pins and common module-build result are included for independent source comparison. [Original guest index](collection/copy-index.json), [source-host copy index](source-host-copy-index.json), [source archive](source-host/fixture/source.tar), [retention summary](retention-summary.json).

This native-only failure has no generated JIT completion, general reader/writer support or performance claim. It does not alter the separate successful rwsem receipt. The unprotected C epilogue, physical numerical context and assembly/unwind limits remain distinct. Raw captured whitespace is preserved. Offline retention performed no project imports, AST, tests, builds, guest/network calls, code changes or behavioral retries.
