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


## Nineteenth candidate: `00af410a`

Exact source: `00af410a1e2a895a1d2c6c7c3c3a165f993b4884`. All eight
focused drivers and67,608 resident checks passed ([checks](nineteenth-checks.json)).
Provider/observer builds, loads and preparation passed, and actual MM
delegation activated. On boot `5a5f1b26-143e-4130-9932-b2e8714684cd`,
munmap generation87, O11917/E11858, entry `ffffffff8181c73b`, stopped on
GS CMP at `ffffffff8148f9f8` in `kick_process`. The complete available
[resident log](nineteenth-resident-kernel.log) and controller state are kept.
This remains undrained application failure, with no completed worker proof;
the process model was not run. Normal serial records were preserved before
recovery to idle boot `7de8564f-fdcc-4d2e-941e-3a97b98a96dc`.

Design `e6be1d7c` adds the one-argument void public CPU-notification API to
the existing returning Native service. Its [exact source inventory](cpu-notification-source.json)
binds the original CPU comparison, notification and balanced preemption body.
O executes that API; E continues the retained MM algorithm afterward. The
caller-owned task reference and exact ACK remain required. Fresh context
checks and actual thread/process validation are pending.


## Twentieth candidate: `06952039`

Exact source: `06952039f142b35af66e4fba0d99f9c9c966721e`. Eight focused
drivers and67,608 resident checks passed ([checks](twentieth-checks.json));
provider/observer builds and preparation passed. The actual run reached
`exit_mmap`, entry `ffffffff817f9283`, O5431/E5345, generation1, and stopped
at the runtime-patched PUSHFQ inside `_raw_spin_lock_irqsave`,
`ffffffff8270235f`. IRQ-preserving Native acquisition is not implemented by
this result. The independent monitor also reported an overrun; its record
and partial log are retained. This remains failed/undrained execution;
process-model validation was not run. Ordinary serial records were preserved
and recovery returned to an idle diagnostic boot.

Design `594bf379` adds only eight completed reached CALL edges to the
preallocated cold state, printed at an unsupported point. It makes no IRQ
transition, Native return rewrite or whole-body local continuation. A focused
fixture checks root reset, bounded rotation and failed-CALL non-commit. This
will identify the actually reached enclosing interval before choosing its
required general context support. Fresh build and VM checks are pending.


The source-only review of `4b7b0b97` found the new call-context fixture was
not yet in the worker sequence. No checks or application run used that
frozen candidate. The next commit adds the missing invocation before fresh
VM validation; existing frozen inputs remain unchanged.


## Twenty-second candidate: `dc717333`

Exact source: `dc717333450fddf53fdeb65abd60539f8e4996cb`. Provider and
resident builds passed with67,643 assertions, including the new bounded
call-context fixture. Seven MM-proof and nine private-source cases passed
([checks](twentysecond-checks.json)). Actual execution again reached the IRQ
operation in `exit_mmap`, O5027/E4961, generation1, and failed before that
operation. [Reached call context](twentysecond-call-context.log) identifies
`free_pages_and_swap_cache` → `folios_put_refs` → private page-cache release
→ LRU IRQ acquisition. This resolves the enclosing interval from executed
source, without an upfront graph or a whole-MM local continuation. The run
remains failed/undrained, and process validation is unrun. Ordinary logs were
preserved before recovery to idle boot `5c11c49a-fbf5-43a8-84bf-058fb6472fc7`.

Design `6c3e2648` adds four general Native folio/reference-release APIs with
exact original arguments, encoded pointer bits and batch/refcount semantics.
Their balanced LRU/IRQ work executes on O and returns to the same E MM body.
[Source inventory](folio-release-source.json) binds the declarations and
implementations. No private LRU helper or MM algorithm body is registered.
The broader IRQ-held-body case remains unsupported; fresh context checks and
actual thread/process validation remain required.


## Twenty-third candidate: `02990b62`

Exact source `02990b62e55f7c2c9b5d6f0d9d6c5b1dd486151e` passed four
focused unit drivers and67,643 resident assertions, including the folio API
roster ([checks](twentythird-checks.json)). The first host placement
preflight failed before transfer or application launch; its separate retry
used unchanged inputs. The thread application printed all six warmups and
both measurement samples, then failed to finish within30 seconds. This is
an unscored diagnostic, not a throughput result or shutdown pass.

Both kernel-log cursors overran. The controller retained5,333 roots and5,332
completions with unsupported=0, but these counters include other active
processes and cannot prove application completion or a valid final drain.
No process-model run started. A later ordinary guest status read timed out;
no task trace was obtained. Preserve this failed/undrained run and its
[receipts](twentythird-attempt.json). Ordinary console logs were retained
before restart; the recovered boot is
`923c6745-e2f0-4bf7-9c81-34f8e146716e` and the idle gate passed. Restart is
recovery, not retirement.

The next diagnostic reserves collector CPUs from executor placement and
increases the explicitly bounded collection allowance. Executor/collector
CPU overlap and log volume are observed configuration facts; their role in
the shutdown failure remains a hypothesis until a complete trace exists.


A subsequent read-only analysis of the full preserved console found later
watchdog and blocked-task records, beyond the initial incomplete cursor
subset. [Wait locations](twentythird-console-waits.json) include
`kd_service_shadow_wait`, cross-CPU calls and CPU-stopper paths; rsyslog
waited in `migrate_swap` during NUMA fault migration. Some later application
roots returned and retired. These observations do not prove application
shutdown, nor do they establish which wait first prevented progress. The
initial missing task-trace request is separate from these ordinary watchdog
records. Do not describe this run as free of watchdog reports.

Diagnostic candidate `6f99fa27bb86a844356f59a740ef9ea25ea93945` implements
the documented executor pool and explicit bounded log allowance. The changed
Python sources parsed and the diff check passed on380G10. It has not built or
run in the VM: source transfer stopped before creating the new private tree
because root free space was0 bytes. Build disk2 retained21,923,479,552 bytes.
The two current ordinary logs were about1.9GiB each. Automatic approval review
rejected the proposed verified-copy/live-log rotation because changing those
contents and briefly stopping rsyslog needed explicit approval. That action
did not run; no logs or services were changed. Approval is pending. Earlier
rotations, frozen inputs, recovery data and all application evidence remain
intact. The placement change is not a claimed lock-protocol correction.


## Approved log preservation and twenty-fourth candidate

After explicit user approval on November4, preserve complete verified
compressed copies of the two current logs on build disk2. The first attempt
stopped when rsyslog's still-active socket restarted its writer and the
source stability check failed; neither live log was truncated. The retry
paused the service and its activation socket together, verified both full
copies before either truncation, and restarted normal logging afterward.
[Receipt](log-headroom-20261104.json) retains original byte counts, hashes,
archive paths and the unchanged earlier rotations. Root headroom returned
to4,006,993,920 bytes; build disk2 had21,550,256,128 bytes free.

Frozen candidate `6f99fa27bb86a844356f59a740ef9ea25ea93945` then transferred
successfully to its own private input directory. All previous frozen bytes
were verified unchanged. Three directly affected VM drivers passed20 unit
cases, and the provider/resident builds passed67,643 assertions with normal
fixture retirement and a final idle gate ([checks](twentyfourth-checks.json)).
The actual diagnostic selects executor CPUs0–61, reserves62/63 for collectors
and permits1024MiB per log; all loss/limit failures remain failures. The
unchanged thread application exceeded its lifetime limit without captured
upstream output; process validation was not started. Both primary log readers
lost records. The independent monitor retained207,568,717 bytes but also
reported325,804 cursor losses. No collection allowance was exhausted; this
is a collection/progress failure, not a byte-limit failure. These component
passes do not prove MM application completion or a performance gain.


[Failed-attempt receipt](twentyfourth-attempt.json) preserves the exact
configuration, counters, collector state and recovery. The later ordinary
console reached `0f 01 ee` at `ffffffff8140cb67`, inside
`__pkru_allows_pkey`, on a new status connection's page-fault path,
`lock_mm_and_find_vma`, entry `ffffffff817dfd33`. This unsupported point
occurred after the original application timeout and therefore does not by
itself explain that timeout. The helper reads the origin task's CPU register;
executing that read on E would use a different task's state. The recovery
returned to the ordinary disabled-MM kernel, boot
`52e91d8d-7cbe-4e38-8b13-335d48d503bb`; the next MM run requires a fresh
explicit diagnostic boot. Root filled again from the ordinary duplicate logs.
The user has been asked about temporary routing that preserves complete logs
on build disk2; no routing change has been made.


## Twenty-fifth candidate component check: `74011ac1`

`74011ac1598dd46dc33393231596aad358de5b6f` passed528 production decoder/
Native scalar checks and the three decoder mutation checks. Collector and
private-source checks passed. The new MM trace fixture failed because its
synthetic root fields placed family generation between generation and object,
which differs from the real trace grammar. The strict parser correctly
rejected it. Correct only that fixture's field order; retain the
[failed check](twentyfifth-checks.json). No provider build, resident run or
actual application run followed this component failure. The source tree is
frozen separately, and the runtime implementation is unchanged by the fixture
correction. The next actual run still requires complete log headroom and the
pending temporary-routing decision.


## Twenty-sixth candidate: `b2e96afe`

Exact source `b2e96afe229ac43c6ee05f186517615a48103385` passed528 Native
instruction/decoder checks,21 affected unit cases and67,643 resident assertions,
with provider build and final fixture drain ([checks](twentysixth-checks.json)).
The actual thread attempt used the normal log paths,512MiB child allowances
and a1GiB auxiliary allowance on boot `12de0f19-7bd8-4076-8a93-c0c82c63b49a`.
It exceeded the application lifetime limit and lost trace records. The
independent monitor retained168,240,232 bytes with233,332 losses. These
instrumented attempts are not a comparable throughput series. Process-model
validation remains unrun; no current MM success or speedup is claimed.

The [attempt receipt](twentysixth-attempt.json) retains ordinary console and
recovery identities. A later background `cron` page fault reached
`get_vma_policy+0x82`, `ffffffff81870a52`, with runtime first byte65. The exact
matching scope5 ELF has `65 48 63 05 66 0d bb 02`, a GS signed32-to64 load of
`numa_node`. This point followed the initial timeout and does not independently
explain it. A bounded ordinary status connection failed its banner exchange;
no successful live task snapshot was obtained. Console records were preserved
before recovery to idle diagnostic boot
`220dc789-0a1f-429f-a795-0e70af2b0f2d`. The prior approved log preservation was
repeated with full verification ([second receipt](log-headroom-second-20261104.json));
no earlier records were removed. Temporary routing is still unperformed.


## Twenty-seventh candidate: `cb5ee7a1`

`cb5ee7a10591fd2e505a9b029a3bad9e7132b3f3` passed562 production instruction
checks,21 affected unit cases and67,643 resident assertions, plus provider
build and final fixture drain ([checks](twentyseventh-checks.json)). Its actual
thread run again exceeded the lifetime limit and lost log records. The
[progress series](twentyseventh-progress.json) shows source generations,
instruction counts and completions advancing while the application remains
alive; at78 seconds the retained count was5,613 roots and5,612 completions,
with two active requests. Those samples cannot be described as a continuous
lock stall. One origin was executing munmap while the other waited for writer
admission; the roles/generations continued to change. The independent monitor
retained213,623,789 bytes with333,893 losses. Process validation remains unrun.

The [attempt](twentyseventh-attempt.json) retained all six warmups, both
measurement samples and average85 in the unchanged upstream output. This is
an instrumented failed diagnostic, not an accepted throughput result. Exact
pinned `main.c` samples first, then calls `pthread_cancel` and `pthread_join`
at termination (lines143-151,421-428). The application cannot be called drained
because it printed its average. Its actual `tests/mmap1.c:20` increments the
counter every operation; older256-operation publication notes concern a
different harness and are not applicable here. A bounded status read did not
complete. Ordinary records were retained before recovery to idle boot
`26cd5e75-bd3c-4df2-b2e6-35301aa5f751`.


## Twenty-eighth candidate: `283b70c2`

Exact source `283b70c24bd664e5c2614723b80d63ffd357ff04` passed562 Native
instruction checks,21 affected unit cases and67,643 resident assertions, with
provider build and final fixture drain ([checks](twentyeighth-checks.json)).
This diagnostic ran processes first. The unchanged two-process application
returned0 in9,280,665,574ns, and both observed workers disappeared. The
retained runtime snapshot reached2,488 roots and2,488 completions with no
active request. These are application and aggregate execution observations;
the complete per-request proof and final provider/source retirement did not
pass. Its collector lost77,737 ranges and the independent monitor lost93,465
ranges; neither file budget was exhausted. The application printed average155,
which is an unscored diagnostic value, not accepted throughput or a gain.
Threads were not started after that failed trace gate. The [attempt](twentyeighth-attempt.json)
retains those distinctions and recovery to ordinary idle boot
`02f54e27-1594-40f4-ac34-29d4033948dd`. Recovery does not prove prior drain.

The user authorized clearing exactly the two current standard log files. The
[receipt](current-log-clear-20261104.json) records their retained paths/inodes
and restored headroom. Earlier compressed copies, rotations and all benchmark
records remain. No log routing or service configuration changed.

An idle-VM [text-scan profile](text-scan-profile-20261104.json) used the same
8,388,428-byte,24,375-record prefix once for each method. The current per-record
regular-expression scan consumed2,009,745,959ns wall time; the batch plus
keyword prefilter prototype consumed121,982,997ns. Neither detected a fault
in this prefix. The exact input hash is retained. This measures collector
text work only, not application performance or full trace acceptance.


## Twenty-ninth candidate: `06caaf07`

`06caaf073543e3923f143014e6a15a4843ec28be` passed562 production instruction
checks,23 affected unit cases and67,643 resident assertions, with provider
build and fixture drain ([checks](twentyninth-checks.json)). The two-process
application again returned0 and its workers disappeared, in9,170,630,144ns.
Its printed average151 remains unscored. Aggregate reached observations were
2,581 roots and2,581 completions with zero active/unsupported requests. The
[attempt](twentyninth-attempt.json) failed complete capture: application reader
3,090 lost ranges and lifecycle reader2,990. Both run in the same Python
process on CPU63. The independent CPU62 reader retained249,270,496 bytes
with zero losses and no detected fault. This supports reducing duplicate
child collection; it does not validate the missing observer/proxy ledger or
prove an MM protocol defect. Threads were unrun after the failed gate. A
bounded ordinary receipt read timed out. Recovery retained console records
and returned to idle enabled boot `60842b20-b98e-4cb1-95a2-0d8bf62df094`;
it does not prove prior provider/frame drain. All raw records remain retained.


## Thirtieth candidate: `c373d273`

`c373d273797405833aff42b297d4a45d7f3a0ccb` passed562 instruction checks,
24 affected unit cases and67,643 resident assertions, with provider build and
fixture drain ([checks](thirtieth-checks.json)). Sharing the model reader
removed both child losses: the retained application window and full lifecycle
capture are complete with zero errors and no detected fault. The independent
reader also retained240,872,402 bytes without loss. The two-process application
returned0 and its workers disappeared. Reached observations ended at2,434
roots and2,434 completions with zero active/unsupported requests.

The [attempt](thirtieth-attempt.json) reached stable observer STOP with balanced
task/MM references, then timed out waiting for the short final syscall summary
in the buffered lifecycle file. The runtime per-root/service validations had
returned before that gate, but the final proof file and normal binding/source/
provider retirement were not completed. Do not report this as a full pass.
Threads were not started. The buffered-summary observation fix requires an
explicit collector checkpoint after STOP. Preserve all raw records and the
failed verdict. No throughput comparison or gain is claimed.


## Thirty-first candidate: `583a875a`

`583a875aef9e8977bfdbc99485df882b1123c9d7` passed562 instruction checks,
24 affected unit cases and67,643 resident assertions, plus provider build and
fixture drain ([checks](thirtyfirst-checks.json)). Its process application
returned normally and its exact application window is complete. The explicit
observer checkpoint resolved the summary visibility issue. Later CPU-intensive
proof parsing shared the interpreter with the active lifecycle reader while
background MM requests generated additional traces; that lifecycle capture
lost records. The independent reader retained385,764,607 bytes without loss.
The [failed attempt](thirtyfirst-attempt.json) retains both capture verdicts.
No final provider/source retirement or thread-model result was obtained.

The next revision moves the existing factory deactivation and zero bindings/
frames drain to after normal application completion and before parsing. The
application still runs fully delegated; this moves normal cleanup earlier
in post-application validation. The failed transfer before this run stopped
at the root-headroom gate and transferred nothing; the user-approved current
log cleanup restored3,966,492,672 free bytes, then a separate retry succeeded.
Earlier files and every failed outcome remain retained.
