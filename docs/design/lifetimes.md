# Source, lock and hook lifetimes

A completed body does not mean its request, lock allocation or code can be freed.
Physical owners, native executors, source pins, images and frames have separate
retirement obligations. Start with [design](../DESIGN.md) and follow
[ownership](locking.md) and [frames](frames.md) for exact unlock/ACK ordering.

## Resource lifetimes

| Resource | What is retained | Limit |
| --- | --- | --- |
| Source text | Session references to LIVE module core text, including learned callees | Pins do not retain arbitrary data or permit source replacement within a session |
| Image | Frame-bound descriptor; immutable mutex and transitioned spin generations survive until teardown | Binding an ordinary in-place spin/rwlock descriptor does not freeze its bytes |
| Physical acquisition | Exact owner, task/acquisition record or spin ticket | A heat, queue or completion counter is not ownership |
| Active request | Shared frame/packet, native executor references, source lease and unlock ACK obligations | DONE/NATIVE_READY or an idle hint alone is not retirement |
| Mutex node | Preallocated CPU/slot storage with separate OSQ and delegation memberships | One membership cannot overwrite another's links or retire the shared reservation early |
| Lock/data allocation | Caller keeps the containing object live through all users | Source/image pins do not retain that allocation |
| Provider | Device-session references and declared module dependencies | These do not establish arbitrary global-hook hot unload |

Address-keyed registration and heat tables cannot distinguish a new allocation
at the same address. Stop users and complete exact retirement before reuse.
An ACK for one logical release can precede final batch physical release; it is
not permission to free the object. An idle rwlock gate alone also misses fast
readers and ungated writers.

## Device session and source retirement

The daemon, cache and translator children retain one writer-open device session.
Real text reads pin their source before kcore access. Closing a parent does not
invalidate a child still holding the open description. Root registration and
ordinary call targets require resident source; kernel/module init text is not
made a valid long-lived target by the source-trust policy.

The source protocol is:

1. Pin source before text inspection, including cold extensions and learned
   callees. Reuse session references for repeated dependencies; retain anything
   an older image may still use even after a failed compilation.
2. Count admitted frame/batch leases exactly. Retirement sets the closed bit
   before inspecting the live count, so a racing admission either obtains its
   lease first or cannot enter. Failed module-reference acquisition rolls back
   its reservation.
3. Close new selection, registration and publication. Closure is permanent even
   if retirement reports busy. Existing owner/native ACK routes remain usable;
   already leased work may finish during DRAINING.
4. After callers stop/join and all source writers, queues, tasks, owners and
   frames drain, invalidate entries under the registry gate, then release source
   pins outside the raw lock. RETIRED is terminal; do not reopen or reuse slots.

A batch lease spans native/remote child cleanup and frame removal. An ordinary
CALL miss pins its target before native transfer or learning. If that fails after
progress, execution cannot restart at entry to hide it. Shared packet/frame
storage is transferred under explicit lifetime rules rather than copied.

Registration's read-only fast check is not an execution lease. It matches the
entry key/backend/ABI and observes source OPEN; readiness and frame admission
still govern execution. Slots are not recycled within the session.

The [daemon guide](../../daemon/README.md#device-session-and-source-residency)
owns device controls; [kd_source.c](../../kernel_module/kd_source.c) and the
[image code](../../kernel_module/execution/images.inc) implement retirement.

## Executable images and guarded spin transition

Frames bind a descriptor independently of acquisition tickets. Mutex uploads
construct a private immutable generation and publish it once. Old frames retain
that image, and old-generation misses cannot alter current metadata. Every
published generation consumes the shared image capacity until session teardown.

Ordinary spin/rwlock entries initially use an allocated in-place code block.
Supported root instruction-marker images (requirements exactly 33) stage a new
immutable block. The retained checked-address and historical string-image ABIs
also trigger their compatible immutable transition. Once transitioned, all later
generations for that entry remain immutable. Upload destination/generation checks
prevent an old in-place upload from overwriting a new immutable image.

Production trusts source and selects ordinary string CALL/RET; it does not emit
address guards or named string-service/direct-bridge images. The old direct route's
near-text pool, relocation and quota contracts remain
[historical compatibility](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/lifetimes.md#executable-images-and-guarded-spin-transition),
not a current translation requirement. Active call-depth policy and configured
near-text-pool restrictions remain in the [Linux 7 port guide](../../kernel_integration/linux70/README.md).

The registry has 511 slots and a shared maximum of 64 image descriptors. The
ordinary pool provides up to 64 blocks of the shared `KD_CODE_BLOCK_SIZE`
(4 MiB in the retained preparation candidate below). Optional legacy near-text
storage does not increase the shared descriptor limit. Descriptor exhaustion is
a real preparation failure; an available block alone does not grant publication.

Source pins do not stop concurrent writers to data or retain arbitrary string
allocations. The selected source/caller contract supplies those lifetimes;
production skips their semantic proof. Runtime source, actual return-word,
physical-owner and frame checks remain enforced independently.

## Object and provider teardown

Stop new calls, join users, close source admission and retire all work before
unloading workload/provider code or freeing locks/data. Check local sleepers,
OSQ/delegation memberships, reader counts, writer reservations, owners, ACKs,
source leases and frames. Never replace those records with an approximate balance.
An `EBUSY`, timeout or lost SSH connection is not drain. Retain pins and diagnose;
do not force unload or clear the guest source tree.

The maintained provider installs no whole-kernel lock replacement. Legacy global
hook experiments have separate reader/unload limitations and remain
[historical evidence](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/lifetimes.md#preserved-kernel-hooks).
A device reference alone cannot prove arbitrary hook-reader lifetime. Linux 7
MM integration uses its separate built-in local adapter and mm-reference/token
rules; see [MM identity and lifetime](../../kernel_integration/linux70/MMAP.md).

General hot reload, concurrent source versions, arbitrary allocation reuse,
whole-kernel replacement and broad oversubscription remain unvalidated.

## Kernel-generated instruction source extents

The isolated `codex/unified-lock-queue-mm` candidate starts this extension from
`b6a3db19ab8326d320b21d3e2690a09181f7f952`. Its build, 58 text-region cases and
19 live continuation/cancellation phases pass on scope5 v2, Build ID
`d3b5cf1b208028495b5fa9be2a3750b0831a2ec3`. Actual mmap1 preparation still
refuses the unclassified `0xffffffffc0002...` source region before activation.
Compact lookahead reached 71,552/105,968 cached bytes and 35,161/50,936 selected
decoded bytes in the first two stopped startup entries. These are preparation
observations, not execution or performance results.

The exact Linux 7 producer in `arch/x86/kernel/alternative.c` allocates ITS
instruction pages separately from static text and module memory regions. Core
pages remain resident, but `its_fini_core()` frees their pointer inventory.
`__retpoline_sites` also lies inside the exact image's freed init range.
Neither dangling metadata, an offline input table, executable-address status
nor matching instruction bytes proves ownership of a live output allocation.
The failing addresses are consistent with this producer; classify them through
an exact owner query before reading them or claiming that identification.

Add a minimal general producer/lifetime interface in the composed kernel:

- Transfer the existing core page inventory to permanent immutable metadata
  before freeing init state. Retain the executable bytes and existing runtime
  behavior unchanged. Do not copy protected bodies or add an allocation on a
  lock path.
- Expose one versioned generated-text extent query. A successful reply names
  exact start/end, source kind and owner. Permanent core extents require no
  releasable owner reference. Module extents require a live module reference
  acquired before returning; enumerate only producer-owned module page lists.
  Do not admit arbitrary executable allocations.
- The module query must be usable from the existing source guard: bounded
  metadata reads, no sleeping/allocation. Module-list inspection uses its
  existing RCU lifetime and live-state/refcount rules. A positive module reply
  transfers one reference to the source provider, which deduplicates or drops
  it exactly and retains accepted owners until normal source retirement.
- `kd_source_piece` keeps its current static-core and module-region paths and
  accepts this additional class only through that exact query. Query absence,
  invalid bounds/ABI, an unknown producer, unavailable owner or exhausted
  storage remains an explicit source failure. Complete text and pin-before-read
  remain required. Existing kernel/module-source sessions keep their protocol.
  The range iterator starts each reply endpoint at its current cursor and
  refuses a successful reply that does not advance it; no unset endpoint may
  enter the next iteration.

Generated register-jump thunks are source instructions, not arbitrary Native
helper bodies. Preserve the actual source CALL word, then translate their
owned JMP instruction normally. A retained indirect tail transfer to a
registered primitive needs its own FULL/flags-preserving exit and exact source
JMP provenance. It may run only the declared returning Native API on O, then
resume the same E/image at the real saved caller successor. It does not push a
second return word, run an O suffix, or treat RET/Jcc as an indirect CALL. Add an
explicit optional capability/image requirement so an older runtime cannot
receive that new exit. Unknown dynamic targets remain an enumerated integration
boundary; source ownership alone never supplies their API signature.

The existing identity observer instruments a function entry that can occur in
translated MM call graphs. Move that observation to the actual x86-64 mmap
syscall wrapper entry, preserving the unchanged application's argument filter,
exact task/mm/backend records, retained mm references and stable STOP/drain.
Decode the wrapper's `pt_regs` argument according to the captured Linux 7 ABI.
This changes observation placement only, not MM bodies or lock routing. The
instrumentation remains unscored; full per-syscall return joins remain pending.

Delivery order is producer/query and source-provider support, explicit returning
tail support and focused fixtures, then a preserved v2-to-v3 kernel amendment.
Record the new producer files/header separately in composition/capture; do not
change older profiles' source coverage retroactively. Preserve the complete v2
source/output, installed modules/boot files, bundles and receipts before any
replacement. Actual inventory/free-space gates decide whether bounded reuse
fits; the 50 GiB fresh-preparation gate remains intact. Use a separate measured
source/Build ID/boot boundary, re-audit writer entry addresses, validate the
query and ownership, then retry both unchanged mmap1 models. Do not claim proxy
execution, throughput or promotion from a build or published image alone.

## Retained text-window budget planning

The `79b6a768` attempt on scope5 v3 stops before factory activation or mmap1
execution. For `__do_sys_brk`, the retained cache holds 205,232 bytes, including
93,709 selected decoded bytes; the next 1,024-byte lookahead batch would require
304,544 bytes and exceeds the unchanged 262,144-byte cap. Three other entries
stop at the same cap with incomplete CFGs. Selected decoded coverage is not a
bound on the eventual complete call closure.

For the retained-service policy only, plan optional new lookahead in the fixed
order 1,024, 512, 256, 128, 64, then the mandatory 15-byte instruction prefix.
Use the largest batch whose merged cache fits. Every existing byte and root,
the aligned new window start and all new roots through `target + 15` remain
required. Planning retries perform no source read. If the minimum merged plan
still exceeds the cap, preserve the explicit budget failure before any read.
Record each attempted plan, its actual lookahead and whether it was selected;
do not report a rejected preferred plan as the fetched byte count.

This changes optional fetch planning, not the source-lease boundary or executable
scope. Keep pin-before-read, complete CFG decoding, the shared 32-expansion
limit, the shared image capacity and all CALL/RET/owner checks. Ordinary translations
retain their 8,192-byte page-aligned policy without these retries. A source
refusal does not trigger budget retries or permit discarding previously fetched
bytes. The existing mandatory-prefix source-refusal handling remains separate.

Focused cases must cover the largest fitting batch, unchanged preferred/default
plans, merged roots and old bytes, the full 15-byte prefix across alignment,
minimum-plan overflow and source refusal after a plan is selected. These cases
and actual MM preparation still require VM validation. Reducing this immediate
storage overhead does not prove complete callee closure, application execution
or performance acceptance.

The [explicit Native argument mapping](native_call_arguments.md) design extends
retained returning calls without changing their source CALL identity, context
checks or exact completion lifetime. Its initial allocation mappings preserve
the original caller input while resuming on the same executor.

## Bounded retained preparation capacity

The next isolated iteration starts from runtime
`8f12f82000ea73d28526f938cc21b87bcfa1c744`. Its actual MM preparation still
stops before either application starts: the brk root has 262,032 cached bytes,
131,000 selected instruction bytes, 33,443 instructions and 8,075 CFG blocks
at expansion 19. Its next minimum plan requires 265,401 bytes, exceeding the
262,144-byte aggregate cap. This is measured resource exhaustion, not evidence
that the reached source operations cannot execute correctly. A complete graph
or returned MM body remains unproved.

Use a larger, still bounded retained preparation profile to measure complete
coverage and emitted size. Ordinary source-window and return-flow defaults stay
unchanged; no lock API, Native MM body or unsupported-operation policy changes.

| Resource | Earlier bound | Candidate bound |
| --- | ---: | ---: |
| Retained aggregate cached source bytes | 256 KiB | 1 MiB |
| Ordinary aggregate cached source bytes | 256 KiB | 256 KiB |
| One provider source pin/read request | 256 KiB | 256 KiB |
| Retained return-flow analysis work | 65,536 steps | 262,144 steps |
| Ordinary return-flow analysis work | 65,536 steps | 65,536 steps |
| One emitted image / code block | 640 KiB | 4 MiB |
| CFG expansion passes | 32 | 32 |

The 64 ordinary blocks and up to 64 near-text blocks are eagerly allocated by
`kernel_module/exe.c`. Raising the shared block size in `include/exe_info.h`
reserves at most 512 MiB of payload instead of 80 MiB, plus allocation/page-table
overhead. The pool still shares 64 live image descriptors, not 128. Record the
actual allocation result on the 24 GiB VM. This is a candidate capacity choice,
not a Nano performance claim; master and historical receipts remain unchanged.

An aggregate merged window may exceed one provider request. Split its I/O into
consecutive pieces no larger than `KD_SOURCE_MAX_READ`; each piece must acquire
its existing source lease before its own complete read. Concatenate only exact,
gap-free returned bytes. Retain all roots, existing cached bytes and leases;
optional-lookahead retry cannot discard source or bypass a refusal. A partial
read/refusal still prevents CFG completion and image publication. Kernel source
request limits and source/module/frame retirement remain unchanged.

The retained-only work limit must be passed explicitly to the existing
return-flow analysis. Budget exhaustion still refuses an incomplete result;
ordinary callers retain the existing default. Keep runtime execution ticks,
CALL/RET words, opcode/context checks, exact owners and the image upload bound.
All daemon/provider consumers of the image capacity must agree through their
shared header or checked equivalent. Do not accept oversized image bytes.

Focused checks cover per-request splitting and refusal before completion,
retained/ordinary aggregate boundaries, the selected return-flow work limit,
and image-size boundary agreement. Build and run the existing helper/cancellation
phases on the VM, then attempt the same unchanged two-model mmap1 diagnostic
once on the frozen candidate. All 55 entry images must still be ready before
activation. Preserve any further resource or instruction failure as a distinct
result; do not infer returned-body, throughput or performance acceptance from a
larger preparation allowance.

### Separate retained CFG work bounds

The actual `3a0171f33516b9c914f4f33da1c7f0c415473ba0` attempt then reaches
32 transitions with 754,720 cached bytes and 329,812 decoded instruction bytes
(85,252 instructions, 20,783 blocks). It has used 22 covered-root rebuilds and
10 source-window extensions. Five new covered seeds are reported at refusal;
they are not the full remaining frontier: 215 blocks are incomplete. Neither
mmap1 model starts. The original failed result SHA256 is
`44bdc084f6136ca5d0aa58c25bcdbafc5d295a99efae41fe82672a4a97019c4f`.

For the next isolated retained candidate, separate these two finite work
allowances: at most 32 covered-root rebuilds and 32 source extensions, followed
by the final completion decode (at most 65 decode passes). Ordinary translation
keeps its original shared 32-transition/33-pass limit. Preserve the exact
seed-first, source-read and complete-analysis ordering; do not batch early
reads before the existing covered-seed rebuild. Earlier reads could change
which source refusal is encountered before the rebuilt graph removes edges.

Each accepted transition must still add the same exact roots or leased source
windows. Record both counters and their limits, refuse the specific exhausted
work class, and never publish a partial CFG or return table. Keep all previous
source, per-read, image and return-flow bounds unchanged. This increases bounded
preparation work; it is not an observed speedup or proof that closure will fit.
Focused tests must cover each independent boundary, the total pass ceiling,
unchanged ordinary behavior and refusal before image publication, followed by
the same VM build/continuation and actual two-model mmap1 checks.

## Production direction after the November 3 clarification

The [reached-path execution model](reached_path_execution.md) supersedes full
CFG closure and all-site image prewarming as production admission requirements.
The bounded-CFG designs and their retained receipts above describe the earlier
candidate and the explicit checked regression path, not the new demand model.
Source leases, immutable published bytes, exact owners and final retirement
remain mandatory in the new model.
