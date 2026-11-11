# Kernel8 private rwsem/query and mutex regressions

Both private runners passed their protected mechanism checks and completed ordinary teardown on kernel8. These records test private source bodies. They establish no generated real-MM completion, full C-function epilogue, general native-context support or performance result. [Saved-record audit](audit.json)

The running identity was boot `e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0`, release `7.0.0-38-kdrebuild8`, BuildID `a33dd4d11d0f0c6649107507e685b6e86e716c1a`, with the exact kernel8 ELF/config and full `current_task` GS input. The core was `0d42063e`. Both signed fixtures were compiled from `140aecc4`. The host compiler/runner snapshot was the separate clean `a99186a5` 143-member export, with all 78 kernel core hashes unchanged. This is separate from the later K grouped-ACK snapshot `6a4ba5a1`. [Rwsem outer receipt](collection/payload/rwsem-controller/result.json.gz), [mutex outer receipt](collection/payload/mutex-controller/result.json.gz), [host snapshot](snapshot/source-state.json), [kernel8 boot evidence](../kernel8-boot-20261111/README.md)

The signed module byte streams are retained exactly. Rwsem SHA256 is `2947b46323911b9325c371c07e4e0b43ddc0b6bba120b05517f776876155a961` and mutex SHA256 is `654d429ef84d885decc7fbf695efd39ca872404132c98b7ed55f38c1ff6ade91`. Their original `.ko` guest paths and identities remain in the collection index. The separate compilation record retains the rwsem 4352-byte frame and missing checkpoint prototype warnings and the mutex 2264-byte frame warning. These runtime checks do not establish general stack coverage. [Rwsem module bytes](collection/payload/rwsem-module), [mutex module bytes](collection/payload/mutex-module), [affected builds and warnings](../kernel8-affected-build-20261111/README.md)

The generic runner inputs stayed at four workers and eight iterations, with separate controlled reader and recursive scenes. Finite compiler, source, frame, learning, holder, request, image and wire bounds are retained with the actual arguments. Each family verified the supplied two-byte `its_return_thunk` span against the exact kernel8 ELF. Original compiler/backend and GS lowering were preserved. [Rwsem arguments](source-host/rwsem-arguments.json), [mutex arguments](source-host/mutex-arguments.json), [runtime receipts](audit.json)

| Saved result | Rwsem/query | Mutex |
| --- | --- | --- |
| Final observation rows | 7257 | 4691 |
| Observation overflow | 0 | 0 |
| Compiler cycles | 16 | 5 |
| Publications | 13 | 4 |
| Acknowledged coverage keys | 13 | 8 |
| Wire responses, all status zero | 90 | 32 |
| Settled archive keys | 4 | 0 |
| Pending before shutdown | 2 | 0 |
| Warm claim empty | false | true |
| Warm claim adds no new facts | true | true |
| Source regions and bytes | 4 / 8207 | 4 / 5079 |
| Dependency pages | 2 | 2 |

These counts come from the new kernel8 receipts and raw wire frames. The rwsem coverage-ACK count is 13 and is not reused from the earlier kernel6 result. Rwsem's warm claim retained two intentional fact keys without adding facts. Its four deliberate reader/downgrade miss records were archived and settled after shutdown collected the late records. Coverage ACK and archive settlement remain separate dispositions. [Rwsem result](collection/payload/rwsem-runtime/result.json.gz), [mutex result](collection/payload/mutex-runtime/result.json), [wire and archive audit](audit.json)

The two ordinary recursive modes retain one original S_W and distinct acquisition records while current execution follows C_A to C_B and back to C_A. Both rwsem child/root modes complete the protected source episodes with DONE3. Mutex mode1 has child/root DONE3, while mode2 has child UNWIND5 and root DONE3 with its exact deferred outer notification and return-user lifetime. Physical callbacks, source drops, final release retirement, ready publication and slot reuse remain separate checks. Native C epilogues remain outside the protected generated episode. [Rwsem warm proofs](collection/payload/rwsem-runtime/result.json.gz), [mutex warm proofs](collection/payload/mutex-runtime/result.json)

Rwsem also retains concurrent and repeated real read credits, native real downgrade, shared-B release returning to the enclosing A proxy, selected retained-writer downgrade, nested terminal return with ancestor physical duties and the deliberate native miss suffix. Matching retained UP_READ waits for the exact physical writer ACK before native continuation. The complete source, events, per-scene proof rows and once-only effect counters are retained. [Rwsem reader proofs](collection/payload/rwsem-runtime/result.json.gz), [final raw observations](collection/payload/rwsem-runtime/observations-final.bin)

The five query checkpoints distinguish an unused unlocked B1 object `(0,0)`, an actual shared B read `(1,0)`, physical WRITE `(1,1)`, logical retained READ that still holds physical WRITE `(1,1)` and native real-converted READ `(1,0)`. Results are checked as integer 0/1 before Boolean aggregation, with exact original-worker counters and zero invalid results. Generated query records join the typed CALL, frame and slot incarnation, current executor/binding/image and exact post-CALL reentry without creating a queue, grant, read credit or mode change. The native real-downgrade checkpoint uses its original-task result path and has no generated QUERY_RESULT claim. The full rwsem buffer contains 30 QUERY_RESULT rows across learning and final checks, including sixteen rows in the four complete selected scene proofs. [Query proofs and counters](collection/payload/rwsem-runtime/result.json.gz), [raw/query binding audit](audit.json)

The rwsem shutdown archive has SHA256 `3a763aee50ab5f2d816b984c4349c276f303d1c8ba946524c2a9a3f836ec7e7d`. The mutex archive has SHA256 `a0d1d1c53609bcf46fec2fe7022f9823c620a8fdf9e72d949319d82047bf83f3`. Each final SHUTDOWN, ARCHIVE, SETTLE and END response returned zero. Both controllers then checked that fixture modules and devices were absent, activity was empty and only NLS remained. The same candidate8 boot and actual taint 4096 were preserved. Rwsem followed the separately proved K02 cleanup and mutex followed the actual rwsem completion. [Rwsem archive](collection/payload/rwsem-runtime/shutdown-archive.json.gz), [mutex archive](collection/payload/mutex-runtime/shutdown-archive.json), [outer identities](audit.json), [K02 cleanup](../kernel8-killable-exit-recovery-20261111/README.md)

All 1025 guest payload files with 67,060,521 bytes are retained, including both module byte streams, the 143 source members, generated images/objects, flat metadata, wire bytes, observation buffers and archives. The source-host control records are preserved separately. Large text and mixed wire frames use lossless gzip with exact raw/stored hashes and readback verification. The duplicate 67,942,400-byte collection tar and duplicate 143-member source tar are omitted only after full safe-member/name/size/hash audits matched every retained member. Their exact transport hashes and audited exclusions are recorded. [Copy provenance](copy-index.json), [transport exclusions](excluded-inputs.json), [checksums](SHA256SUMS)

The offline audit uses saved bytes and standard-library scalar/byte comparisons. It invokes no project module, compiler, helper replay, runtime workload, VM or network action. No source-host test execution is claimed.
