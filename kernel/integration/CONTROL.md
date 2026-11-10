# Compiler channel and managed provider workflow

This guide describes connected source through `c6becf81`, preserving the original
UB JIT, KD GS lowering, one canonical S_W and direct MCS node->state lookup.
Compiler control does not execute source bodies. Source functionality, target
application/build, actual publication and returned execution are separate evidence.

## Cold source and task admission

The source provider snapshots exact actual-address regions and retains all module
dependencies under the selected all-dependency immutable-text contract. Every
mutator is excluded from before capture through final native/JIT/feedback use;
module_get alone is no freeze. Version/configuration/load identities, complete
operation boundaries and the current-task GS offset are explicit inputs.

`kd_jit_runtime_create` composes source, image slot, feedback, durable cycle/image
controls and one fd channel. Caller inputs explicitly bound requests, facts,
claims, cycles, images, code/tables/frames, auxiliary bytes and full control-stack
requirement. No deployment count is configured. Used control addresses remain
retained until shutdown and every host identity/history observer ends; finite
capacity covers that retention, not only simultaneous nesting.

The initial parent enters through `kd_jit_runtime_enter_current` before declared
source activity. Managed lifecycle gives each child independent core/pool/auxiliary
backing and task/stack/native holds. Unmanaged tasks remain outside the lane.
Native-provider/runtime users retain immutable configuration through final task
and callback use. [The task guide](README.md) records exact exit and last-observer
duties; [IMAGES.md](IMAGES.md) records source/code/feedback ownership.

## Exchange and retry

[kd_control.h](../../include/kd_control.h) defines ABI1 as nine 64-bit exchange
words. Bounded payloads use [wire.py](../../disassem/wire.py)'s little-endian
schema. One persistent session has one open fd at a time. The channel caches the
exact command input/output/status before copyout. Ambiguous delivery retries the
same sequence, operation and bytes; it never dispatches the completed effect again.
QUERY returns the actual retained exchange without changing it.

[FdTransport](../../disassem/session.py) preserves the in-flight command and raw
reply before decoding, and requires QUERY reconciliation on reconnect. Output
capacity recovery changes only that buffer, preserving original sequence/input.
Parsing failure is not a new-dispatch or guessed-commit receipt. Closing the fd
neither cancels a cycle nor proves drain; nonidle disconnected work retains its
owner and prevents unregister. Whole-session crash/restart reconstruction beyond
this explicit recovery protocol is not implemented.

## Compilation and publication

1. SOURCE_EXPORT (8) returns exact epoch/version/GS regions, typed boundaries, slot
   and nullable current image baseline. `c6becf81` exposes actual slot/base directly
   for `SessionConfig`; equal version bytes are no ownership or retained base proof.
2. CLAIM (1) retains exact keys/incarnations and producer identities. BUILD_START (2)
   validates/retains the expected baseline and returns actual reserved descriptor,
   input/emission/producer identities, code address/capacity and symbols. The host
   cumulatively merges valid same-version observations before discovery/lowering,
   freezing only MERGED candidate inputs.
3. [GNUImageBuilder](../../disassem/image_builder.py) uses explicit cpp/as/ld/objcopy
   paths, bounded scratch/output/diagnostics and time limits. It links at reserved
   code base with entry offset zero, checks ELF target/entry/bounded text, rejects
   unresolved relocations and other allocated/dynamic sections, then compares the
   extracted binary. It loads or executes no source on the host.
4. STAGE_LOAD (3) sends five exact blobs: assembly, C metadata, manifest, machine
   bytes and flat typed metadata. The execmem loader validates source/ABI/table
   correspondence, copies code once and completes executable permissions. Identical
   retry preserves that reservation without a second load.
5. PUBLISH (4) closes roots, drains exact image users, swaps the pointer and completes
   RCU grace. Candidate binding and old-owner retirement match the actual transaction
   and returned old image. ACK (5) separately confirms emitted ordinary observations
   from the exact validated MERGED subset; publication alone is no coverage ACK.
6. END (6) is the explicit host-observers-ended handoff. It releases acknowledged
   records and unclaims uncovered/nonobservation leftovers without discarding them.
   After ending starts only END retry is legal. ABORT (7) applies before publication;
   it cannot undo a committed pointer swap.

Busy retries preserve actual partial progress. Pending facts or compilation alone
do not disable new JIT/delegation; existing source/context/image checks apply.
An empty/closing slot can retain normal persistent local acquisition eligibility.

## Archived shutdown

SHUTDOWN (9) closes new native/build/publication admission, retires the image to NULL
and drains image/native/JIT users before dropping BUILD. A separate controller
FEEDBACK membership retains source descriptions through final channel teardown.
ARCHIVE_CLAIM (10) selects exact remaining facts after source CLOSED and producer
IMAGE users end; no slot SOURCE user may prevent its own drain.

[ShutdownSession](../../disassem/archive.py) writes exact copied facts, source/
producer construction provenance, cumulative knowledge and dispositions into a
fresh bounded archive. Exclusive creation, file fsync and directory fsync precede
its actual SHA256 content receipt. SETTLE (11) validates that receipt and exact claim
keys/incarnations against closed epoch/producer lifetimes, marking SETTLED separately
from coverage ACK. END follows after archive/transport observers finish. Saved
uncovered facts are never labelled emitted or acknowledged merely because saved.

Busy close/destroy retains backing rather than discarding facts, forcing unload
or freeing a live source task. Callback/module/caller-return users remain separate.
Archive durability alone does not reconstruct a restarted session. Deployment
sizes and auxiliary scheduler/IRQ/unwinder proof remain outstanding; retain actual
build/runtime receipts separately from these source and focused-host checks.
