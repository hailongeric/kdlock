# Final munmap g7: possible native continuations

**The exact taken handback PC/reason was not retained.** The fixed application
recorded 336,037 munmap JIT entries, zero retained returns and 336,037 completed
native handbacks. Under the recorded image identity and exact runtime
invariants, its permanent handbacks narrow to a completed release/downgrade
with ownership still live, or a permanent source frontier. The records do not
select a particular instruction within those classes.

On the ordinary successful userspace munmap path, the clearest release candidate
is `kd_mmap_write_downgrade`: source CALL **`0xffffffff81818dd4`**, followed by
native continuation **`0xffffffff81818dd9`**. If reached, this runtime definitely
hands back after completing the downgrade because read custody remains live.
Earlier frontiers or inner releases can precede it, so this is a conditional
source-path result, not an observation that the fixed point took that exit.

This analysis uses only retained artifacts from the single `d421e7d5` normal
campaign recorded by `53889930`. It does not reuse the prior `40edde00` g6
diagnostic as runtime evidence. No workload, provider activity, probe, tracing,
targeted capture, build or test was started for this analysis.

## Exact image and source association

| Field | Value |
| --- | --- |
| Entry | `0xffffffff8181c73b`, `__vm_munmap+0xbb` |
| Registry | pid 0, tgid 2430, slot 443, ABI2, g7 NORMAL |
| Image pointer / requirements | `0xffa0000025174000` / `32640` (`0x7f80`) |
| Final workspace batch | 14; snapshot token 14, base g6, revision 6 |
| Image size / SHA-256 | 578,944 bytes / `458e5b036e2a19c8b364b52110e80167512d5972bf59e309832de699c852e267` |
| Assembly SHA-256 | `03b43a502a7445cf77398c0d63c24f7adfd3a3b1d95e19fcc22a536f452829f7` |
| Kernel Build ID | `357a7115d21941960b90262ac1165bf70d1b398e` |
| Kernel ELF SHA-256 | `1cd5fa2b6094903cd644b202967a9f7ad5ddce0fc29cef9d5b2b981fb2e5e216` |

The workspace final image and retained g7 epoch copies have matching hashes.
The continuation-02 kernel log ends with the 2,944-byte final install chunk at
offset 576,000 and status NORMAL; fixed-point registry/code/generation and
completed compiler records then remain unchanged. This associates the retained
generated image with the observed g7 entry. No kernel-side payload digest was
recorded. The separately retained `run/provenance/compile-7` and `upload-13`
directories belong to **mmap**, not munmap; they must not be substituted for a
munmap upload receipt.

The local v4 kernel ELF matches both the recorded SHA-256 and Build ID. Symbol
names/offsets below use that exact ELF. Five relevant kernel source files also
match the final run's baseline manifest; their hashes and image hashes are in
[image-identity.json](image-identity.json). The earlier unmap-review Maple source
and older context-capture System.map differ and were excluded.

## Complete emitted inventory

[exits.csv](exits.csv) and [exits.json](exits.json) inventory **all 2,908 emitted
branches to the wrapper exit labels**. These are static wrapper exits, including
resumable services; they are not 2,908 permanent handback instructions or proof
that any listed site executed. Each row gives the generated line, class, source
PC/symbol, continuation, condition and unit/root effect. JSON adds source CALL
references and known transfer tables.

| Static class | Count | Runtime interpretation |
| --- | ---: | --- |
| Block budget pause | 2,676 | `RUN_YIELD`; resume the same retained image, not terminal handback |
| Native callee/control stub | 77 | Returning instruction service resumes; a release ends its unit; an unregistered ordinary target can report a CALL miss |
| Original-CPU memory service | 61 | 55 constant GS-read guards cannot select service; six GS INC/DEC operations have exact resume labels |
| Retained RET/JMP miss table | 59 | An unmatched actual destination hands back and reports IJ learning |
| Source frontier | 28 | Permanent handback before the pending source instruction; no learning edge |
| Indirect CALL miss | 2 | Preserve real CALL word and report actual missing destination |
| Indirect tail miss | 2 | Preserve transfer/stack state and report missing destination |
| Entry/resume dispatch miss | 3 | Source RIP absent from the relevant dispatch set; not an ordinary release |

The 55 GS-read nonoverlap calculations are in
[gs-read-guards.csv](gs-read-guards.csv). All decoded offsets are disjoint from
the preempt-count interval `0xffffffff8440b030..33`; the six unconditional GS
INC/DEC source PCs are `81411ac9`, `81411b02`, `81411b19`, `81411b20`,
`818d7570`, `818d758d` (all with prefix `0xffffffff`). Successful memory service
resumes or completes all ownership; it has no independent ordinary terminal
handback result. A later absent successor would be a retained miss instead.

## All emitted release CALL sites

[release-calls.csv](release-calls.csv) gives all eleven source CALLs and their
generated line references. All addresses below have prefix `0xffffffff`.

| Operation / source function | CALL PC | Post-CALL PC | Condition and scope |
| --- | --- | --- | --- |
| `up_write`, `anon_vma_clone` | `81807954` | `81807959` | Its inner anon-vma writer release branch; remaining outer/native ownership selects whole-root native continuation |
| `up_write`, `vma_complete` | `8181779b` | `818177a0` | Conditional inner writer release; same ownership rule |
| `up_write`, `vma_complete` | `818177b2` | `818177b7` | Alternate inner writer release; same ownership rule |
| `up_write`, `userfaultfd_unmap_prep` | `81965456` | `8196545b` | Optional userfaultfd writer release path; same ownership rule |
| `kd_mmap_write_unlock_clobber_v1`, `do_vmi_munmap` | `8181a75e` | `8181a763` | Early/no-matching-VMA path; complete outer/all-owner release would count a retained return |
| `kd_mmap_write_unlock_clobber_v1`, `__vm_munmap` | `8181c869` | `8181c86e` | Error or `unlock=false`; complete outer/all-owner release would count a retained return |
| `kd_mmap_write_downgrade`, `vms_complete_munmap_vmas` | `81818dd4` | `81818dd9` | Ordinary success with `unlock=true`; if reached, live read custody forces whole-root native continuation after the CALL |
| `kd_mmap_read_unlock`, `vms_complete_munmap_vmas` | `81818daa` | `81818daf` | Read-tail release after downgrade; on the ordinary `unlock=true` path, the earlier downgrade has already handed back this root |
| `_raw_spin_unlock`, `vmalloc_dump_obj` | `81816c33` | `81816c38` | Conditional allocation diagnostic path; native owner record must match |
| `_raw_spin_unlock`, `vmalloc_dump_obj` | `81816c67` | `81816c6c` | Alternate diagnostic path; native owner record must match |
| `_raw_spin_unlock`, `mas_nomem` | `826c6b6a` | `826c6b6f` | Requires allocation failure, blocking GFP and internal tree locking; excluded for normal MM/detach trees |

The normal syscall passes `unlock=true` (`mm/mmap.c:1075`). The completion
routine downgrades before its read tail (`mm/vma.c:1319`, `1346`). Both generated
post-CALL labels `81818dd9` and `81818daf` are absent, but the release protocol
completes the CALL word and saves the real post-CALL PC before handing back;
absence of a generated successor does not itself cause a miss here.

A release is a **unit boundary**. With the current same-root-image protocol,
remaining KD or native ownership turns it into native continuation of the
retained root's remaining suffix. Complete outer/all-owner release instead
produces `RUN_TO_UNLOCK` and increments `returned`. Thus zero returns excludes
that complete-release outcome, not every outer release instruction regardless
of ownership state. No lock-state witness was collected.

Maple's internal unlock exclusion is specific: final g7 tests
`(tree->ma_flags & 0x300) != 0x300` before `mas_nomem+0x6a` can unlock. Hash-matched
`mm_types.h:1421` and `fork.c:1087` establish external locking for `mm->mm_mt`;
`mm/vma.c:1570` transfers that lock mask to the detach tree. The normal-tree
branch is therefore excluded by source semantics. This does not exclude the
whole `mas_nomem` function or the two distinct diagnostic spin-unlock sites.
See [maple-scope.md](maple-scope.md).

## Every permanent source frontier

[frontiers.json](frontiers.json) lists all 28 exact PCs and generated lines.
There are 23 diagnostic/report branch sites: six list-link validation sites,
six refcount diagnostic sites, one `__split_vma` diagnostic, five Maple
range/slot diagnostics, and five format/width/precision diagnostics. Four more
are in `dump_stack_lvl`, `vkdb_printf`, and two UBSAN handlers. These are
conditional branches, not evidence that diagnostics executed. Empty fixed-point
kernel output alone cannot exclude every previously reported or conditional
diagnostic path.

The remaining frontier is **STD at `0xffffffff826f0777`**,
`memmove`/`__memmove+0xb7` (`jit.S:144942`). Its generated path requires backward
overlap (`src < dst < src+len`), length at least `0x2a8`, and equal low address
bytes. Reaching it hands back before STD, preserving all earlier effects.
Its presence, the earlier learned Maple callee, and the all-handback counts do
not prove those runtime data conditions or that STD was reached.

Generated frontier comments omit the replaced instruction bytes. The exact
ELF matches STD, but its bytes at the other 27 PCs differ from the generated
runtime-frontier form. They are retained as `elf_bytes`, not claimed as the
leased live bytes. Runtime validation accepts only its explicit opcode set
(UD1, RDPKRU, CLAC, CLI, STI, CLD, STD); this static record cannot choose an
opcode at those 27 sites or infer their execution from an ELF CALL/NOP.

## What the learning history identifies

[learning-decoded.json](learning-decoded.json) decodes the retained binary
snapshots using the exact 128-byte header/40-byte record ABI. The cumulative
final CALL table contains four targets and the IJ table contains two pairs.

| Admitted generation | Incorporated into | Historical report |
| --- | --- | --- |
| g1 | g2 | IJ `814f4a38 -> c0e3c970` |
| g2 | g3 | IJ `c0e3c9ac -> 814f4a38` |
| g3 | g4 | CALL `826f0560`, `memcpy` |
| g4 | g5 | CALL `826b2720`, `mas_leaf_max_gap` |
| g5 | g6 | CALL `826b2f60`, `mas_mab_cp` |
| g6 | g7 | CALL `826bfd20`, `mas_spanning_rebalance` |

The final frozen record is sequence 6, admitted g6, CALL target
`0xffffffff826bfd20`, `from=0`, token 14. Final g7 includes that callee.
The final image has two matching source CALLs: `mas_wr_bnode+0x1074` at
`0xffffffff826c2e64`, continuation `826c2e69`, and
`mas_wr_spanning_store+0x7de` at `0xffffffff826c44ae`, continuation `826c44b3`.
The CALL report records a target, not the CALL PC, so it cannot select between
them. This is the **last incorporated learning event**, not the final g7 exit.
The module IJ addresses are kept exactly as recorded; no earlier run's module
pointer or containing-symbol attribution is transplanted.

## Runtime exclusions and the remaining evidence limit

The receipts do not directly retain a post-g7 miss ledger. The exact immutable
ABI2 source nonetheless supplies a useful deduction:

1. Successful publication acknowledges records under the publication gate.
   Any survivor selects CALL/IJ pending status; g7 NORMAL therefore implies an
   empty unresolved ledger (`execution/images.inc:321`, `339`, `33`).
2. A first current-g7 miss must allocate and publish pending state: revision six
   is not exhausted and the empty 32-slot ledger cannot overflow or deduplicate
   it (`images.inc:394`, `410`, `423`).
3. Mutable NORMAL publication rejects this immutable image; only another
   immutable publication could clear pending state, and that increments the
   generation (`images.inc:356`, `324`).
4. Earlier applications drained; fresh fixed-point frames bound the unchanged
   g7 image. Both boundaries stayed NORMAL g7 with no additional compiler
   records or publication. Thus retained CALL/IJ/RET/JMP miss handback is
   excluded for these frames by the source invariants, rather than by silence
   in the history file alone.

In particular, the generated outer RET at `0xffffffff8181c7f5` has an empty
RET-destination table (`ij_ffffffff8181c7f6`, `jit.S:145984`): if reached it
would report a retained miss. That outcome is excluded by the preceding
deduction; its static presence is not an observed return or handback.

Budget pauses resume the same image. Ordinary memory services resume or finish
all ownership. Context, IRQ, invalid owner/ledger and unsupported-operation
checks are error/BUG routes rather than successful finished handbacks;
nonreturning helpers cannot explain a drained completed application. The
image's requirements exclude legacy native-escape, direct-string quota and
address-guard mechanisms. Supported nested acquisition resumes this same root
image with exact child ownership; inner acquisition itself is not evidence of
a nesting failure or deadlock.

Relevant exact runtime locations are `kd_service.c:816`, `834`, `898`, `984`,
`992`, `1013` (release boundaries), `execution/continuation.inc:641` (completed
CALL/continuation), `execution/wrapper_entry.inc:268`, `334` (miss/frontier),
`exe.c:564`, `576`, `626`, `635` (routing), and
`kd_service_observe.inc:110` (counter fields). With tracing off, the counters
retain event totals without PC/reason. **Completed release/downgrade and source
frontier remain possible; the exact taken point remains unrecorded.**

Static copies, exact-source copies, symbol map and the preserved original
logs are retained beneath the original raw evidence directory at
`raw/bench/mmap1-normal-d421e7d5-v1/munmap-g7-static/`. All original campaign
receipts remain unchanged.
