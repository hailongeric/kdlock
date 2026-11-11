# Kernel8 MM native-context prefix

This is an offline source and linked-disassembly result, with no observed runtime instruction path or admitted auxiliary-context claim. The saved export has 8 source files and 12 exact GNU symbol spans totaling 423054 bytes. I independently checked every source and disassembly size/hash, empty diagnostic file, and before/after source/ELF identity. Manifest SHA256 is `78f6c172d5de54175c2d40459b4915bac2bc8e76fd4b9133b6880086c9e850e1`. Copy-index SHA256 is `80da81847e620b55fcc792f8ee61e1f7d72625526b9b6bd07763c690430fffd0`. The linked ELF is kernel8 Build ID `a33dd4d11d0f0c6649107507e685b6e86e716c1a`, SHA256 `4441e45c27f9300a4cd19739c917458308581472604c3b75d8ffba9fec493be1`. These bytes do not establish live alternative/paravirtual patching or actual workload reach.

The input is `/tmp/kdlock-kernel8-mm-context-20261111-01/export`, with paths below relative to that directory. Existing authenticated `mm/memory.c` supplies the enclosing zap source. This note refines the earlier source-extent proposal and selects no source expansion or capacity increase.

## Exact interval

`source/mm/pgtable-generic.c:283–306` enters RCU before mapping a PTE table. On success it returns with RCU still held. The comments at lines342–361 explicitly require `pte_unmap_unlock` or `pte_unmap` to end the mapping/RCU interval. `pte_offset_map_lock` at lines391–408 calls that mapping helper before `spin_lock(ptl)`. A failed PMD recheck performs both releases and retries.

| Linked address | Emitted operation and obligation |
| --- | --- |
| `ffffffff8181e4a2` | `unmap_page_range` CALL to `pte_offset_map_lock` |
| `ffffffff8184152d` | `pte_offset_map_lock` CALL to `__pte_offset_map` |
| `ffffffff81841237` | `__pte_offset_map` CALL to `__rcu_read_lock`, before the PTL |
| `ffffffff81566f35` | RCU helper loads exact GS `current_task` at `ffffffff84425018` |
| `ffffffff81566f4a` | RCU helper stores incremented nesting at `[task+0x9bc]` |
| `ffffffff81841269` | Later indirect paravirtual CALL inside the open RCU interval |
| `ffffffff8184159c` | CALL to `_raw_spin_lock` with the selected native PTL |
| `ffffffff8276ccf5` | Native spin entry increments GS `__preempt_count` at `ffffffff84425030` |
| `ffffffff8276cd03` | `lock cmpxchg [rdi],edx` attempts actual PTL acquisition |
| `ffffffff8276cd2a` | Contended native spin path calls `pv_ops_lock` while preemption remains disabled |
| `ffffffff818415a9` | Indirect paravirtual CALL after native spin acquisition returns |
| `ffffffff8181e4ba` | `flush_tlb_batched_pending` CALL after successful mapped/locked PTE return |
| `ffffffff8181e4cb`–`ffffffff8181e4ee` | Inline lazy-MMU code reads logical current and increments `[task+0x1570]` |
| `ffffffff8181e89a`, `ffffffff8181e89f` | Normal path CALLs native spin unlock, then RCU unlock |
| `ffffffff8181edbc`, `ffffffff8181edc1` | Flush branch performs the same two releases after its flush calls |

`disassembly/pte_offset_map_lock.txt` also contains mismatch cleanup at `ffffffff818415f8` and `ffffffff818415fd`, followed by retry. `_raw_spin_unlock` calls the paravirtual unlock at `ffffffff8276cea9`, decrements GS preemption depth at `ffffffff8276ceaf`, and can call `__SCT__preempt_schedule` at `ffffffff8276cec8`. `__rcu_read_unlock` can call `rcu_read_unlock_special` at `ffffffff8156feed`. A cut at a release helper is still inside the preceding physical/task context until that release actually completes.

The configuration selects PREEMPT_RCU and plain native spin acquisition here. The emitted plain-spin path changes preemption state. It does not establish an IRQ-disable prefix. The conditional IRQ save/restore source in `pgtable-generic.c:271–280` is not evidence that this x86-64 emitted path executes it. Lazy-MMU enable/disable is another task-associated pair, as documented in `source/include/linux/pgtable.h:205–299`.

## Why GS and handback do not close this interval

The unchanged lowering in `disassem/backend/normal.py:39–58,110–116` replaces only the exact 64-bit `current_task` MOV with logical W. Ordinary GS memory still uses the saved original GS base. `kernel/jit.c:692–713` captures that base with a short physical preemption pin and reenables preemption before arbitration.

If these functions are translated, the RCU helper therefore increments logical W's task nesting while C remains the physically scheduled task. Scheduler/RCU task identity has not transferred. The later lazy-MMU inline accesses also name logical W. A same-mm predicate does not reconcile those task-associated roles.

For preemption depth, an origin captured on another CPU can make translated GS INC/DEC access that origin CPU's storage while physical C executes elsewhere. Pinning the entire client/combiner group to one unchanged CPU removes that spatial difference only. It does not turn W's RCU state into C's state or permit an explicit scheduling wait while the native PTL/preemption interval is open. The single canonical packet transfers source registers and CALL/RET state, not the physical executor's outstanding RCU/native-lock/lazy-MMU obligations.

A first missing-source, indirect-target, instruction-budget or helper frontier can occur after these prefixes. Examples are `81841269` after RCU entry, the spin slow-path `8276cd2a` after preemption disable, or `818415a9`/`8181e4ba` after PTL acquisition. These are static possible cuts, not reproduced runtime exits. Reexecuting the acquire or pretending a Boolean context flag covers them would not preserve the protocol.

## Safe current cut and smallest generic integration

For this demonstrated interval, a native pre-operation cut at the CALL to `__rcu_read_lock` at `ffffffff81841237` occurs before its RCU effect. The enclosing CALL at `ffffffff8181e4a2` is earlier and also avoids this interval. These are available safe cut locations with respect to the shown RCU/PTL/lazy-MMU sequence. The preceding broader MM path still needs its own context review. Stopping only before `_raw_spin_lock` at `ffffffff8184159c` is already too late to avoid the RCU prefix.

The smallest source-boundary integration is an explicit permanent pre-operation frontier for actual generic native context-entry targets, beginning with this configuration's `__rcu_read_lock`. It uses the existing SPECIAL frontier and exact pre-CALL handback without a named MM helper model or changed native MM body. The original W then executes the ordinary context pair and remaining native suffix once. This can truthfully establish a generated prefix. It cannot satisfy the strict generated munmap protected-completion oracle.

Completing that protected range requires additional generic context service, not more text alone. Such a mechanism must retain exact physical C ownership of native RCU/PTL/lazy-MMU state through their matching releases, preserve original source CALL/RET/no replay, prevent ordinary sleepable rwsem pumping or W handback while those physical duties remain open, and define cancellation/failure disposition at every possible cut. The current single-family rwsem runtime and existing private KD spin grant path do not supply a native `spinlock_t`/RCU/lazy-MMU context token or transfer protocol. An object name, a source hash or a same-CPU scope cannot provide those roles. No ownership or progress policy is silently selected in this note.
