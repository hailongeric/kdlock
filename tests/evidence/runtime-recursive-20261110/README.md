# Protected JIT completion and recursive delegation — 2026-11-10 UTC

The single live5 controller returned **0**, and the actual runner saved
**`protected_jit_recursive_mechanism_pass`**. On one fixed generated image,
two warm plain proxy requests completed their protected JIT episodes. Two
five-task scenes then established distinct-task recursive delegation through
C_A → C_B → C_A, including a child `EPISODE_DONE` result and a child
`UNWIND_PARENT` result for deferred outer unlock. Exact physical callbacks,
release users and final slot retirement were also observed.

This is kernel mechanism evidence. The completed scope ends after the matching
protected source unlock. The final C function epilogue remains native and is
explicitly outside this completion claim. The result does not establish a
real-world syscall workload, T01–T56, performance, arbitrary nesting, complete
mitigation coverage or complete auxiliary stack/unwinder support.

## Exact run identity and limits

| Input | Actual identity |
| --- | --- |
| Frozen fixture/runtime snapshot | `69ba6b030c1eb7e5f1c3f9461b70f5fef6791309`, 109 files |
| Core observation implementation | `1b50e37382d2c739b16953027c47d7e2388562f0`, 66 package inputs |
| Common compiler | `18c8f2e499d5fb74972e92bad5748489b921035d` |
| Running kernel | `7.0.0-38-kdrebuild3`, boot `bceee25d-a189-4f51-89fa-0e31322b70e6` |
| GNU Build ID | `264a4ef8e55952e5d9ceccf93f65f25f05a50c1f` |
| Linked ELF SHA256 | `c099d66949ba99bc0ec200ef1570cc2917e7b8a3eb0acdd97811333247d2a43d` |
| Configuration SHA256 | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| Loaded fixture SHA256 | `2be5cd04f9b7e5aa570c56dd1e940619e03696b33ef8d14bbc4262d2ac11a2a3` |

The linked core, actual boot and fixture compilation have separate receipts:
[kernel3 build](../kernel-build3-20261110/README.md),
[kernel3 installation/boot](../kernel-install3-20261110/README.md) and
[module4 build](../module4-build-20261110/README.md). The module build's
2,264-byte status-read frame warning remains recorded there.

The persisted controller SHA256 was
`ce7ce07c512a5f0c158225fea378163d292f05208fad45c29e7890e6fe6ce6a1`.
It ran exactly once, from 20:31:30.513996 to 20:31:33.519852 UTC; the observer
elapsed time was 3.005665945 seconds, not a performance measurement.
[command.json](guest/controller/command.json) retains actual argv and environment;
[result.json](guest/controller/result.json) retains controller return 0.
The runner's distinct result is [guest/runtime/result.json](guest/runtime/result.json).
The controller's empty stdout log is retained unchanged.

The fresh [HMP receipt](before-live5-host.json) verified the real recovery
snapshot on all three disks and 9,604,972,544 host bytes available. The
[guest preflight](guest/live5-preflight.json) recorded no fixture module/devices
or build/test activity, tracer `nop`, taint 0 and the successful actual postboot
and GS-proof hashes. Guest free bytes were 14,328,778,752 on the output filesystem
and 1,272,709,120 on root. The controller independently rechecked all 109 frozen
source files, module bytes and six actual linked output pins before loading.
The exact full linked GS input was `current_task == const_current_task ==
0xffffffff8440f018`, with per-CPU section/start `0xffffffff843f7000`.

The invocation passed explicit limits: four dependency pages, 262,144 source
bytes, 65,536 scalar observation records, a 134,217,728-byte wire log bound,
four ordinary workers, eight iterations and a 120-second per-operation deadline.
The outer 600-second observer retains any still-running child; it does not kill
or infer drain. Actual source export contained three regions and 5,077 bytes:
116 helper bytes, 865 body bytes and one 4,096-byte module-owned dependency page.
No named thunk model or compiler mitigation flag override was introduced.

## Fixed-image completion

Cold learning retained eight ordinary indirect-JMP facts and published four
images, with actual coverage acknowledgments `0, 2, 4, 2`. The fourth image,
`0xff1100010b643138`, remained fixed during all warm checks. A final consumer
claim was empty and published no image. The run finished with zero pending
facts and a zero-fact archive settlement. The 32 actual wire exchanges all
returned status 0; the final sequence includes shutdown, archive claim,
settlement and claim end. Actual wire reservations used 70,330,157 bytes of the
128 MiB bound. Raw requests, returned envelopes and replies remain under
[guest/runtime/wire](guest/runtime/wire); all four GNU objects, executable
images, flat metadata and five-blob stage inputs are retained under the cycle
directories. These actual receipts remain separate from a host boolean or
construction-only emission receipt.

The complete final trace has 4,691 records with overflow 0. Its binary header is
`[1, 20, 65536, 4691, 0]`; the file is 750,600 bytes, SHA256
`8ca3d9284f3d2a8702ffcfc001c06ca4ad128371d23ec51e8a9822b84394081c`.
[raw-correlation.json](raw-correlation.json) verifies every binary scalar against
the retained JSON representation. Records are 20 scalars, not a second register
packet or ownership references. Row numbers below are zero-based payload rows.

| Warm check | Positive generated execution | Actual source effects |
| --- | --- | --- |
| Plain | Two exact proxy-selected lifetimes each reached accepted matching JIT unlock and protected `EPISODE_DONE`; no native forward inside either lifetime | 32 total requests completed, 32 helper effects; the other 30 acquisitions won locally and are not claimed as JIT completions |
| Recursive mode 1 | C_A entry 4495 → child enqueue 4500 → C_B entry 4517 → child done 4522 (`3`) → C_A current return 4536 → parent done 4544 (`3`) | Five tasks finished; A effects 2, B effects 1, helper effects 3; all error counts 0 |
| Recursive mode 2 | C_A entry 4612 → child enqueue 4617 → C_B entry 4634 → child done 4644 (`5`) → C_A current return 4661 → parent done 4664 (`3`) | Five tasks finished; A effects 2, B effects 2, helper effects 4; all error counts 0 |

H_A/H_B held the two ordinary mutexes while C_A/C_B and W enqueued. Controller
gates outside protected source released H_A only after C_A and W's exact MCS
links were observed, then released H_B after C_B and W's child link. Selection
was performed by the ordinary optional local/proxy protocol. No core selection
gate forced a delegation. Both recursive scenes used one exact W canonical
state with distinct root/child acquisition identities and actual C_A/C_B task
identities. Current JIT return endpoints and cursors were matched across the
child return; mode 1 then reentered C_A's generated continuation. In mode 2,
the already-closed parent completed at the current child-returned cursor.
The final function epilogue remains native and is outside the generated
completion claim.

[The independent raw audit](audit/proof.md), with [full joined records](audit/proof.json)
and [audit source](audit/audit.py), reads only retained bytes using the standard
library. It imported neither project code nor the runner oracle. It independently
confirmed the fixed-image execution/exit/accepted-operation joins, exact
CA/CB selections, distinct acquisitions, child return bindings and positive
completion before root outward outcome conversion. `EPISODE_DONE.image` is
intentionally zero; image association comes from the exact earlier events.
No audit or source-host receipt check reran the kernel workload.

## Deferred physical release and retirement

In mode 2, outer A's exact request at 4636 selected the deferred route, followed
by marker 4637. Child completion 4644 precedes post-export unwind publication
4645 and notifier drop 4646. The original physical A owner handled it at 4660.
Its synchronous callback began at 4678 and returned successfully at 4680;
the exact source user dropped at 4683, all three release users were zero at
retirement 4684, readiness was recorded at 4685 and `SLOT_FREE` followed at 4690.
The return token dropped at 4662. These are partial ordering obligations;
return/notifier drops are not required to precede physical release generally.

| Scene | A callback begin/end | A source drop / release retirement / ready / free | B callback begin/end | B source drop / release retirement / ready / free |
| --- | --- | --- | --- | --- |
| Mode 1 | 4558 / 4560 | 4563 / 4564 / 4565 / 4570 | 4531 / 4533 | 4538 / 4545 / 4546 / 4569 |
| Mode 2 | 4678 / 4680 | 4683 / 4684 / 4685 / 4690 | 4655 / 4657 | 4663 / 4666 / 4667 / 4689 |

The audit joins exact callback, object, physical owner/task and source/notifier/
return users, with owner control-stop and owner retirement checked separately.
Readiness is recorded before its final publication. `SLOT_FREE` flags `0x86f`
observe acquired retirable plus queue/result completion, no result user, empty
pool users and idle components. This proves final slot retirement and reuse
eligibility, not an observed later reuse. Physical callback completion alone is not
reported as request retirement.

## Teardown and retained bytes

The ordinary runner completed shutdown/source-user drain, destroyed the runtime,
stopped/synchronized its listener and unloaded normally. The immediate
[poststate](guest/runtime/poststate.json) found no fixture module, devices or
worker/build/test activity. The same candidate boot remained running with taint
12,288 after the out-of-tree unsigned module, without the warning bit. Complete
kernel/task readback is retained in
[post-live5-readback.json](guest/runtime/post-live5-readback.json).
The final [input readback](post-live5-input-readback.json) independently compared
all 109 source files, 66 kernel package inputs, six linked output pins and exact
module bytes after live5. This is raw stdout from the bounded read-only SSH
comparison; it was not a saved guest file. The separately verified [ordinary return to the normal kernel](../return-normal5-20261110/README.md)
reached boot `884c4a65-4f4c-4a6b-89a3-cefd65221615`, release
`7.0.0-38-kdlock1`, baseline Build ID and taint 0. That normal boot is not pooled
with this candidate run.

[guest-index.json](guest-index.json) and [collection.json](collection.json) verify
all 232 exact guest copies (10,385,931 bytes). They include both observation
prefixes, source exports, raw typed claims, all stage artifacts, the four actual
GNU `image.o` files and every wire attempt. The source-host HMP receipt, final
input comparison and independent audit are additional retained records.
`SHA256SUMS` covers the stored evidence. Raw command/disassembly whitespace is
preserved. No further unit suite, build or live experiment ran during receipt
collection.

The staged whitespace check reports 153 trailing-space lines only in the raw
`guest/runtime/module.disassembly.txt`. Those captured bytes remain unchanged;
authored metadata passes the whitespace check.
