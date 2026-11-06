# Five-level mmap1 learning: partial-image results

Both models completed and drained at one and eight workers, once per point.
The mmap entry still published no image. Munmap published generations 1 and 2,
but its eight-worker applications each had eight JIT entries followed by eight
permanent handbacks and zero ordinary delegated returns. These are unscored
learning observations, not complete MM delegation or performance acceptance.
No merge or performance gain is claimed.

Tested source: `bee6e2b22c6b08ea7e55cc281ca197aa1c7ee3be`, branch
`codex/mmap-reached-jit`. `5c14cdd9` documented the call/publication design;
`d5ec4eee78d764e7f706ff5a850059bf809af779` implemented it. Fixture-only
corrections ended at `1f847d5b2062ab6a286922d1f129cca4ea156438`.
`32bce9d6` documented the two observed decoder gaps before `bee6e2b2` fixed
them. Separate child images for selected KD acquisitions remain unimplemented.

## Actual results

Units are mmap/munmap pairs per nominal second. Each application used six
upstream warmup samples and two nominal measured seconds. One one-worker
application primed fresh histories in each model; one eight-worker application
followed. Observation counters were enabled. Every application passed and
drained, with `scored=false`; both sessions retired exactly.

| Model | Workers | Preserved Native | Candidate | Difference |
| --- | ---: | ---: | ---: | ---: |
| threads | 1 | 281886.5 | 187061.0 | -33.64% |
| threads | 8 | 225144.5 | 50447.0 | -77.59% |
| processes | 1 | 354007.5 | 221110.0 | -37.54% |
| processes | 8 | 1692926.0 | 397627.0 | -76.51% |

Native controls are the matched experimental kernel with `kd_mmap=off` from
[the preserved comparison](../mmap1-scaling-f9fdaa2a/README.md#native-results).
They were not rerun. Changing images, concurrent compilation and observation
overhead remain separate from Native and earlier fixed-image conditions. One
observation gives no repeat variance. No Nano/TCLock or cross-NUMA comparison
was run, and no regression gate was passed.

| Eight-worker scope | Entry | Selected | Local / no image | Submitted / bound / JIT entered | Handback / finished | Delegated return |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| threads | mmap | 406059 | 406059 | 0 | 0 | 0 |
| threads | munmap | 406054 | 406046 | 8 | 8 | 0 |
| processes | mmap | 3178322 | 3178322 | 0 | 0 | 0 |
| processes | munmap | 3178316 | 3178308 | 8 | 8 | 0 |

These counts include warmup and match task name plus entry, not per-edge TID
traces. All selected one-worker acquisitions were local, with zero submissions.
Cancellation and invalid-clock counts were zero. The counter and terminal
conservation checks passed. There is no complete delegated downgrade/read-tail
proof, measured physical batch length, dynamic instruction count, full
critical-section hold time or critical-section ratio.

## Why mmap published no image

Both sessions ended with `0xffffffff817b6f68` at generation 0 / NativeOnly.
The exact compiler reason is:

`retained-service scope needs unsupported instruction services`

The emitting condition is in `disassem/disassem.py:845`: retained services
cannot currently be combined with the older instruction-service/terminal
marker mechanism. Source logic implies `service_queue_required=true` and
`has_escapes=true`. `root_escapes=false` by definition for this mutex/ABI2
backend. The exact `origin_sites` count and legacy instruction sites were
not logged. These boolean conclusions are control-flow inference, not captured
variable values. They do not identify a particular opcode.

The reported `0xffffffff81213636` is the last coverage diagnostic location,
retained through this later aggregate refusal. The matched ELF places it at
`check_panic_on_warn.cold`, beginning with ordinary register moves and a CALL.
It is not proof that this address, that function or its CALL caused the guard.
No claim about a dynamically reached legacy instruction is justified.

This is not source-budget, image-capacity or return-graph exhaustion. The
reported mmap graph had 823296 cached bytes, 62760 decoded source bytes, 15924
instructions, zero incomplete blocks and 15 decode passes. The 1-MiB aggregate,
33-pass/32-transition limits and ordinary return-flow check were retained.

The separately fixed RDPKRU/CLAC forms use `SOURCE_FRONTIER`, not the older
`native_escape.INSTRUCTIONS` directory; they do not explain this remaining
aggregate rejection. The compatibility guard was not relaxed.

## Munmap's confirmed continuation boundary

Both retained munmap histories contain exactly one IJ pair and no ordinary
callee-table addition:

`0xffffffff814f4a38 0xffffffffc0e32bf0`

The matched kernel ELF and saved generation-1 JIT source establish the source
CALL at `0xffffffff814f4a33` in `kd_mmap_assert_held_write`. The live decoded
form in that saved source is `CALL RDX`; its five-byte source continuation is
`0xffffffff814f4a38`. The provider callback is loaded from offset `0xc8`.
The provider layout and initializer identify this slot as `assert_held_write`
(`include/kd_rwsem_provider.h`, `kernel_module/kd_rwsem_provider.c:254`). The
module target address is retained exactly; no symbol mapping from another
module instance is substituted.

Generation 1 had no allowed target at `ij_ffffffff814f4a38`. Its generated code
had already pushed the real return word `0xffffffff814f4a38` on the source
stack, selected the target in R14, then exported the packet with source CALL
PC `0xffffffff814f4a33` and exit 11. `kd_jit_retained_miss()` validates the
word against CALL-PC plus instruction length and records the IJ pair before
the existing Native handback. The callee at `0xffffffffc0e32bf0` is the first
unexecuted position. The waiter starts there; it must not redo the CALL push.
Its later native RET consumes the saved word once.

This confirmed miss is **not a completed RET pop**. The retained RET/JMP-miss
path uses exit 15; the saved generation-1 image uses exit 11 at this source.
Both models' generation-1 image source has SHA-256
`bdb37384c3f1c6d0abd4cb8054d80f8b0aa830c18f937f69177308a0dd382e8f`.
The receipt hashes and selected source excerpts are retained with the histories.

The history is unique-edge evidence, not an event count. It confirms a miss
at this boundary in each session and explains generation 1 → 2 learning, but
cannot assign that reason individually to all eight handbacks. Handback reasons
and source-frontier hits were not separately counted. In particular, RDPKRU
and CLAC runtime hits are **unmeasured**, not established as zero.

## Changes, configuration and limits

Direct CALL lookahead counts the acquisition entry as depth zero and follows
five edges, using minimum depth for shared functions. Reached history targets
are additional depth-zero decoder seeds within the same region. This does not
limit API nesting or recursive runtime stack depth. Callee expansion runs after
the existing critical-section selection. Lexically matched releases cut caller
paths; where decoded blocks cannot identify the held object, exact runtime
records delimit execution. This is not a new proof of per-lock static image
boundaries for every nesting case. The original backend, GS handling, 8-KiB lookahead, 4-KiB
alignment, 1-MiB source cache, 256-KiB reads and ordinary work limits remain.

New images can publish during learning. Immutable old images remain resident;
captured frames continue using their bound generation. Publication and stale
miss reports retain the existing shared generation guard. Source/status races
can select a complete old/new image or no eligible image, without changing an
already captured frame. No new ownership, queue or frame ABI was introduced.

Compiler work overlapped the two application lifetimes in each model (roughly
7.9 seconds per overlap). This is compiler overlap, not proof that publication
or replacement overlapped an executing frame. Publication timestamps were not
collected. Strict fixed-image scoring checks remain separate and were not run.

The first candidate encountered undecodable live forms at
`0xffffffff813b1b67` (`0f 01 ee`, RDPKRU) and `0xffffffff81dbceb2`
(`0f 01 ca`, CLAC). A maintained leased read confirmed them; static ELF NOPs
at the latter location had been replaced by kernel alternatives. The first
candidate's threads rates 190216.5 / 50785.5 passed and drained but were entirely
local. Its generation-zero refusals and readiness failure remain retained.

`bee6e2b2` extends only the existing exact first-unexecuted source marker for
those two observed forms. Revision 19 negotiates the additions; revision 18
retains its original five-byte form. If reached, the instruction runs on the
original task after exact leased-byte validation, full packet export and the
existing ACCEPT/final ACK. Neither instruction is executed or emulated on the
executor. Static discovery alone is not runtime execution evidence.

Kernel: `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, lazy preemption,
boot `46b1110e-1365-4935-a916-a5cac76edd80`. Unchanged will-it-scale revision
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`, arguments `-t N -s 2 -m`.
The 64-vCPU/24-GiB VM has two 32-CPU NUMA nodes; requesters used CPUs 0–7,
collector 63 and existing executor pool 0–61. Host pins, 2-GHz/performance/
turbo-off settings and the existing recovery snapshot were verified. Each
model used fresh histories, its own source-bound receipts and one writer.

Focused evidence covers exact depth five/zero, outer and nested releases,
downgrade continuation, immutable capture/publication/stale reports, the two
new generated instruction boundaries with preceding effects/other branches,
and Native continuation write/downgrade/read joins with supplied task/physical
primitives. Only the necessary changed cases were repeated; both provider
builds passed. Test-only mock-reader, continuation-label and fixture-header
failures remain recorded. Unchanged earlier checks were reused by source
identity. This is not a full API/configuration or general MM correctness proof.

Both final sessions retired to `state=2, modules=0, frames=0, writers=0`, unloaded
normally and ended idle. Normal kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored on boot
`b563a4b2-19e6-4af7-862c-297c9bfa69bb`. Idle and empty `next_entry` were verified.
`analysis.json` and `retained-files.json` bind all positive/negative results,
histories, selected generated source, compiler records, identities and recovery.

## Minimal next cutoff assessment

The existing terminal C-call path can preserve the real CALL word and hand back
before a helper's first instruction. It is suitable if the exact required
helper is unconditionally an original-task operation on that reached branch.
It must not mark an ordinary helper wholly Native merely because a different
branch contains such an operation.

The present aggregate refusal does not identify the legacy instruction or its
enclosing CALL, so choosing that boundary now would be a guess. First retain
those exact selected-site details at the existing refusal. Then use an existing
terminal CALL boundary where justified, or the same precise terminal instruction
frontier when actually reached. Keep PAUSE/fences in ordinary faithful JIT
lowering. No broader returning instruction-service join, blanket terminal list
or compatibility-guard relaxation was implemented for these unproved branches.
