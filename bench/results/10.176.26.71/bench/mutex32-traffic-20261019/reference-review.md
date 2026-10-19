This source review describes runtime revision `ba98937`, which retains the
fetch-add change from `113b317` and the subsequent inline pin guards. It records
code facts and lifetime reasoning; it adds no throughput measurements.

The required lifetimes are distinct:

- **Invocation reference:** acquired before node reservation/publication in
  [kd_mutex.c:191](../../../../../kernel_module/kd_mutex.c#L191), stored in the
  node at line 264, and released after node/packet restoration at line 295. The
  clobber completion path transfers that same reference through `node->aux`
  because the original C frame can be overwritten; it puts the reference only
  after preserving the return state and releasing the node in
  [clobber.inc:6](../../../../../kernel_module/mutex/clobber.inc#L6).
- **Physical owner reference:** an immediate successful gate acquisition before
  node reservation transfers its invocation reference directly to the owner
  (`kd_mutex.c:203`). A queued
  acquisition takes a separate owner reference in
  [queue.inc:101](../../../../../kernel_module/mutex/queue.inc#L101). Synchronous
  unlock borrows that existing reference, verifies the current physical owner,
  and puts it after physical and gate release (`kd_mutex.c:327`). It needs no
  temporary lookup reference.
- **Frame/ACK lifetime:** a batch borrows its enclosing invocation reference,
  rather than acquiring one reference per frame
  ([combiner.inc:10](../../../../../kernel_module/mutex/combiner.inc#L10)). Early
  outer release drops the owner reference while batch work can continue
  (`combiner.inc:154`). Native handoff can retire/reuse the waiter node before
  owner ACK and frame completion (`combiner.inc:355`). The batch source lease
  remains through the final ACK/pop (`combiner.inc:277`, `543`); it is separate
  from the auxiliary reference and is unchanged.

`waiter_count` is an exact origin-side balance, not an auxiliary lifetime
reference or queue publication barrier. The tail exchange precedes waiter entry;
the originating waiter decrements the count after observing completion/native
handoff, or after finishing its combiner role
([waiter.inc:25](../../../../../kernel_module/mutex/waiter.inc#L25), lines 38,
45 and 80; [queue.inc:66](../../../../../kernel_module/mutex/queue.inc#L66)).
An invocation therefore exists before waiter entry and after waiter exit. Empty
queue fields cannot establish that all invocation, owner and frame users ended.
The auxiliary layout keeps `waiter_count` at offset 192 and `refs` at offset 200
on the same cache line; both remain exact shared atomic fields
([kd_mutex_aux.c:365](../../../../../kernel_module/kd_mutex_aux.c#L365)).

The implemented fetch-add path uses permanent, directly indexed table storage.
A successful LIVE pin performs one atomic increment, including a pin from LIVE
zero before retirement. Negative BUSY/FREE observations retain a counted rejected
pin until an ordinary put: publication can turn that pin into the last LIVE
reference. Additive publication, rollback and retirement preserve these counts.
Only a retiring put that wins the zero-to-BUSY CAS may inspect protocol fields
and retire the slot; a delayed final CAS may safely reserve a later empty generation.
The post-pin key check and read-only observation sequence checks remain intact
([kd_mutex_aux.c:51](../../../../../kernel_module/kd_mutex_aux.c#L51), lines 136,
196 and 231). No registry lock, RCU, per-operation allocation or caller cleanup
was introduced. Provider teardown still stops/joins callers before freeing the
table (`kd_mutex_aux.c:383`).

The inline change preserves those RMW and lifetime boundaries. `try_ref` and
`find_ref` are explicitly inline; the common get accepts exactly old LIVE counts
`0..INT_MAX-1` with one unsigned comparison. All remaining positive encodings and
excessive negative counts still fail closed. The put shortcut accepts exactly
old counts `2..INT_MAX`; larger valid LIVE counts, negative pins, underflow and
the last-reference CAS keep their original handling. The actual-code fixture
checks these boundaries, original RMW counts and lifecycle interleavings; its
driver contains 20 mutation controls
([mutex_aux_fixture.c](../../../../../tests/unit/mutex/mutex_aux_fixture.c),
[test_mutex_aux.py](../../../../../tests/unit/mutex/test_mutex_aux.py)). Test
results belong to the VM validation evidence, not this static review.

The archived fetch-add ELF is
`fetchadd/profile/pipe/build/kdlock_km.ko`, SHA-256
`5931ef7b1ea645c2202968b96811ae2500c766aee67df891959afe35d184e514`.
[Inspection metadata](fetchadd-reference-code.json) and
[disassembly](fetchadd-reference-code.txt) show an outlined `try_ref`, two call
sites from `get`, and a common pin path with a 62-bit mask, two condition-code
sets, an OR and a sign branch after `lock xadd`. This is evidence for removing
helper calls and simplifying guards. It does not measure cache-line transfers,
prove a throughput gain, or establish a ceiling on reference-related cost:
coherence stalls may also change waiting and batch timing outside these symbols.

The lifetime reasoning rules out two local substitutions. A combiner cannot
bulk-put awakened waiters' invocation references at batch completion: those
origins can still be in `waiter_exit` or packet restoration after the combiner
has finished. Safe transfer would require an explicit completion/ownership
record or an additional acknowledgement. A persistent per-CPU reference would
prevent automatic generation retirement and exact idle detection until an
eviction policy released it. Caching only the permanent slot pointer grants no
generation lifetime; a later operation must still validate the key and acquire
its exact pin. Neither substitution removes the required ownership work without
changing the protocol. The cached outer-hint experiment was measured separately
and rejected; it is absent from `ba98937`, and its comparison numbers are reported
with the workload results.
