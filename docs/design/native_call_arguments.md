# Native returning calls with explicit argument mapping

This is a general retained-continuation extension on
`codex/unified-lock-queue-mm`, starting from runtime
`a3dc92071351e4858c105c386f80a51a1a2011f9`. Kernel component
`1ab7124abb6140752c1f0bb6e862144d426a3875` remains separate; its v3 Build ID is
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`. No MM caller adapter or body change
is proposed. Public lock acquisition, cancellation, release and downgrade
behavior stays unchanged. This design extends the existing returning-call
transaction; it does not return the critical-section suffix to its origin.

## Observed reason for this step

The `0b33995c5aa8c6f8bab046900b6b3fb00c449719` preparation retry preserves the
262,144-byte text-cache bound and makes progress with smaller optional windows,
but complete ordinary callee closure still does not fit. For
`__do_sys_brk+0x93`, 261,088 cached bytes need another mandatory-prefix plan of
265,777 bytes; `userfaultfd_unregister+0x15e` needs 263,680 after 259,712 cached
bytes. Neither mmap1 model starts; the binding factory stays inactive with zero
bindings. These are preparation failures, not executed MM failures or scores.
The exact failed result SHA256 is
`fed833fdea0e0f37e85ef9b42663d7d0bc348b047c636a35ca8a7282c1c42efe`.

The source graph includes general allocator frontends absent from
`include/kd_service_calls.def`. A bare descriptor for `__kmalloc_noprof` would
change its implicit caller input: the Native bridge's real CALL has a different
return PC. `CONFIG_RANDOM_KMALLOC_CACHES=y` uses that input for cache selection.
Keep the original source CALL word; use a source-proven explicit-caller API for
this interval instead of translating the entire allocator graph.

## Source/API equivalence and limits

Current v3 pristine `mm/slub.c` SHA256 is
`c787ef6eafc90d1bc83b269aefac1db5f95ede0bdc79165500617414e8c64775`;
`include/linux/slab.h` is
`b5122cfc8d8ed4c4660f35e02fb482f07fece7ce581f7bb0c606012c8233779b`.
The current-v3 hash receipt is
`/tmp/kdlock-mm-v3-allocation-source-hashes-20261103.json`.
At `slub.c:5244-5275`, `__kmalloc_noprof(size, flags)` enters
`__do_kmalloc_node(size, NULL, flags, NUMA_NO_NODE, _RET_IP_)`.
At `slub.c:5372-5375`, `__kmalloc_node_track_caller_noprof` enters the same helper
using its explicit arguments. Likewise, the four-word
`__kmalloc_node_noprof(size, buckets, flags, node)` may append its source return
PC for that helper. Preserve the Linux 7 bucket argument; older three-word
prototypes do not apply.

These mappings preserve allocation result and policy, zero-size and large-size
branches, original GFP flags, bucket/node choice, accounting, initialization,
failure behavior and caller-dependent cache selection. They do not promise
identical physical stack or trace metadata: the large-allocation helper traces
its own wrapper caller after allocation, and stack collection sees the actual
Native bridge. This distinction does not change the allocator API result or
policy through the reviewed source. Do not extend this claim to arbitrary
caller-sensitive APIs. In particular, cache allocation has no reviewed public
cache-plus-caller equivalent, and kvmalloc has alignment/fallback semantics that
ordinary kmalloc cannot replace.

## Descriptor and argument contract

Keep `struct kd_service_call_desc` and the existing exported registration API
unchanged. Add a separate version-1 mapped descriptor/registration interface.
It contains the existing logical source descriptor, execution target, execution
argument count (at most six), six bounded argument selectors and zero-required
reserved fields. Selectors can choose a declared source argument, zero, minus
one or the validated source return IP. Reject unknown versions, incompatible
contexts, out-of-range source indices, missing execution targets and nonempty
unused selectors before publishing any part of a registration batch.

Initially mappings require `KD_SERVICE_CALL_BALANCED_ORIGIN`: an ordinary C ABI
operation with no retained spin/preemption pin, no retained RCU interval and
matching enabled IRQ context. Existing scheduling, terminal, spin/RCU ownership
and preserved-register callbacks do not acquire mapping behavior implicitly.
All their identity descriptors and bridge inputs remain unchanged.

The discovery table's six fields continue describing the logical source API.
Its cookie, source target and source arity identify the immutable registry slot;
the translator excludes that declared source callee and emits the existing
returning CALL boundary. No wire version, image requirement, Python discovery
format or generated CALL/RET contract changes are required.

The first production mappings are:

| Logical source API | Execution API | Native arguments |
| --- | --- | --- |
| `__kmalloc_noprof(size, flags)` | `__kmalloc_node_track_caller_noprof` | source0, zero, source1, minus one, source return IP |
| `__kmalloc_node_noprof(size, buckets, flags, node)` | `__kmalloc_node_track_caller_noprof` | source0, source1, source2, source3, source return IP |

Only use a mapping when both exact symbols exist. A present logical symbol
without its required execution counterpart must stop registration explicitly.

### Related cache-allocation identity intervals

Source and exact-v3 configuration review also qualify two ordinary identity
descriptors: `__kmalloc_cache_noprof(cache, gfp, size)` with three arguments,
and `__kmalloc_cache_node_noprof(cache, gfp, node, size)` with four, both WORD
results and `BALANCED_ORIGIN`. Unlike the generic kmalloc frontend, these APIs
already receive their selected cache. Their implicit caller reaches allocation
trace/debug attribution, rather than cache/node/retry/failure decisions.
`slub.c:4840`, `4454` and `4375` pass it to `set_track` at `4449`; wrapper traces
at `5385` and `5397` also retain that attribution distinction. Use the exact
APIs and original size/GFP/cache/node inputs: ordinary cache allocation loses
requested-size handling, while `___slab_alloc` omits required pre/post hooks.

The configuration receipt at
`/tmp/kdlock-mm-v3-config-read-20261103/reply.json` binds the actual build config
SHA256 `7dffb540209d34287f7ece75a6b3635b87dd751179fb7953f92aa2eff9b714aa`.
It includes SLUB debug metadata and initialization on allocation; the reviewed
source still limits this caller-address difference to trace/debug attribution.
Retain that documented limit instead of claiming identical physical traces.
These identity descriptors use the existing registry/bridge path and preserve
all existing context checks; they require no mapping-specific execution mode.

## Transaction, ownership and lifetime

The immutable registry entry retains both targets and the fixed map. Freeze and
pin both source roots before publishing any image depending on the entry. An
active transaction retains the same entry/owner reference until its exact
completion ACK. Closed admission, source/frame drain and zero entry users remain
prerequisites to unregister; target substitution cannot shorten either lifetime.

Prepare the six-word cold execution vector from the untouched source packet
only after the existing FULL-packet, frame/image, root identity/generation,
sequence and actual CALL-word checks succeed. The existing scalar bridge prefix
keeps its offsets; append an execution target and vector before other internal
metadata with compile-time C/assembly offset assertions. Logical `target`,
`packet->ip` and `kd_call_state.target` continue identifying the source API.
Identity calls keep their existing input path. Mapped calls load only their
execution target/vector; do not rewrite or copy the whole packet to impersonate
the alternate API.

O executes the single typed Native interval on its own task stack, with unchanged
context checks, original arguments and validated source return PC. The bridge
captures Native volatile outputs and arithmetic flags before restoring context.
Completion validates the immutable source/execution identities, original source
CALL word, sequence, request generation, O, E and image. E consumes that word
exactly once and resumes the same image immediately after the source CALL.
There is no prefix replay or implicit original-task suffix. A mapped interval
cannot introduce a cancellation decision after acquisition has committed.

## Focused delivery and evidence

1. Implement the bounded map, dual-target lifetime and bridge path while keeping
   identity registration/assembly and the discovery format compatible.
2. Check actual production map validation and marshaling, including invalid
   selectors/version/context, unused words, source return IP and both target
   pins; retain negative controls. Run the existing returning-call checks.
3. Add a general live alternate-target fixture with differing source/Native
   arities. Prove Native arguments, actual O stack/task, source CALL word,
   same E/image resumption, AX/flags and no body replay. Exercise a small bounded
   real allocation sample through the production mappings. Keep the existing
   nine helper and eleven killable/nesting phases.
4. Build and run directly affected checks only on the VM. Then retry the same
   unchanged two-model mmap1 diagnostic once on a fresh frozen source identity.
   All 55 built-in entry images must still be ready before binding activation.
   Do not increase text/image bounds, omit unready entries or alter MM bodies.

The mapping may reduce the observed callee closure; it is not proof that all
closure or lowering gaps are solved. Actual mmap1 acceptance still requires
other-task writer/read-tail completion, a later fresh writer acquisition, actual
syscall completion and final drain. Performance and Nano acceptance are separate
unmeasured gates. Any further unsupported reached operation must remain explicit.
