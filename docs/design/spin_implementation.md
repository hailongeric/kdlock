# Spin implementation: KD, TCLock and Linux Native

This guide follows storage and the ordinary spin path. [Lock protocols](lock_protocols.md)
defines exclusion and handoff; [register ABI](../JIT_REGISTER_ABI.md) defines JIT state.
All measurements belong to their recorded source versions in [benchmarks](../../bench/README.md).

The same KD engine also serves [rwlock writers](rwlock_implementation.md). Their
ABI3 prelude acquires writer admission before dispatch; the count and embedded
gate belong to a separate 128-byte object, not the four-byte spin object below.

## Source paths

| Backend | Caller | Implementation |
| --- | --- | --- |
| Linux Native | `spin_lock/unlock` | Captured kernel `kernel/locking/qspinlock.c` and architecture/PV helpers |
| TCLock | `komb_spin_lock/unlock` | [komb.c](../../tclock_backend/komb.c), private [spin components](../../tclock_backend/spin/) |
| KD | `KD_SPIN_DIRECT_LOCK/UNLOCK` | [kd_spin_direct.h](../../include/kd_spin_direct.h), [spin components](../../kernel_module/spin/) |

The three workload arms share payload, post-lock work, timing and verification.
Each target lock belongs exclusively to its backend; equal word size does not
make the node pools or unlock protocols interchangeable.

## Storage and cachelines

Sizes below are from the captured x86_64 build; source assertions protect required offsets.

| KD object | Size/count | Allocation and lifetime |
| --- | --- | --- |
| Lock word | 4 bytes | Workload owns it until all callers drain |
| Scheduling node | 128 bytes, four/CPU | Provider's aligned per-CPU array; reusable after queue handoff |
| Continuation | 704 bytes, twelve/CPU | Producer-owned stable record; outlives node reuse |
| Embedded execution frame | 648 bytes | Inside the continuation; not a second allocation |
| Private register packet | 168 bytes | Inside frame; shared by waiter, combiner and virtual child |
| Continuation/wait region | 20 KiB/CPU | Low 12 KiB for records, high 8 KiB for pinned waiter stack |
| Stack header plus records | 8512 bytes | Inside the low region |

NUMA-on initialization requests the CPU's node with `vzalloc_node`; allocator
fallback is allowed. A bounded CPU-dependent 64-byte offset distributes the
continuation stack within the same low region. The maximum current offset is
3776 bytes; all twelve records still end below the wait stack. Request paths
perform no extra allocation or offset calculation. Teardown frees the original
base recovered from the wait-stack top.

The scheduling node's first line contains links, CPU/node identity, execution
pointer and prepared prefetch addresses. The second line isolates `completed/locked`
notification bytes from successor link writes.

The aligned frame begins with a 40-byte header and IP/SP/BP at offsets 40/48/56.
Request identity, entry ABI, packet/depth/frame state and the continuation triple
therefore share one cacheline. Virtual R15..R11 backing occupies offsets 64..96
in the next line. Packet reference, origin GS, logical task and parent share
offsets 208..232. Cold lock ledgers remain separate. Linux `pt_regs` is unchanged.
The ABI3 `rwlock_admitted` bit shares the existing queue-tag byte and does not
move the header, packet or provenance fields.

Reservation takes the next record. Retirement only collapses the contiguous retired
top; it never moves live records or fills holes below them. Only the allocating
CPU changes top. Remote native cleanup publishes retirement after pop; the producer
reclaims on its next reservation/release. Exhaustion before publication uses native
KD MCS with the existing ticket. [Frames](frames.md) gives the ownership rules.

## KD acquisition and delegation

1. The paired direct caller pins and reads its per-CPU heat scalar. The cold path
   tries an inline CAS; its failure continues through pending/MCS without a second
   initial CAS. Successful native ownership uses locked byte 5.
2. The hot clobber entry captures IP/SP/BP. Fast acquisition records the owner and
   avoids request/frame preparation. Contention enters the helper, reserves a ticket
   only when required and checks translation/backend/context/resource eligibility.
3. Eligible waiters prepare the shared record, switch to the 8 KiB wait stack,
   release-publish their queue node and poll. Native nodes have no execution frame.
4. A queue-head combiner holds the same KD word and runs ready bodies through one
   resident C loop. Simple roots use direct batch helpers and one source lease;
   complex FULL exits enter the generic frame dispatcher.
5. Completion validates the exact terminal unlock and continuation, pops the frame,
   then publishes DONE. The physical waiter reads all restore state before reclaiming
   its continuation and ending the original pin.

Normal clobber COMPLETE needs only IP/SP/BP. FULL materializes current logical GPRs
for control/native recovery. Compiler-owned caller spills remain live on the
waiter's original stack; clobber does not mean the body has no stack or register
backing accesses. Nested spin uses its own child frame/ticket while aliasing the
root packet. [KD locking](locking.md) covers early unlock and exact native ACKs.

Unlock always enters the generic broad-clobber endpoint. Byte-5 native ownership
uses its short release path; delegated/ticketed ownership follows the existing
ledger/ACK route. Current heat is never used to choose which acquisition to unlock.

## Batch and NUMA selection

Default `KDLOCK_NUMA=1`, `KDLOCK_SPIN_BATCH=1024`; the compile-time body limit accepts
1..1024. A separate NUMA scan budget begins at the configured batch value and is
consumed independently. The code checks exhausted scan budget before dependent
successor reads. Native/IRQ nodes and unsupported queue boundaries stop delegation.

Local eligible successors can stay in the batch; remote runs are deferred without
rewriting already-correct links. Deferred remote waiters receive priority at final
handoff. The remote chain is reattached before ownership transfer.
A temporarily empty successor link can be rechecked with at most eight PAUSEs;
with a deferred remote chain, this refill is allowed only before body 128.
After that grace, an empty link ends the batch and the deferred head receives
handoff. Already-linked work retains the configured 1024-body maximum. This
amortizes short-queue/socket handoffs while bounding added refill opportunities;
it does not wait indefinitely for a producer or inspect a node after wake.
These work bounds do not prove starvation freedom.

## Current KD prefetch strategy

[spin/prefetch.inc](../../kernel_module/spin/prefetch.inc) supplies three modes:

| `spin_prefetch` | Behavior |
| --- | --- |
| 0 | No request hints |
| 1 | Consumer reads the live frame/task/packet to discover addresses |
| 2, default | Producer records addresses and bounded stack coverage before publication |

For a known-live successor, mode 2 issues write-prefetch hints before executing
its predecessor. MINIMAL covers three frame/packet lines: hot header plus IP/SP/BP,
provenance/reference line, and the adjacent five virtual GPR backing slots.
FULL additionally walks its actual 168-byte packet at 64-byte steps. Complex
requests also hint the three lock-ledger arrays.

The producer verifies SP against the retained logical task's stack and records
SP-8 plus up to four upward addresses: SP, SP+64, SP+128, SP+192. Those lines cover
the virtual CALL word and measured hash locals/counters; hints never become an
alternate executable SP or grant admission. Mode 1 retains its narrower SP/SP-8
stack hints. All node-based hints stop before wakeup or outer release can permit
node reuse. Caller stack, queue header and JIT image accesses are distinct from
minimal frame information; hint counts are not measured cache misses.

## TCLock stack delegation

TCLock preallocates per-CPU nodes and an 8 KiB shadow stack. Queue publication saves
the real caller RSP. Its trampoline saves six callee-saved GPRs and switches to
that shadow stack. The combiner switches onto a waiter's original stack and runs
native body instructions; unlock can jump directly to the next waiter with WWJUMP.
There is no KD packet, translation registry, generated body or daemon in this arm.

NUMA selection defers remote waiters and prefetches six caller-stack addresses at
64-byte intervals. Completion and previous-waiter wakeup retain upstream order.
The configured batch value is 1024; its zero-based WWJUMP counter can execute
1025 bodies. The current comparator does not truncate batches on `need_resched()`.
Callers pair preemption protection; queue waiting polls and IRQ checks are disabled
for the selected ordinary IRQ-enabled task-context workload.

The port preserves the actual C inline-assembly stack switch. Private components
stay in one translation unit; [provenance](../../tclock_backend/README.md) retains
immutable upstream files and an expanded-source adaptation diff. Spin delegation
counts are intentionally unmeasured, so data/drain success cannot supply a share.

## Linux Native path

The Native arm calls the original kernel spin functions without a lock provider.
The captured kernel is SMP, non-PREEMPT_RT and includes paravirtual qspinlock
support. The benchmark's required `nopvspin` boot policy selects the native path.
Architecture fast acquisition CASes the native word; contention
uses bounded pending followed by per-CPU MCS tail publication and acquire handoff.
The ordinary raw-spin contract pairs preemption protection and leaves IRQ/BH state
unchanged. No other task's critical section is delegated.

PV stealing and PV waiting/kicks are disabled in this boot. Kernel instrumentation
and runtime patching remain part of the Native arm. Verify build/config/live
identity and [boot selection](../PROJECT_GUIDE.md#native-qspinlocks-in-the-vm)
separately; historical samples may use the earlier PV policy.

## Verification boundaries

Review actual built trampolines and source/workload ABI; check business results,
IRQ/preempt state, every worker/node share and final queue/frame/owner drain.
Returned-body counts establish KD JIT where required. Flat cycle/IP samples locate
execution work, but do not measure remote-memory latency or establish a cache
cause. See [tests](../../tests/README.md), [runner](../../bench/tclock_compare/README.md)
and [performance status](../PERFORMANCE.md) for selection and acceptance.
