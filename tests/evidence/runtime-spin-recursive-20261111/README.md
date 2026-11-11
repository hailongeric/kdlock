# Plain spin recursive mechanism evidence — 2026-11-11 UTC

The actual controller and runner returned **0** with `protected_spin_jit_recursive_mechanism_pass`. The independently run saved-record auditor also returned **0**. The controller observer recorded 4.222853 seconds. This is kernel mechanism evidence from the ordinary `kd_spin_lock/kd_spin_unlock` pair.

The run used fixture source `db7d7d6e38e1341e24b643553bd83633616d4ea7`, kernel core `2d0ad60b0bc46929f3070aefa364e710c0a81115` and `7.0.0-38-kdrebuild4`, BuildID `f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053`. Boot was `1b3b298f-051b-42ea-a53b-429c16f4e114`. The [module-build record](source/module-build-result.json) binds all 103 frozen files, 67 kernel inputs and six actual kernel-output hashes. The [module source record](../module-spin-db7-build-20261111/README.md) preserves both module builds and the [shared private include](../module-spin-db7-build-20261111/source/fixture/tests/kernel/payload/runtime_fixture_observe.inc).

The actual module SHA256 is `79521d2ec8f87b5750c7ac2dc7f4e4fff2959d39928d30db1736985569642e1f`. [Source state](source/state.json), [complete manifest](source/manifest.json), [fixture manifest](source/fixture-inputs.json), [reviewed controller](source/fixture-controller.py) and [actual argv](controller/dispatched-argv.json) are retained. Kernel build and the fresh boot have separate [build](../kernel-build4-20261111/README.md) and [repeat-boot](../kernel-repeatboot4-db7-20261111/README.md) records.

The five ordinary scene roles ran on CPUs 0–4, with userspace control on CPU 5. The actual controller started on the fresh taint-zero boot. Native checks covered local acquisition, two live spin grants with out-of-order unlock, contended handback and the original task/CPU/preemption/IRQ state. The finite holder wait was 10,000ms. The two recursive warm scenes both returned root/child outcome 3 after pinned generated execution.

Actual source export contained **4 regions and 5,115 bytes**. The caller supplied the ELF symbol extent at `0xffffffff8271be20`, length 2, bytes `c3 cc`. [The retained ELF span](runtime/builtin-source-elf.bin) has SHA256 `56de62c1837575efee31915828000fde2932e3c34c06b498f648ecaf6bae8d7c`. Actual SOURCE bytes matched that executable ELF span before compilation. The ordinary source-byte decoder/backend consumed it with the existing CALL/RET handling. The [earlier omitted-span failure](../runtime-spin-frontier-20261111/README.md) and [ordinary recovery](../runtime-spin-recovery-20261111/README.md) retain their own records.

The four images retain private image ABI version 1, a 168-byte canonical register backing and a 56-byte IO record. The full linked `current_task` GS input is `0xffffffff8440f018`. Per-cycle source, assembly, C metadata, linked images, machine bytes, actual GNU objects, COMMITTED receipts and ACK replies remain under `runtime/cycle-*`. Raw source export and its address/length metadata are retained with the actual wire frames.

All **32 wire attempts** completed with status 0. Four actual publications ACKed `0 / 1 / 2 / 1` exact facts, totaling **4**. A later empty claim ended without another publication. Every included fact is joined to its actual producer, source version, candidate, emitted input, COMMITTED old/new image identities and exact ACK subset by the [saved proof](audit/verified/proof/proof.json). The fixed warm image was `0xff11000107091938`.

[Raw observation history](runtime/observations-final.bin) contains ABI1, 20 words per row, capacity 65,536, **5,190 rows and zero overflow**. Row IDs below are zero-based positions in that immutable prefix. The proof carries exact state, task, object and acquisition identities. Each scene uses its own reserve/free interval to distinguish reused addresses. The auditor found 1 positive warm-plain proxy lifetime.

| Warm mode | A/B proxy selections | Child JIT entry | Child completion row | Current-state return row | Parent reentry row | Root completion row |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4869 / 4888 | 4896 | 4905 | 4909 | 4914 | 4932 |
| 2 | 4995 / 5015 | 5023 | 5041 | 5045 | Root already closed | 5050 |

| Warm mode | Canonical S_W | Root A / child B requests | C_A / C_B physical tasks |
| --- | --- | --- | --- |
| 1 | `0xff1100010c7da800` | `0xff11000127500068` / `0xff110001275004c0` | `0xff1100034b7e3180` / `0xff11000344853180` |
| 2 | `0xff1100010c7da800` | `0xff11000127500068` / `0xff110001275004c0` | `0xff110003488a0000` / `0xff1100034719b180` |

Physical callbacks and final retirement have separate rows. The callback rows name the retained physical owner and its exact callback. RELEASE_RETIRE has zero source/return/notifier users. NODE_RETIRE_READY precedes the final retirable publication, and SLOT_FREE records acquired retirable state, empty pool users and idle components. The table establishes final retirement eligibility. Subsequent storage reuse is outside this record.

| Mode/request | Request / owner handled | Physical callback begin/end | Control stopped | Source user dropped | Release retired | Node ready / slot free |
| --- | --- | --- | --- | --- | --- | --- |
| 1/A | 4918 / 4919 | 4920 / 4924 | 4933 | 4930 | 4941 | 4944 / 4952 |
| 1/B | 4898 / 4899 | 4900 / 4902 | 4906 | 4904 | 4939 | 4942 / 4949 |
| 2/A | 5025 / 5026 | 5027 / 5029 | 5052 | 5031 | 5059 | 5061 / 5075 |
| 2/B | 5034 / 5035 | 5036 / 5038 | 5042 | 5040 | 5055 | 5058 / 5072 |

In mode 2, C_B requests outer A at row 5025. Its original owner C_A handles the request at 5026 and finishes the physical callback at 5029. The accepted source unlock is row 5030, followed by pinned child JIT reentry at 5032. The release has no deferred/unwind marker. C_A and C_B later rejoin their own still-pending local requests; the saved queue joins distinguish those requests from W’s physical turns.

The separate native-miss case selects W at row 5136, enters generated code at 5153, exits at the exact direct CALL with CALL_STAGED at 5158 and forwards at 5159. The original W reaches the checkpoint once with A’s native pin active. Physical ACK ends at 5166 before the native unlock row 5167. Native nesting records 48 pin samples. The raw miss remains in the durable archive and has one exact SETTLED key, with no coverage ACK for that miss.

The host coordinator knew zero pending keys immediately before shutdown. Shutdown then claimed the newly recorded native-miss fact, so the actual archive settlement count is **1**. The [447,348-byte archive](runtime/shutdown-archive.json) has SHA256 `a4762e7621299fdd615a12af19934f41971c0ea4c726d34731d412d157daacd1`.

Both the runner and final controller require successful native-hold drain, actual final wire operations 9/10/11/6, ordinary destruction and unload. [Per-run controller state](controller/result.json) contains its actual post-run idle snapshot. The separately captured [combined poststate](context/combined-live-poststate.json) follows both runs on the same kernel4 boot at taint 12288 with both modules/devices/workers absent. The later [normal return](../return-normal4-db7-20261111/README.md) has a separate identity record.

The first saved-record audit returned 1 when its final metadata read requested an absent `runtime/poststate.json`. Its [original source and failed attempt](audit/initial/) are retained. The [corrected audit](audit/verified/) reads the already captured combined poststate and per-controller idle/identity fields, then returns 0. The [source diff](audit/metadata-correction.diff) changes that metadata binding and adds the explicit input path. Its event, release and wire checks retain their earlier form. These source-host inspections execute no kernel/source body.

The scope is protected source lock/unlock episodes and their concrete native/JIT transitions. Full native C function epilogues, general scheduling/progress, arbitrary affinities/oversubscription, complete auxiliary IRQ/unwind/stack bounds and broader API/configuration lanes require separate evidence. The trusted-source and AS01 flags/SIMD assumptions remain in force. Normal mitigation flags are preserved; complete mitigation coverage of generated/handwritten returns remains a limitation. This fixture supplies no real-world syscall workload or performance result.

[copy-index.json](copy-index.json) inventories 276 exact-byte copies. [remote-index.json](remote-index.json) selects 255 guest records, 15,597,348 bytes, from the original verified 508-file, 26,092,327-byte collection. The complete original index and copy verification remain under `collection/`. `SHA256SUMS` covers all stored files except itself. Actual GNU `image.o` files are retained. Raw whitespace diagnostics are listed in `whitespace-exceptions.txt`; retain those bytes when committing.
