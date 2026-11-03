# Reached MM activation: Stage (d)

Isolated branch: `codex/reached-path-translation`, continuing from
`1fec704bbeb19b3391066c49a5cb1e303528d2e9`. Native MM bodies, the MM integration
layer and the pinned will-it-scale executables are unchanged. This campaign
activates the general reached-mode rwsem provider; it adds no mmap1-specific
production helper or origin suffix.

## First candidate: `c7e10b24`

Exact source: `c7e10b24d80f6d710f12791a5159c23f1e9573a7`. The new session
contract requires no translator, image or writable device descriptor. General
provider preparation validates and pins the complete writer-site table without
allocating image slots. The old image session remains a separate contract.

| Check | Result |
| --- | --- |
| Affected session/runner unit driver | 21 cases passed |
| Delegated MM proof driver | Six cases passed |
| Syscall-pair driver | Nine cases passed |
| Private frozen-source driver | Nine cases passed |
| Ordinary provider and observation module builds | Passed |
| Actual mmap1 launch | Failed during the fresh child's exec MM setup |
| Returned mmap1 worker body / syscall pair | Not proved |
| Process-model run | Not started |
| Final retirement | Failed/undrained; VM recovery required |

The kernel was `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`17478c05-2012-4095-ada6-977c32222817`, with `kd_mmap=on` and full/lazy
preemption. The exact v3 ELF site audit has SHA256
`bcc3b8b23fc332904e26929e7e43961416d11db705480ed63e301dca07e1a7a1`;
all 55 records were audited. The retained unit and build receipts are separate
from actual application completion.

The first captured root was `create_init_stack_vma`, entry
`ffffffff8181cc7d`, O `18533`, E `18513`, request identity
`ff11000633db8fa8`, generation 1. It stopped at `ffffffff817f66da` in
`find_vma_intersection`, after reaching artifact sequence 82. The instruction
`65 4c 8b 25 26 49 c1 02` is a 64-bit GS load into R12. It reads the kernel's
per-CPU stack guard; the existing decoder recognized it, but the runtime read
policy allowed only preempt-count operands and returned `-EINVAL` internally.
The existing diagnostic path stopped E; O remained pinned and waiting. No
public lock error or completed body is inferred.

The stopped origin occupied the collection CPU during exec, so the ordinary
guest collectors could not record a final state. Before reset, the QEMU host
preserved the full serial file and a paused, consistent copy of the kernel
printk ring, descriptor array, info array and data buffer. The decoded
[failure excerpt](first-kernel-ring.log) is offline diagnostic evidence,
not a continuous complete-run receipt. [Raw capture identities](first-ring-capture.json)
and [retention locations](first-retention.json) preserve the original bytes.
The failed guest's persisted controller/build/session files were copied after
recovery; [the controller state](first-controller-state.json) remains at
`APPLICATION`, without worker return or drain.

One QEMU reset recovered the failed VM to the ordinary kernel; a one-time GRUB
entry then returned to scope5 KD. Default GRUB configuration was unchanged.
Recovery is not successful retirement. New attempts use separate frozen inputs,
output directories and boot identities; no counts are pooled across attempts.

## General instruction-service correction

The design was committed first as `8536bf61`. General resident GS loads/tests
now use the returning O instruction service, retaining exact CPU/GS base, IRQ,
Native owner, source frame and artifact ACK checks. Only actual preempt-count
operands receive count normalization; an ordinary read allocates no preempt
owner. This is an instruction interval, not an MM body moved to O.

The encountered function's normal epilogue contains
`65 48 2b 15 f8 48 c1 02` at `ffffffff817f6708`. General GS-source SUB32/SUB64
to a register is added with its exact input register value, width, destination
and Native arithmetic flags. The input operand is retained through all four
service/ACK stages. There is no named canary or caller-specific execution path.
This bounded inspection of the reached callee's return neighborhood does not
require an upfront CFG closure.

## Second candidate: `0ac46e80`

Exact source: `0ac46e80fac5ceebe7ddd429cae0feb0315a16da`. The seven selected
drivers passed: 500 decoder/Native-effect assertions including 98 Native SUB
tuples, 64 production read-policy checks, six memory-service validator cases,
21 MM session cases, seven delegated-proof cases, nine syscall-pair cases and
nine private-source cases. Provider and observation module builds passed.
See [units](second-units.json) and
[the persisted controller state](second-controller-state.json).

The retry used boot `4574d413-0717-40ea-ae1c-eb04726ce829` on the same verified
scope5 kernel. A prestarted additional resident collector ran on CPU 62,
independently of the ordinary CPU-63 collectors and the application. This is
an unscored diagnostic configuration, not a comparable timing point. Exact
module inputs, source hashes and boot identity remain in
[the launch receipt](second-launch.json).

Two ordinary GS LOAD64 transactions completed on O `3964` and resumed on E
`3956`, with generation 1 and exact artifact sequences 82 and 104. They created
no preempt owner. The [continuous resident log](second-resident-kernel.log)
then records the stop at `ffffffff826bbc0f`, bytes `f3 48 ab`, REP STOSQ in
`mt_find`. The root remained exec's `create_init_stack_vma`. Its normal local
initialization uses eight qword stores according to the captured ELF prefix;
the source `MA_STATE` correspondence is inferred from the matching Linux 7
source, not a runtime count measurement.

No root returned, and no mmap1 worker syscall completion or process-model run
is claimed. Actual SUB service was not reached before this stop; its passing
evidence is the separate Native differential fixture. The failed attempt was
preserved and reset using the armed one-time scope5 entry. See
[raw capture identities](second-ring-capture.json),
[retention locations](second-retention.json) and [reset](second-reset.json).
The recovered boot is `cc27a778-7ad3-4ce9-be5e-f4a0c69a5ce4`.

## Bounded STOS correction

The design was committed first as `1d9a20f1`. General byte/word/dword/qword
STOS, with or without REP, executes at most one source-width store per cold
step on E. Zero count performs no memory access. Only a completed store advances
RDI according to virtual DF and decrements REP's RCX; the source PC remains
at the instruction until count zero. A later failed element retains the exact
prefix and does not replay earlier stores. Source flags remain unchanged.
The normal local cap and persistent scheduling window count element steps.
The `instructions` observation is resident steps, including string elements,
not unique retired x86 instructions after this change.

Native effects, zero count, both directions, all widths, bounded resumption and
failure-prefix conservation require the fresh VM fixture before another actual
MM retry. The general qualified-store contract still excludes arbitrary
fault/fixup behavior. No origin memset model or caller-specific path is added.
Returned mmap1 delegation, throughput and a Nano gate remain unproved. Remaining
unsupported operations must be supplemented when reached; no entire suffix is
run on O.

## Third candidate: `afe1ba21`

Exact source: `afe1ba2118f150478340b5a87bda40443be41b69`. The provider build
and resident fixture passed, with 53,553 assertions including 96 Native STOS
tuples. Seven MM proof cases and nine private-source cases also passed. The
fixture drained normally; it remains component evidence, separate from MM.
See [the exact reply](third-units.json).

The actual retry used boot `cc27a778-7ad3-4ce9-be5e-f4a0c69a5ce4`. O `4837`
and E `4810` completed generation 1's `create_init_stack_vma` root, including
its release and returned events. This is positive other-task execution of an
exec MM writer, not proof of mmap1 worker mmap/munmap completion. Generation 3
then stopped at `ffffffff817fd1d7` in `change_protection`, within entry
`ffffffff818e077d`, on the source prefix `2e`. No successful application exit
or process-model run is claimed. The [resident log](third-resident-kernel.log),
[controller state](third-controller-state.json) and
[raw retention record](third-retention.json) preserve this distinction.

The ELF at that PC contains a CALL to `__SCT__might_resched`; a static-call
patch changes its live bytes. After recovery to boot
`e3bdd1fb-4f25-4b25-a137-5fd460c31758` with the same declared kernel/policy,
a [live read](recovered-staticcall-bytes.json) contains
`2e 2e 2e 31 c0`, the padded return-zero XOR form. This is explicitly a
recovered-boot read, not a full-byte pre-reset capture of the failed instruction.
The source implementation's `xor5rax` form independently explains the prefix.

## Padded static-call correction

The design was committed first as `03eec69c`. The reached decoder accepts
repeated CS prefixes only for NOP and register-register XOR16/32/64. The live
form clears EAX and sets XOR's arithmetic flags through the existing lowering;
it is never skipped as a NOP. Prefix/REX ordering, full instruction fetch and
the fifteen-byte limit remain enforced. Other CS-prefixed operations remain
explicitly unsupported. Native differential and bounded-fetch fixtures require
a fresh VM run before the next actual MM attempt.

## Fourth candidate: `140ca7e5`

Exact source: `140ca7e52a121d2ab449f9ed860de3bab0e47d91`. The provider build
and resident fixture passed 54,504 assertions, including 150 Native padded-XOR
tuples and complete NOP fetch/no-access checks. Seven MM proof and nine
private-source cases passed. See [the exact reply](fourth-units.json).

On boot `e3bdd1fb-4f25-4b25-a137-5fd460c31758`, actual MM execution passed the
patched scheduling site, then two generation-3 roots stopped at
`ffffffff826f0568`, `__memcpy+8`, bytes `f3 a4` (REP MOVSB). The origins/executors
were `4987`/`4980` and `4990`/`4947`. Both occurred within this one failed
activation; they are not two benchmark points. Their captured entries were
`ffffffff818e077d`. No returned worker mmap/munmap or normal application exit
is claimed. The [resident log](fourth-resident-kernel.log) retains both stops.

The [complete live-byte read](fourth-live-site.json) was taken before reset,
alongside the serial and kernel-ring capture. The ELF identifies the selected
fast-string helper; its RCX comes from RDX and its returned destination is in
RAX. See [retention](fourth-retention.json) for original raw files and hashes.
Recovery used the armed KD entry; the new boot is
`f194aa8c-fad2-49c2-962f-5fe22024eae7`.

## Bounded MOVS correction

The design was committed first as `10de7f6b`. General MOVS widths 1/2/4/8,
with and without REP, read one qualified source element and store one
destination element per step on E. Only successful storage advances RSI/RDI,
decrements REP's RCX and advances the PC when complete. Flags and RAX remain
unchanged. Zero count accesses neither address, and failed source reads or
destination stores retain the exact earlier prefix. Native overlap behavior
and bounded resumption have focused fixtures; fresh VM validation is pending.
There is no origin memcpy service or caller-specific path.

## Fifth candidate: `b8b915e9`

Exact source: `b8b915e93a8ff6a3897c15063c609179c9170278`. The provider and
resident fixture passed, with 57,972 assertions including 480 Native MOVS
tuples and overlap/read-failure/store-failure/resumption checks. Seven MM proof
and nine private-source cases passed. See [the exact reply](fifth-units.json).

On boot `f194aa8c-fad2-49c2-962f-5fe22024eae7`, the actual retry passed the
copy and reached `kvfree_call_rcu+0x237`, `ffffffff817ca6b7`, bytes
`65 39 15 02 71 c5 02`: compare EDX against the origin CPU's NUMA field.
O `4821`, E `4782`, generation 3, entry `ffffffff818e077d` stopped there.
[The full live read](fifth-live-site.json),
[resident log](fifth-resident-kernel.log) and [raw retention](fifth-retention.json)
preserve the undrained attempt. No mmap1 worker completion or process-model run
is claimed. Recovery returned to scope5 boot
`10ea8f17-afa2-41b1-b449-2522fc6c4294`.

## General deferred-free API service

The design was committed first as `cf39c552`, after reading the exact scope5
source. [Source hashes and locations](deferred-free-source.json) bind
`mm/slab_common.c`, `include/linux/rcupdate.h`, `mm/slub.c` and related files.
`kvfree_call_rcu(head, ptr)` is an unchanged public deferred-free API. A NULL
head requires a sleepable context and can reach `synchronize_rcu()`/`kvfree()`;
an embedded head supports atomic callers. Its own Native implementation must
own its temporary local IRQ/slab intervals.

The immutable descriptor now declares a general argument-zero-dependent
context policy, appended as value 14. Each invocation captures argument zero
and resolves its private context before publication: NULL selects balanced,
non-NULL selects atomic-compatible. Existing context checks and exact CALL,
owner, frame and ACK machinery remain unchanged. Fixed policies retain their
values and behavior; mapped descriptors do not admit the new policy. The
public two-argument void API is registered once for all callers, without MM
caller flags or a body adapter.

This new candidate executes the API once on O from its entry and returns to
the same E continuation. It does not restart the already interpreted prefix
of the failed attempt. Ordinary memcpy/memset still execute on E through the
backend. Optional trace fields retain the selected private context and argument
zero through all four Native stages; policy 14 must never reach execution.
Focused selector/context and actual-MM validation are pending for this revision.

## Sixth candidate: `a8325ab5`

Exact source: `a8325ab58769d5addaeee82b46c1670d8555a3aa`. The focused Native
context fixture passed 426 checks with PREEMPT_RCU=0 and 426 with
PREEMPT_RCU=1; all eight expected negative variants were detected. Returning
CALL discovery/emission passed 20 cases, helper trace validation seven, MM proof
seven and private-source admission nine. See [units](sixth-units.json).
Provider and observation module builds passed.

On boot `10ea8f17-afa2-41b1-b449-2522fc6c4294`, the
[resident log](sixth-resident-kernel.log) positively records one
`kvfree_call_rcu` request/enter/done/resume: O `4199`, E `4182`, generation 3,
sequence 15, artifact 3407, context 2 and non-NULL argument zero
`ff11000343638908`. The same E resumed the same retained root. NULL-head
execution is unit/context evidence only in this attempt, not an observed MM
call. This API return does not establish complete worker syscall execution.

The body then stopped at `_find_first_bit+0x25`, `ffffffff81cc7195`, bytes
`f3 48 0f bc c9` (TZCNT RCX to RCX). The captured entry remained
`ffffffff818e077d`. [Complete live bytes](sixth-live-site.json),
[retention](sixth-retention.json) and the undrained controller state are kept.
No process-model run or returned worker mmap/munmap is claimed. Recovery boot
is `ec3eeb9c-0223-4379-a99c-2f8cd6eda18b`.

## General bit-scan correction

The design was committed first as `2dcc22bf`. BSF/BSR/TZCNT/LZCNT16/32/64
execute one actual Native scalar instruction on E. They retain the full old
destination and source flags as inputs, then import the full captured GPR and
arithmetic flags. This preserves the CPU's actual zero-input undefined BSF/BSR
result and 16/32-bit upper-register behavior. Qualified memory sources read
before effects; a read failure leaves the packet and budget unchanged. The
bitmap primitive stays delegated rather than becoming a Native API service.
Native register/memory, zero-input, alias and failure fixtures require fresh
VM validation before the next actual-MM attempt.

## Seventh candidate: `6b4a8983`

Exact source: `6b4a898397daae157254387691543f7efa953f52`. Provider and resident
fixture builds passed; 63,165 assertions included 864 Native bit-scan tuples,
zero-input/width behavior and exact reached-alias/failure checks. Seven MM
proof and nine private-source cases passed. See [units](seventh-units.json).

On boot `ec3eeb9c-0223-4379-a99c-2f8cd6eda18b`, execution reached read-only
memory BT in `__next_zones_zonelist`, `ffffffff817b7c44`, bytes `48 0f a3 02`.
Two generation-3 roots stopped at this same operation within the one failed
activation: O/E `4848`/`4837` and `4853`/`4832`, entry `ffffffff818e077d`.
The signed node index comes from a preceding MOVSLQ in the captured code.
[Resident trace](seventh-resident-kernel.log),
[complete live bytes](seventh-live-site.json) and
[raw retention](seventh-retention.json) remain separate from completed-worker
proof, which is still absent. Recovery boot is
`91c2a715-19d4-4f19-b210-65e10cdb2864`.

## Read-only memory-bit correction

The design was committed first as `4a9701fb`. Memory BT16/32/64 computes the
containing word with a signed operand-width register index; imm8 uses only
within-word bits. Exactly one qualified word is read. Native memory-form BT
then operates on that private retained value for its flags, with no source
data/GPR write. Source failure has no packet/budget effect. Memory BTS/BTR/BTC
and LOCK forms remain explicit unsupported operations. Native signed/immediate
and no-effect fixtures require the next VM validation.


## Eighth candidate: `07189e3c`

Exact source: `07189e3c2f618c0b96993542e1d6bcbf63e108be`. Provider and resident
fixture builds passed, with 64,432 assertions including 252 Native signed and
immediate memory-BT tuples. Seven MM proof and nine private-source cases passed;
see [units](eighth-units.json).

On boot `91c2a715-19d4-4f19-b210-65e10cdb2864`, the body advanced into
`get_page_from_freelist+0x2c9` and stopped at `ffffffff81828ca9`, bytes
`65 48 03 1d 77 23 be 02` (GS ADD deriving a CPU-local page-allocation address).
The preceding code increments the Native preempt count; the following code
tries a raw spinlock. O `4837`, E `4812`, generation 3, entry
`ffffffff818e077d` are retained in the [resident log](eighth-resident-kernel.log).
[Live bytes](eighth-live-site.json) and [raw retention](eighth-retention.json)
record this undrained attempt. Worker mmap/munmap completion and the process
model remain unproved and unrun respectively. Recovery returned to scope5
boot `a2887015-5808-4947-ae2f-f3d7d3416a98`.

## General public page-allocation API service

Design was committed first as `18f87893`. The [exact source inventory](page-allocation-source.json)
binds page allocation, GFP, task-scope and NUMA-policy definitions. Six public
page/folio allocation APIs now use the general returning Native API service,
with exact original arguments and results. Their Native bodies run on O,
retaining task GFP scopes, NUMA policy and internal CPU/IRQ/refcount ordering;
the same E then continues the MM algorithm. No private allocator body or MM
caller-specific adapter is registered.

Context 2 means atomic-compatible: inherited source pins remain exact, while
a sleepable origin is not artificially made atomic. The Native allocator
decides whether its original GFP and task context permit blocking. No new
argument selector, weakened context check, or replay of the interpreted prefix
is introduced. Ordinary delegated instructions still execute on E. The new
roster/context fixtures and actual syscall retry require fresh VM validation.


## Ninth candidate: `9b0da70c`

Exact source: `9b0da70c7a8b8a0c32c4b3e624688da7fbb4d731`. Five focused unit
drivers passed: the public allocator/context contract, 20 returning-call cases,
seven helper traces, seven MM proof cases and nine private-source cases.
[Unit receipt](ninth-units.json) retains the context checks and eight expected
negative cases. Provider and observation module builds passed.

On boot `a2887015-5808-4947-ae2f-f3d7d3416a98`, the next reached operation
was `mod_node_page_state+0x33`, `ffffffff817b9883`, bytes `65 0f b6 07`: a
byte GS load in the CPU-local accounting transaction. O `4173`, E `4151`,
generation 3, entry `ffffffff818e077d` are retained in the
[resident log](ninth-resident-kernel.log). [Live bytes](ninth-live-site.json)
and [raw retention](ninth-retention.json) preserve the failed activation.
It remains undrained, with worker mmap/munmap completion unproved and the
process model unrun. Recovery boot is `2beefbc5-196a-4620-8859-e38b83768b9b`.

## General Native VM-accounting service

The source-backed design was committed first as `73c246ab`.
[Source inventory](vm-accounting-source.json) binds scope5 `mm/vmstat.c` and
`include/linux/vmstat.h`. Six ordinary public node/zone mod/inc/dec APIs now
use returning Native API service, retaining exact public arguments/results,
CPU-local differential retry and atomic overflow accounting on O. Their
private helpers and MM callers are unchanged and unregistered. The same E
continues afterward. Context and exact CALL/ACK/lifetime guards are unchanged;
fresh roster checks and actual syscall validation remain required.


## Tenth candidate: `918cd561`

Exact source: `918cd561026a61156b81511597c4737402551d5f`. The five focused
context, returning-call, trace, MM-proof and private-source drivers passed
([units](tenth-units.json)); provider and observation module builds passed.
On boot `2beefbc5-196a-4620-8859-e38b83768b9b`, the next stop was
`ffffffff818a863b` in private `mod_memcg_lruvec_state`, bytes
`65 48 01 5c c2 18` (GS ADD RBX to a CPU-local accounting word).
O `4112`, E `4049`, generation 3, entry `ffffffff818e077d` remain in the
[resident log](tenth-resident-kernel.log). [Live bytes](tenth-live-site.json)
and [raw retention](tenth-retention.json) preserve the undrained activation.
No worker mmap/munmap completion is proved; the process model remains unrun.
Recovery boot is `b777ab81-d2f8-4afc-9c7e-f9708d0d120e`.

## General memcg/lruvec accounting service

Design was committed first as `c2ebc9a5`, based on the
[exact source inventory](memcg-accounting-source.json). Four public accounting
APIs now retain their Native per-CPU, RCU, node/cgroup/lruvec transaction on O
and return to the same E continuation: `mod_memcg_state`, `mod_lruvec_state`,
`lruvec_stat_mod_folio` and `mod_lruvec_kmem_state`. Each is three arguments,
void, atomic-compatible, with original int delta semantics. No private helper
or MM body adapter is registered, and existing context/owner/ACK checks stay
intact. Fresh focused checks and actual-MM validation are pending.


## Eleventh candidate: `eb21e334`

Exact source: `eb21e33446de2a519f1299f02b9d567591dbc2b7`. All five focused
drivers passed ([units](eleventh-units.json)); provider and observation builds
passed. On boot `b777ab81-d2f8-4afc-9c7e-f9708d0d120e`, execution advanced
to generation 5, entry `ffffffff817b6f68`. The next stop was
`__get_unmapped_area+0x6b`, `ffffffff817f716b`, live bytes
`2e 2e 2e ff d0` (CS-padded CALL RAX), O `4072`, E `4046`. The ELF
originally calls an indirect thunk at this site; its live patched bytes must
be decoded faithfully. [Resident log](eleventh-resident-kernel.log),
[live instruction](eleventh-live-site.json) and [raw retention](eleventh-retention.json)
remain failed/undrained evidence, with no completed worker proof or process
model run. Recovery boot is `16530f92-2961-4dc4-a1fa-49858d3d3408`.

## Reached padded register-branch correction

Design was committed first as `a8d562a6`. The resident decoder now admits
CS-padded register FF /2 and /4 near CALL/JMP, preserving REX prefix order,
64-bit targets, full source CALL word and normal edge/return dispatch. Memory,
far, other FF groups, operand-size override, LOCK and REP in this slice stay
explicitly unsupported. Source truncation retains its source-failure status.
The address-selection algorithm continues on E; no MM body is added to the
Native API service catalog. Fresh differential/edge checks, build and actual
MM retry are required.


## Twelfth candidate: `4fd4d4d5`

Exact source: `4fd4d4d5c11ad6dcc659580c3de44960801ef931`. Provider and resident
fixture builds passed, with 64,552 assertions. The new padded CALL/JMP cases
are virtual control-flow/edge checks, not a Native branch differential oracle;
prior scalar/string Native comparisons remain included. Seven MM-proof and
nine private-source cases also passed; see [units](twelfth-units.json).

On boot `16530f92-2961-4dc4-a1fa-49858d3d3408`, the application retry
reached `vma_link_file+0x4e`, `ffffffff81816e6e`, live bytes
`48 0f ba 6d e0 03` (BTSQ immediate3 on a source-stack flag word); the
next source instruction sets bit5. O `4855`, E `4795`, generation5, captured
entry `ffffffff817b6f68` are retained in the [resident log](twelfth-resident-kernel.log).
[Live bytes](twelfth-live-site.json) and [raw retention](twelfth-retention.json)
preserve the undrained activation. No completed worker mmap/munmap or process
model is claimed. Recovery boot is `a30dc9fd-a378-435c-9b2f-5b42d85472e1`.

## Exact memory bit-update correction

Design was committed first as `978f9e92`. General memory BTS/BTR/BTC now use
one actual Native source-word RMW through the existing qualified callback,
with distinct unlocked/LOCK operations. Signed register bit-string addressing,
imm8 masking, widths16/32/64, exact flags and no source GPR write are preserved.
No split load/store or retry is introduced. Read-only BT keeps its existing
path; LOCK BT remains unsupported. No callback or a failed callback leaves
packet and budget uncommitted. The VMA algorithm continues on E. Fresh Native
differential checks, build and actual-MM retry remain required.


## Thirteenth candidate: `c2ee2298`

Exact source: `c2ee2298d138e036cc8803038c464798ce89842d`. Provider and resident
fixture builds passed, with66,008 assertions including288 Native memory
bit-update tuples. Seven MM-proof and nine private-source cases passed
([units](thirteenth-units.json)). The actual retry reached generation11
at mmap entry `ffffffff817b6f68`, O4837/E4808, then stopped on a CS-relative
CALL in `__rb_insert_augmented`, `ffffffff826cd5cb`. A separate PID1 root
reached the same encoding at `ffffffff826cd699`. Preserve these as separate
roots in one failed activation; no worker completion is inferred.

The additional monitor also reported a lost kernel-log cursor. Its
[exact result](thirteenth-monitor-result.json) and partial
[resident log](thirteenth-resident-kernel.log) remain observation-failure
evidence. The failed controller files are retained separately. The VM was
recovered and verified idle on boot `8fc802a7-cf87-4db6-be29-0f059fefb751`.
This is recovery, not successful request retirement. The process model was
not run. Existing local and host archives of this activation remain intact.

## Fixture naming and relative-call completion

The naming design was committed as `ce5ad76a`/`fca2e50b`, and the mechanical
rename as `d127adc2315938b3d0fd2fc0bbcd394012696144`:20 correctness-module
directories now use `fixture/`, and five shared body headers use `body`.
Current build/runner/include paths were updated. Moved module contents were
verified unchanged except for one updated relative include;755 maintained
Python files parsed, and renamed includes resolve with their existing include
directories. These are static checks, not VM test passes. Historical records
and explicit old-baseline artifact lookups remain unchanged.

Relative-branch design was committed first as `c389ddeb`. The general resident
decoder now admits CS-prefixed E8/E9/EB near CALL/JMP with full-prefix next IP,
signed displacement, exact CALL word, flags and unchanged failure behavior.
Rotation callbacks stay on E; no MM body service is added. New component
checks cover complete CALL/RET, forward/backward limits, prefix order, jumps,
truncation and failed stack writes. The new launcher drains its independent
log cursor every10ms and still fails on missing records. Fresh VM builds and
separate actual threads/processes validation remain required.


## Fourteenth candidate: `e37977dd`

Exact source: `e37977dd29183a0271f77200a54af0cc8fcc1602`. The renamed
resident fixture and provider built successfully and passed66,068 assertions;
seven MM-proof and nine private-source cases passed ([units](fourteenth-units.json)).
The actual MM probe also built successfully from `fixture/`. The reference
scan found no remaining active directory references, apart from the explicit
old-baseline artifact adapters retained unchanged.

On boot `8fc802a7-cf87-4db6-be29-0f059fefb751`, the actual run advanced
to munmap entry `ffffffff8181c73b`, generation87, O5023/E4962. It stopped at
`ffffffff81822009`, GS ADD inside private `__free_frozen_pages`. Separately,
a PID1 root O1/E4965 reached locked byte AND at `ffffffff817eced8` in
`copy_page_range`. Both remain explicit failed roots; repeated ordinary
acquisitions do not by themselves prove complete mmap1 worker syscalls.
The observer again reported an overrun, despite shorter polling
([monitor](fourteenth-monitor-result.json)); its log is partial. The process
model was not run. Ordinary serial and controller records were retained, and
recovery returned to idle boot `ae1caaa8-6b41-4a13-9e56-920db362d739`.

## Release APIs, logical RMW and diagnostic buffer

Design was committed first as `08b7bd3d`. General page release now uses
Native returning services for the six declared allocator APIs, preserving
exact original inputs, refcounts, FPI policy and balanced CPU/IRQ context.
The private static helper and MM bodies are unchanged. The
[exact source inventory](page-release-source.json) binds the declarations.
LOCK AND/OR/XOR now execute one exact Native RMW at widths8/16/32/64;
register and immediate forms have focused Native differential checks.
Ownership, cancellation, downgrade and retirement code is unchanged.

The next diagnostic uses a separate one-time scope5 boot entry with a16MiB
log buffer; it preserves the ordinary default and all old entries. It must
retain its new boot/command-line identity and still fail on lost records.
No timing result is inferred or combined across these settings. Fresh checks
and actual thread/process execution remain required for the new candidate.


## Fifteenth candidate: `73b8da74`

Exact source: `73b8da745535ac8098a66a329b294c2796b8872b`. Four unit drivers
passed, including the Native release/context roster,20 returning-call cases,
seven MM-proof cases and nine private-source cases. The resident runner
stopped at the exact identity check before its build: the new log16 command
line differed from the original scope5 bundle. This is a failed prerequisite,
not a module or application pass; see [receipt](fifteenth-checks.json). Neither
actual application model was started on this candidate.

Design `47151226` adds separate explicit profile `kdscope5-log16-kd` and its
own canonical bundle. Original profile identities remain unchanged. Both
module runners and the actual MM controller use the same explicit label; the
new runtime profile requires exactly the16MiB log argument. Fresh bundle
verification, focused checks and the two application runs remain required.


## Sixteenth candidate: `9dc0fbf3`

Exact source: `9dc0fbf310134840e9198c632c87702ded6f9935`. The separate
diagnostic bundle passed full source/build/installed/runtime verification;
only explicit variant and runtime policy differ from its preserved base.
The log-buffer syscall reported16,777,216 bytes on boot
`5a5f1b26-143e-4130-9932-b2e8714684cd`; see [boot](log16-boot.json) and
[bundle derivation](log16-bundle.json). Four focused unit drivers and67,608
resident checks passed ([checks](sixteenth-checks.json)).

Actual provider load returned ENOSPC before factory activation.
[Ordinary load/lifecycle logs](sixteenth-load.json) retain the failure;
subsequent idle checks confirmed no remaining project module. No actual
thread or process run started. Source inspection identified the one-page
Native descriptor discovery bound; the128-slot registry is retained.

Design `9da1622b` now publishes eight bounded16-slot pages and an exact
generation/slot/active state. New readers require unchanged before/after state,
correct cookie/page membership and the complete active count. Existing
single-table readers receive overflow for an oversized complete table.
Registration slots, cookies, Native context, source references and request
retirement remain unchanged. Unit coverage is updated for the expanded
publication contract, including legacy overflow, full registry capacity,
missing/changed/misplaced rows and empty pages. Fresh VM validation is pending.


## Seventeenth candidate: `d9a9e529`

Exact source: `d9a9e5295ea22ce09ca67df295e1da89abd764f3`. The focused
VM checks found fixture compilation issues: two signed comparisons and a
page-size assertion included in a context-only fixture. The mapped-registry
fixture also still expected the former single-page capacity rejection.
These were failures, and the resident/module/application stages did not run;
[all check results](seventeenth-checks.json) are retained.

The correction keeps the compile-time page bound in the actual page getter,
uses explicit checked comparison types, and updates mapped publication to
require the complete80-row registration plus an unchanged128-slot capacity
rejection. It preserves every old ownership/context check and adds page
completeness coverage. Fresh focused VM checks remain required.


## Eighteenth candidate: `14b00a56`

Exact source: `14b00a56aeda7c40c9a9c2046bad19b18bff818b`. All seven
focused drivers and67,608 resident checks passed ([checks](eighteenth-checks.json));
provider and observer builds and loads passed. Preparation stopped because
the generic parameter snapshot still read the legacy oversized table, which
returned EOVERFLOW. The [traceback](eighteenth-controller.json) identifies
that exact reader. No factory activation or application run followed.

The inactive provider had zero bindings, frames and writers. It was retired
through the ordinary source retirement operation, reached exact zero modules/
frames/writers, and unloaded normally; [receipt](eighteenth-retire.json).
This is successful configuration cleanup, not completed mmap1 execution.
Design `6b24d82d` updates that known table read to use validated pages and
retains errors from every other parameter. A focused old/new snapshot fixture
is added; fresh VM checks and both actual application models remain required.
