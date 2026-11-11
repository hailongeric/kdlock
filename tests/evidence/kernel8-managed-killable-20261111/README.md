# Kernel 8 managed killable K04 mechanism pass

K04 passed all five named scenes and both learning scenes, then completed
ordinary archive settlement, provider retirement and module unload. All 19
original children have actual waitpid observations and returned, reaped exit
acknowledgments: 13 exited normally and six received SIGKILL. This is private
mechanism evidence. It establishes no real MM JIT execution, full generated C
epilogue return, general nested cancellation, native-context expansion or
performance result. [Runtime result](collection/payload/runtime/result.json.gz),
[outer result](collection/payload/receipts/result.json.gz), [offline audit](audit.json)

The earlier K03 run remains failed in its separate
[claim and recovery record](../kernel8-killable-claim-recovery-20261111/README.md).
K04 ran only after K03's actual ordinary cleanup and the new runner's single
successful AST check. The provider build and AST check remain separate in the
[provider and AST record](../kernel8-provider-build-runner-ast-20261111/README.md).

## Exact execution identity

| Item | Identity |
| --- | --- |
| Host compiler and runner source | `5c14b483ca16b3bba8f3dd40a00f16a6efefc12c` |
| Compiled fixture source | `140aecc4f83a6b6ae6f20245234e8a63504f9210` |
| Linked kernel core | `0d42063ead37dc8fc1631fa56c8348890ede9c5f` |
| Signed fixture SHA-256 | `74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8` |
| Kernel release / boot | `7.0.0-38-kdrebuild8` / `e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0` |
| Kernel Build ID | `a33dd4d11d0f0c6649107507e685b6e86e716c1a` |
| Outer result SHA-256 | `d7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488` |
| Runtime result SHA-256 | `d50378c6e084a41eca1da70e23f9d76b7df80048175e85f6fba6ce57cb7bb062` |
| K03 cleanup predecessor SHA-256 | `40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0` |
| Actual runner AST result SHA-256 | `3fc26667154f5232125e0e02ea40e11084a39fd475e5a44367d30514bc7d2de0` |
| Fresh three-disk recovery receipt SHA-256 | `86e4eb06f9b478f3907a3d78b0d2a216d9e3bbbfdf3898a3f628f983b735ac13` |

The actual argument vector, all 39 finite caller limits, original GS proof and
two-byte `its_return_thunk` bootstrap remain retained. The outer helper SHA-256
is `d760565b7ca37b1ed5cd3a8404ca8e4448e4203050e9007e467737bd1ee6789d`;
the limits SHA-256 is
`23f2208dd9fe4f0d55df3cfe7955d10005a99b22995cb2b2e8f744b270a68cb8`.
The same 143-member source export has 1,612,508 source bytes, and all 78 kernel
core hashes match the linked core. [Arguments](source-host/actual-argv.json),
[limits](collection/payload/input/limits.json),
[source state](source-export/source-state.json),
[kernel package](source-export/kernel-package-0d42063e.json)

## Scenes, cancellation and lifetimes

The complete raw observation stream has ABI 1, 20 words per row, capacity
131072, 241 rows and zero overflow. Its SHA-256 is
`4308a0de2912c07480e1ac0a842c6f49e6ee6a98bda63a9c59fb14875c4f5343`.
The offline audit joins all 134 event dictionaries embedded in the runtime
result to their exact raw words. Numeric indices below refer to this stream.
[Raw observations](collection/payload/runtime/observations-final.bin),
[decoded observations](collection/payload/runtime/observations-final.json.gz),
[independent audit](independent-peer/audit.json.gz)

| Scene | Exact ordering witness |
| --- | --- |
| `ready-before-fatal-cancel` | Physical grant 5 wins; its physical completion, source drop and ready publication precede slot free 18. |
| `reader-drain-cancel` | Canceled 27, retire-ready 28, slot free 29; the original read grant remains held during cancellation. |
| `queued-exit-before-holder-release` | Canceled 37; actual waitpid observed at event cut 38 while H remains held. H begins ordinary release at 38/39; W retire-ready 41 and slot free 42 follow. H physical completion is 44. |
| `learning-0` | First learning publication; its ACK contains zero coverage keys. |
| `learning-1` | Second publication; one ordinary coverage key is ACKed; the native helper frontier remains pending. |
| `origin-signal-wakes-foreign-c` | The original W registers C as its physical wait task; canceled 165, retire-ready 166 and slot free 167; actual waitpid is observed at event cut 168 before releasing the original reader. |
| `candidate-cancel-drains-current-w` | W grant 204, native frontier 206/207 and physical end 214 precede C cancellation 216. W native ACK 218 and source drop 219 precede D grant 222; C slot free 235 and W slot free 236 remain separate. |

Each completed scene retains exact task, source-state, acquisition, queue node,
physical owner and image records. Physical release, source drop, final release
retirement, owner retirement, ready publication and slot free remain distinct
events. The raw retirement records and actual child exits are preserved; an
exit is not inferred from a role becoming inactive. The original safe native
context handback remains the execution boundary. No new native-context or CPU
reservation architecture is introduced. [Runtime proofs](collection/payload/runtime/result.json.gz)

## Fixed image, exact frontier reservations and shutdown

There are four compiler cycles, two image publications and one acknowledged
ordinary coverage key. Cycles 3 and 4 publish nothing and retain the same image.
The fixed claim reports `fixed_claim_no_new_facts=false`,
`fixed_claim_no_new_ordinary_learning=true`,
`fixed_claim_only_expected_native_frontiers=true`,
`fixed_image_unchanged=true`, `fixed_snapshot_unchanged=true` and
`fixed_claim_published=false`.

The two pending record identities are `0xff11000108b001d4/incarnation 1` and
`0xff11000108b002c4/incarnation 1`. They retain separate exact FactKeys in epoch
`0xff11000105bcf800`, with producer `0xff1100010c13b000` and image
`0xff1100010c13b138`. They describe the same intentional helper frontier:
COVERAGE_MISS (3), UNRESOLVED_TARGET (10), IP/cursor `0xffffffffc000b4e6`,
target `0xffffffffc000b300`, TARGET_READY (1), UNCLASSIFIED (0), entry result 0.
The reached indirect CALL is the actual five bytes `2e2e2effd0`. The native
target lies outside all five exported source regions.

Each reservation joins a separate completed root invocation. Their raw
reserve/frame/grant/ENTER/EXIT/FORWARD chains are
102/103/112/113/114/115 and 191/192/204/205/206/207. They have separate original
task lifetimes and slot-free events 145 and 236. Equal frontier scalars do not
combine their acquisition identities. [Frontier and claim proofs](audit.json)

All 22 recorded channel responses returned status zero. Their final ordinary
protocol is SHUTDOWN sequence 18, ARCHIVE_CLAIM 19, SETTLE 20 and END 21. The
218,365-byte shutdown archive has SHA-256
`fc2220a597868184cb5731251f8a33b7869f6c541bbb6c7f0802846440782d1e`.
Its exact claim and fact keys equal both pending frontier keys. The actual
SETTLE request contains that archive digest; its actual reply contains both
exact keys. Neither frontier receives a coverage ACK. Archive settlement and
ordinary coverage ACK remain different dispositions.
[Archive](collection/payload/runtime/shutdown-archive.json.gz),
[SETTLE request](collection/payload/runtime/wire/attempt-00000021/request.bin),
[SETTLE reply](collection/payload/runtime/wire/attempt-00000021/reply.bin)

The final status has `retired=1`, `pool_idle=1`, zero native scopes and no live
binding, source, runtime, trace, self-hold, queue, gates or roles. The outer and
post-close checks found no fixture devices, actors, retained controller or
runner. The 16 linked outputs, kernel source/protected outputs, signed fixture,
limits, 143 source files and boot files remained unchanged. Boot and Build ID
are unchanged; taint remains 4096 and only `nls_iso8859_1` remains loaded.
[Post-close check](source-host/postread.json)

## Retained bytes and offline inspection

All 179 selected guest payload files (2,093,451 bytes), their exact indexes,
complete collection transport and collection controls are retained. The full
frozen source transport, manifest and state are included. Source-host launch,
recovery, staging, collection and post-close controls are preserved as historical
inputs; they must not be replayed as current commands. The earlier failures
remain in their own evidence directories.

Files of at least 65,536 bytes use lossless gzip, except ELF/object/module files
retained directly. `copy-index.json` records each original path and identity,
exact raw hash and stored hash. No complete transport tar is omitted. Both
generated `image.o` objects are retained under their original relative paths;
the signed fixture module is identified by its exact checked SHA-256 and is not
an additional selected payload file. [Copy index](copy-index.json),
[checksums](SHA256SUMS)

`archive-copy.py`, `audit.json` and the separately retained independent audit
use source-host standard-library byte, hash, tar, event, ELF and wire inspection.
They run no project imports, tests, builds, workloads or VM operations. The
runtime pass is established by the original VM receipts and raw observations.
