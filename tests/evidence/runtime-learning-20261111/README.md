# Ordinary JMP learning and reached mutex scopes, 2026-11-11

Live4 returned **0** with status `partial_jit_mechanism_pass`. Eight successful
generated entries returned ordinary indirect-JMP facts. All eight exact facts
were merged, included in actual emitted/published candidates and coverage-ACKed.
They describe three unique source/target pairs. Generated execution reached
source points before optional B acquisition, under B, and after A's logical
unlock while B remained open. **A complete protected JIT-body return remains
`not_established`.** No physical role/chain trace or universal progress result
is inferred from these source points.

The [controller result](controller/result.json) records 2026-11-10
18:37:08.322039–18:37:10.325931 UTC (November 11 local date), elapsed
2.002745587000007 seconds. This is correctness-run elapsed time, not lock
performance. The observer records `RETURNED`, not timeout/drain. The actual
[runner result](output/result.json), [command](controller/command.json),
[source export](output/source-export.bin), [source metadata](output/source-metadata.json),
[static correlation](correlation.json) and complete raw wire history are retained.

## Exact source and execution identity

The fixture/runner source is `9f3279524b41c37fec5e0f29e1fd40975e2b8421`, with
the common compiler unchanged from `18c8f2e4`. The 106-file frozen input is
`/mnt/kdlock-builds/kdlock-main-work/module3-9f327952-01a1bc4f/input`.
Its [separate build record](../module3-build-20261111/README.md) retains the exact
source manifest/archive and normal compiler flags. Module SHA256 is
`bbd3ba41a3c4d4a68efbf24843b291ede0a38ef9223a24e421fe978a94635048`.
The actual [fixture](source/tests/kernel/payload/runtime_fixture.c.txt),
[runner](source/tests/kernel/run_runtime_fixture.py.txt),
[private ABI](source/include/kd_regs.h.txt) and
[emission-receipt types](source/kernel/feedback_publish.h.txt) are copied from
that exact Git revision. Source operations remain ordinary mutex API calls;
there is no named-thunk model or mitigation override.

The running kernel is `7.0.0-38-kdrebuild2`, core correction `81feb2d7`, BuildID
`fd2262c047e130787ef669419111eba6eb9ebb2c`. Actual ELF SHA256 is
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809`, config
SHA256 `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
This run used boot `0f3f9c09-8837-4763-8320-388278bd83d7`, initially taint 0,
following [separate boot4 proof](../kernel-repeatboot4-20261111/README.md).
The supplied full linked GS input is `0xffffffff8440f018`; tracer was `nop`.
Immutable-text and task-owned auxiliary-stack contracts remain admitted inputs,
not a general instruction-equivalence or stack-context proof.

## Actual dependency bytes and source scopes

SOURCE exported one 4,096-byte module-owned ITS page at
`0xffffffffc09e8000`, the 116-byte helper at `0xffffffffc09ea010`, and the
865-byte body at `0xffffffffc09ea0a0`: **5,077 bytes total**. Explicit limits
were 4 dependency pages and 262,144 source bytes. Actual dependency bytes and
disassembly are retained as [source-0.bin](output/source-0.bin) and
[source-0.disassembly.txt](output/source-0.disassembly.txt).

Each reached dependency site contains ordinary bytes `ff e0` (`JMP RAX`), with
following `cc` padding. Every observed target was the helper entry
`0xffffffffc09ea010`. The three sites each have a unique actual direct source
CALL, independently checked using its signed E8 displacement:

| Logical source point | Actual source CALL | Return word | Actual JMP | Facts / producing image |
| --- | --- | --- | --- | --- |
| A open, before optional B | `0xffffffffc09ea14b` | `0xffffffffc09ea150` | `0xffffffffc09e8020` | 4 / image 1 |
| A and B open | `0xffffffffc09ea1c8` | `0xffffffffc09ea1cd` | `0xffffffffc09e8023` | 2 / image 2 |
| After logical A unlock, B open | `0xffffffffc09ea29b` | `0xffffffffc09ea2a0` | `0xffffffffc09e8026` | 2 / image 3 |

The actual [body disassembly](output/source-2.disassembly.txt) and fixture source
establish the scope order. Before optional B, mode 0 proceeds to A unlock at
`0xffffffffc09ea210`, while modes 1/2 acquire B at `0xffffffffc09ea184`.
After the under-B CALL, mode 1 proceeds to B unlock at `0xffffffffc09ea1ef`;
mode 2 instead reaches A unlock at `0xffffffffc09ea25a`, the third CALL, then B
unlock at `0xffffffffc09ea2bb`. These alternatives are explicit in the
correlation; no single following operation is assigned to every under-B fact.

All eight records have `entry_result=0`, `KD_JIT_EXIT_COVERAGE_MISS` (3),
`KD_JIT_DETAIL_UNRESOLVED_TARGET` (10), and `KD_JIT_PHASE_JUMP_RESOLVED` (4).
They are classified ordinary and retain observation kind `jump`, exact epoch,
record identity and incarnation. The actual target has already been evaluated;
the phase does not stage another CALL word or replay its earlier effects.

This is evidence of generated execution at nested and outer-unlock source
prefixes. It does not independently identify the physical combiner, local/proxy
winner for each node, notification timing or exact physical release instant.
The source-operation markers alone are not a per-node authority trace. The
stronger statement that a full recursive JIT episode returned is not made.

## Actual emission, replacement and acknowledgment

Every candidate was actually built and published; every raw COMMITTED/ACK
receipt is retained in its cycle and in the complete wire log:

| Cycle | Claimed facts | Coverage ACK keys | Cumulative emitted JMP pairs |
| --- | --- | --- | --- |
| 1 | 0 | 0 | 0 |
| 2 | 2 | 2 | 1 |
| 3 | 4 | 4 | 2 |
| 4 | 2 | 2 | 3 |

The initial old image was NULL. Each later COMMITTED receipt names the exact
prior image as expected/actually returned old image. Included and acknowledged
record/incarnation sets match each exact claim, and the three later sets are
disjoint: **8 total ACKed facts, 3 unique JMP pairs**. The runner retains separate
observed, merged, candidate-input, emitted, published-input and ACK key sets;
all eight exact keys reach all stages. Publication and ACK are distinct actual
operations, not the construction receipt's `runtime_ack=false` flag.

Each [cycle](output/cycle-4/manifest.json) retains original assembly, C metadata,
manifest and GNU intermediate assembly/object/ELF/machine bytes. All actual
STAGE requests retain all five transmitted blobs, including flat metadata.
Static correlation matches the first four blobs to those saved artifacts, checks
the actual flat-metadata typed JMP dispatch outcomes, and verifies each ELF's
`.text` equals its staged machine image with entry at text base. No new assemble
or execution was performed to make these correlations.

Image 2 emits the first learned pair, image 3 emits the first two, and image 4
emits all three. The facts for the third site were produced by image 3; **no later
generated record proves execution of image 4's newly learned third dispatch**.
Emission/publication/ACK of that pair must not be reported as such execution.

## Completed effects, archive and retirement

| Case | Workers × iterations | Completed | Helper calls | A effects | B effects |
| --- | --- | --- | --- | --- | --- |
| native-local | 1 × 8 | 8 | 8 | 8 | 0 |
| contended-local | 4 × 8 | 32 | 32 | 32 | 0 |
| jit-while-pending | 4 × 4 | 16 | 32 | 16 | 16 |
| nested | 4 × 8 | 32 | 64 | 32 | 32 |
| out-of-order | 4 × 8 | 32 | 96 | 32 | 64 |

All cases record errors/core_errors/origin_errors 0 and locks_clear 1. Helper
CALL effects are 1/2/3 per body in modes 0/1/2. These counters support once-only
effects for the observed fixture; they are not an execution distribution or a
general progress result. Managed fork/exit also passed with distinct child own
state, unchanged parent state, successful child exit and explicit parent detach.

There were zero pending facts before shutdown. Actual wire sequence 26 SHUTDOWN,
27 archive claim, 28 SETTLE and 29 END all returned status 0, with their raw
requests, returned envelopes and replies retained in attempts 27–30. The zero-fact
[durable archive](output/shutdown-archive.json) has SHA256
`25512da1296248f09ffefdb2fbf975d756dbf970c43200c488b234c6b383239d`;
the exact content identity is in SETTLE's request. Settlement count is 0, distinct
from the eight earlier coverage ACKs. Ordinary destroy and normal rmmod completed.

The [separate read-only post-state](diagnostic/read-only-post-state.json),
captured at 18:44:29 UTC before any later default-kernel return, confirms the
same boot/release, module and both devices absent, taint 12288 without WARN,
no fixture/build/test activity, unchanged 106 source files and module hash.
It retains full dmesg and actual GRUB environment/default: `next_entry` empty,
normal default `7.0.0-38-kdlock1`. This timestamp is not a later-boot identity.

## Retention and limits

All 30 wire attempts completed successfully. Their cumulative worst-case log
reservation was 66,127,410 bytes under the explicit 134,217,728-byte limit.
[copied-files.json](copied-files.json) and the independently read
[VM index](vm-copy-index.json) bind all 214 raw VM files (3,383,744 bytes), plus
source/helper/diagnostic copies. `SHA256SUMS` covers every retained file except
itself. Raw tool output whitespace remains unchanged.

This collection performed static saved-record/ELF inspection only: no project
compiler import, build, test, code execution or guest control mutation. Earlier
[live3 prefix limits](../runtime-jit-prefix-20261111/README.md) remain historical.
No whole protected JIT-body return, physical batch-length measurement, universal
progress, performance gain, whole-kernel replacement or real-world syscall/API
workload acceptance is established by this mechanism fixture.
