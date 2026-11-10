# Returned JIT prefix and native completion, 2026-11-11

The actual live3 runner returned **0**, with status
`partial_jit_mechanism_pass`. It recorded eight successful generated entries
returning the same typed source frontier, and all five fixture cases completed
with their expected effects. This establishes execution of a generated prefix
and continuation on the original task. It does not establish a complete
protected JIT body, recursive JIT execution or ordinary indirect-target learning.

The [controller result](controller/result.json) records 2026-11-10
18:04:52.369365–18:04:54.372199 UTC (November 11 local date), elapsed
2.001764116000004 seconds. This is correctness-run elapsed time, not a performance
measurement. The observer records `RETURNED`, with no timeout/drain inference.
The [runner result](output/result.json), earlier incomplete
[identity](output/identity.json), exact [command](controller/command.json) and
[controller source](sourcehost/kdlock-main-live3-controller.py.txt) are retained.

## Exact source, module and boot

The host compiler/runner is committed source
`18c8f2e499d5fb74972e92bad5748489b921035d`, from the same 106-file immutable
input recorded by the [separate focused checks](../multi-entry-pipeline-20261111/README.md).
Its VM path is
`/mnt/kdlock-builds/kdlock-main-work/focused3-18c8f2e4-01a1bc4f/input`.
The module is the unchanged actual kernel2 fixture, SHA256
`378bf139407bf57de1b4d708db3c6548a5d25537219b8ce83c2232c89010267e`, built from
the retained `2cc70fce` source input. Its normal compiler flags were preserved;
no branch-mitigation override or handwritten source CALL adapter was added.

The running kernel is `7.0.0-38-kdrebuild2`, including cold-allocation correction
`81feb2d749ebbca468c0ab2eb895dcdd82fe519e`, BuildID
`fd2262c047e130787ef669419111eba6eb9ebb2c`. The actual kernel ELF SHA256 is
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809`, config
SHA256 `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
The [repeat-boot proof](../kernel-repeatboot-20261111/README.md) is separate:
this attempt used boot `fb0601dd-db5c-4396-aaa5-e59b91b16924`, initially taint 0.
The actual full linked GS input is `0xffffffff8440f018`, with `nokaslr` and the
recorded tracer `nop`. Immutable-text and auxiliary-stack contracts were explicit
admission inputs; these declarations do not prove general instruction equivalence.

Exact frozen [runner](source/tests/kernel/run_runtime_fixture.py.txt),
[fixture](source/tests/kernel/payload/runtime_fixture.c.txt) and
[private ABI header](source/include/kd_regs.h.txt) are copied with their Git
identities. The full ordinary source body and helper remain ordinary C using
the actual mutex API. These fixture controls are mechanism evidence, not a
real-world application or syscall-path substitute.

## Completed effects and their scope

| Case | Workers × iterations | Completed | Helper calls | A effects | B effects |
| --- | --- | --- | --- | --- | --- |
| native-local | 1 × 8 | 8 | 8 | 8 | 0 |
| contended-local | 4 × 8 | 32 | 32 | 32 | 0 |
| jit-while-pending | 4 × 4 | 16 | 16 | 16 | 16 |
| nested | 4 × 8 | 32 | 32 | 32 | 32 |
| out-of-order | 4 × 8 | 32 | 32 | 32 | 64 |

Every case records errors, core_errors and origin_errors 0, and locks_clear 1.
The protected counters/helper calls support once-only effects across the observed
prefix and native continuation. The records do not assign every generated exit
to an individual case. In particular, successful nested/out-of-order body
completion must not be counted as proof that their inner operations ran in JIT.

The managed fork/exit case also completed: actual child PID 3278 has distinct
own-core/native-binding identities, child wait status 0, unchanged exact parent
identities, and a detached parent afterward. No packet contents were copied.
The later successful shutdown records that native holds drained; child identity
alone is not the drain proof.

## Exact executed frontier

All eight unique retained records have `entry_result=0` and the same exit:

| Field | Actual value |
| --- | --- |
| kind | `KD_JIT_EXIT_COVERAGE_MISS` (3) |
| detail | `KD_JIT_DETAIL_SOURCE_UNAVAILABLE` (1) |
| phase | `KD_JIT_PHASE_CALL_STAGED` (2) |
| source IP | `0xffffffffc09ea14b` |
| target and cursor | `0xffffffffc09e8020` |

The actual source bytes are the direct near CALL `e8 d0 de ff ff`; its source
return address is `0xffffffffc09ea150`. The two supplied regions are the
116-byte helper at `0xffffffffc09ea010` and 833-byte body at
`0xffffffffc09ea0a0`. The actual target lies outside both. The ordinary compiler
route references `__x86_indirect_thunk_rax` in the module's retained disassembly;
this record does not invent a decoded body or helper model for that external
target. No near indirect CALL is present in the supplied source records.

[The emitted assembly](output/cycle-1/image.S) at
`.Lkd_src_ffffffffc09ea14b` writes the actual return word, then dispatches the
retained target to `.Lkd_exit_20`. That exit exports the exact site, target and
CALL_STAGED phase above. The native route therefore continues after the already
staged CALL effect. [Static correlation](correlation.json) matches all eight
records to that archived producer, emitted exit and actual committed image.

This frontier precedes the inner B lock CALL at `0xffffffffc09ea184`.
**No recorded generated execution reaches inner B.** The later source suffix
and helper complete on the original task. `returned_full_jit_body` remains
`not_established`, and `ordinary_indirect_kernel_learning` remains `unverified`.
No physical batch length, recursive JIT success, broad instruction equivalence,
performance gain or complete acceptance matrix is established.

## Publication, pending records and exact archive

There was one actual publication from an empty old slot. The initial claim has
zero rows; its [COMMITTED receipt](output/cycle-1/commit.bin) and
[ACK receipt](output/cycle-1/ack.bin) include/acknowledge zero facts. The later
three cycles publish no replacement and retain claims of 2, 6 and 8 rows.
Those are overlapping snapshots of pending facts, not 16 additional exits.

All eight facts are `unclassified`, with disposition
`direct_call_has_no_indirect_observation` and merge
`feedback_has_no_compiler_observation`. The construction receipt has no emitted
observations, and no fact receives coverage ACK. Source CALL type and actual
target are preserved rather than relabelled as indirect learning.

All eight pending keys are present in the exact
[shutdown archive](output/shutdown-archive.json), SHA256
`baa3f0b36ccca44274329e91f60fbc91f75c6d4877c57b5f0ffc1fb0c751f56b`.
The completed runner records `settled_keys=8`, through the ordinary
SHUTDOWN → archival claim → durable file/directory fsync → SETTLE → END sequence.
Settlement is separate from coverage ACK. The archive embeds the actual raw
archival claim; the other [raw claim snapshots](output/cycle-4/claim.bin) are
retained separately. Raw SHUTDOWN, SETTLE and END replies were not separately
saved by this runner; its exact reply checks are visible in the retained source
and its successful completed result.

The retained artifacts include original assembly, C metadata, manifest, GNU
preprocessed assembly, linker script, object, ELF and 14,504-byte extracted
machine image. Machine SHA256 is
`71b97c4aa181028c5a3d77e31e9943e1dc6c78b24d8c92cdd3246ab468c4e21e`.
Static ELF inspection confirms that its `.text` bytes equal the saved machine
image and entry equals text base `0xffffffffc0e00000`. The saved producer's
construction assembly exactly equals `image.S`. A separate flat-metadata blob
was not saved and is not reconstructed as a new runtime receipt here.

## Cleanup and copy integrity

The runner's normal channel close, destroy and rmmod completed before return 0.
A separately timestamped [read-only post-state](diagnostic/read-only-post-state.json)
confirms the same boot/release, module absent, both device nodes absent and
taint 12288 (out-of-tree/unsigned module bits, without WARN). It retains actual
activity, full dmesg and their hashes; unrelated AppArmor diagnostics are retained.
The check neither unloads anything nor infers drain from a timeout.

[copied-files.json](copied-files.json) binds every raw receipt/artifact/source
copy to its original path, size and SHA256. All 29 VM files (888,111 bytes)
matched the independently read [VM index](vm-copy-index.json). `SHA256SUMS`
covers all retained files except itself. The correlation is static saved-record
inspection, not another execution run. This collection performed no project
compiler import, build, test, generated-code execution or guest control mutation.
Git reports trailing whitespace in the raw module objdump output; its bytes and
hash remain unchanged. All other retained files pass the whitespace check.
