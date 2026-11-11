# Mutex regression after plain spin — 2026-11-11 UTC

The actual controller and runner returned **0** with `protected_jit_recursive_mechanism_pass`. The independently run saved-record auditor also returned **0**. The controller observer recorded 3.684735 seconds. This is kernel mechanism evidence from the ordinary `kd_mutex_lock/kd_mutex_unlock` pair.

The run used fixture source `db7d7d6e38e1341e24b643553bd83633616d4ea7`, kernel core `2d0ad60b0bc46929f3070aefa364e710c0a81115` and `7.0.0-38-kdrebuild4`, BuildID `f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053`. Boot was `1b3b298f-051b-42ea-a53b-429c16f4e114`. The [module-build record](source/module-build-result.json) binds all 103 frozen files, 67 kernel inputs and six actual kernel-output hashes. The [module source record](../module-spin-db7-build-20261111/README.md) preserves both module builds and the [shared private include](../module-spin-db7-build-20261111/source/fixture/tests/kernel/payload/runtime_fixture_observe.inc).

The actual module SHA256 is `bdbfb2111e64d13a8b8416c2b43b91851c227346fdbe3c7fc6e06253a9ac0515`. [Source state](source/state.json), [complete manifest](source/manifest.json), [fixture manifest](source/fixture-inputs.json), [reviewed controller](source/fixture-controller.py) and [actual argv](controller/dispatched-argv.json) are retained. Kernel build and the fresh boot have separate [build](../kernel-build4-20261111/README.md) and [repeat-boot](../kernel-repeatboot4-db7-20261111/README.md) records.

This regression ran after the [successful spin run](../runtime-spin-recursive-20261111/README.md) on the same boot, with the expected module taint 12288. Its controller binds the exact successful spin receipt before admission. The ordinary mutex path retained its deferred outer-unlock sequence. The mode-2 child returned UNWIND_PARENT outcome 5, followed by current-state return and root outcome 3.

Actual source export contained **4 regions and 5,079 bytes**. The caller supplied the ELF symbol extent at `0xffffffff8271be20`, length 2, bytes `c3 cc`. [The retained ELF span](runtime/builtin-source-elf.bin) has SHA256 `56de62c1837575efee31915828000fde2932e3c34c06b498f648ecaf6bae8d7c`. Actual SOURCE bytes matched that executable ELF span before compilation. The ordinary source-byte decoder/backend consumed it with the existing CALL/RET handling. The [earlier omitted-span failure](../runtime-spin-frontier-20261111/README.md) and [ordinary recovery](../runtime-spin-recovery-20261111/README.md) retain their own records.

The four images retain private image ABI version 1, a 168-byte canonical register backing and a 56-byte IO record. The full linked `current_task` GS input is `0xffffffff8440f018`. Per-cycle source, assembly, C metadata, linked images, machine bytes, actual GNU objects, COMMITTED receipts and ACK replies remain under `runtime/cycle-*`. Raw source export and its address/length metadata are retained with the actual wire frames.

All **32 wire attempts** completed with status 0. Four actual publications ACKed `0 / 2 / 4 / 2` exact facts, totaling **8**. A later empty claim ended without another publication. Every included fact is joined to its actual producer, source version, candidate, emitted input, COMMITTED old/new image identities and exact ACK subset by the [saved proof](audit/verified/proof/proof.json). The fixed warm image was `0xff11000353fb1938`.

[Raw observation history](runtime/observations-final.bin) contains ABI1, 20 words per row, capacity 65,536, **4,691 rows and zero overflow**. Row IDs below are zero-based positions in that immutable prefix. The proof carries exact state, task, object and acquisition identities. Each scene uses its own reserve/free interval to distinguish reused addresses. The auditor found 2 positive warm-plain proxy lifetimes.

| Warm mode | A/B proxy selections | Child JIT entry | Child completion row | Current-state return row | Parent reentry row | Root completion row |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4491 / 4513 | 4517 | 4522 | 4536 | 4539 | 4544 |
| 2 | 4608 / 4630 | 4634 | 4644 | 4661 | Root already closed | 4664 |

| Warm mode | Canonical S_W | Root A / child B requests | C_A / C_B physical tasks |
| --- | --- | --- | --- |
| 1 | `0xff1100034b6fc800` | `0xff110003bc880068` / `0xff110003bc8804c0` | `0xff11000350513180` / `0xff110003503bb180` |
| 2 | `0xff1100034b6fc800` | `0xff110003bc880068` / `0xff110003bc8804c0` | `0xff110003503b3180` / `0xff11000345bc3180` |

Physical callbacks and final retirement have separate rows. The callback rows name the retained physical owner and its exact callback. RELEASE_RETIRE has zero source/return/notifier users. NODE_RETIRE_READY precedes the final retirable publication, and SLOT_FREE records acquired retirable state, empty pool users and idle components. The table establishes final retirement eligibility. Subsequent storage reuse is outside this record.

| Mode/request | Request / owner handled | Physical callback begin/end | Control stopped | Source user dropped | Release retired | Node ready / slot free |
| --- | --- | --- | --- | --- | --- | --- |
| 1/A | 4541 / 4542 | 4558 / 4560 | 4554 | 4563 | 4564 | 4565 / 4570 |
| 1/B | 4519 / 4520 | 4531 / 4533 | 4527 | 4538 | 4545 | 4546 / 4569 |
| 2/A | 4636 / 4660 | 4678 / 4680 | 4674 | 4683 | 4684 | 4685 / 4690 |
| 2/B | 4641 / 4642 | 4655 / 4657 | 4651 | 4663 | 4665 | 4666 / 4689 |

Mode 2 records A’s request/defer at rows 4636/4637, accepted source unlock at 4638 and child UNWIND_PARENT at 4644. Export is followed by unwind/notification rows 4645/4646. The original A owner handles at 4660, current-state return is 4661 and root completion is 4664. Its physical callback completes at 4680, with final source-user drop/retirement at 4683/4684 and SLOT_FREE at 4690. These rows distinguish source completion, the retained owner’s physical duty and final retirement.

The host coordinator reported zero pending keys before shutdown. The exact shutdown claim had zero facts and the settlement count is **0**. The [durable archive](runtime/shutdown-archive.json) still contains its cumulative context and snapshot. Its SHA256 is `c46f19e0e4a804cf1e5a5ff7a5a84627db17cab019aa32a51f8921809299d7ea`.

Both the runner and final controller require successful native-hold drain, actual final wire operations 9/10/11/6, ordinary destruction and unload. [Per-run controller state](controller/result.json) contains its actual post-run idle snapshot. The separately captured [combined poststate](context/combined-live-poststate.json) follows both runs on the same kernel4 boot at taint 12288 with both modules/devices/workers absent. The later [normal return](../return-normal4-db7-20261111/README.md) has a separate identity record.

The first saved-record audit returned 1 when its final metadata read requested an absent `runtime/poststate.json`. Its [original source and failed attempt](audit/initial/) are retained. The [corrected audit](audit/verified/) reads the already captured combined poststate and per-controller idle/identity fields, then returns 0. The [source diff](audit/metadata-correction.diff) changes that metadata binding and adds the explicit input path. Its event, release and wire checks retain their earlier form. These source-host inspections execute no kernel/source body.

The scope is protected source lock/unlock episodes and their concrete native/JIT transitions. Full native C function epilogues, general scheduling/progress, arbitrary affinities/oversubscription, complete auxiliary IRQ/unwind/stack bounds and broader API/configuration lanes require separate evidence. The trusted-source and AS01 flags/SIMD assumptions remain in force. Normal mitigation flags are preserved; complete mitigation coverage of generated/handwritten returns remains a limitation. This fixture supplies no real-world syscall workload or performance result.

[copy-index.json](copy-index.json) inventories 274 exact-byte copies. [remote-index.json](remote-index.json) selects 253 guest records, 10,650,745 bytes, from the original verified 508-file, 26,092,327-byte collection. The complete original index and copy verification remain under `collection/`. `SHA256SUMS` covers all stored files except itself. Actual GNU `image.o` files are retained. Raw whitespace diagnostics are listed in `whitespace-exceptions.txt`; retain those bytes when committing.
