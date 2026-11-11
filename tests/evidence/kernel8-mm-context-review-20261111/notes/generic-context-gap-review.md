# Generic context gap beneath an outer rwsem episode

Source-only audit of current main and the actual kernel8 export at
`/tmp/kdlock-kernel8-mm-context-20261111-01/export`. Source files were only
read. There were no repository edits or behavioral execution. The existing independent tests are unchanged.
This note identifies mechanisms and open obligations. It selects no new
ownership, release or progress rule.

## What current code actually supports

The canonical state and grant index represent distinct family/mode records
(`kernel/state.h:50–77`, `state.c:390–415`). This is useful shared storage,
not an implemented mixed-family execution lane. Runtime creation fixes one
family and one derived `atomic_spin` value (`runtime.c:370–410`). Exported
typed public entries are filtered to that family (`runtime.c:593–607`).
The episode driver rejects another family's operation before preparation
(`episode.c:820–823`), and root preparation likewise requires that family
(`episode.c:578–588`). The native bootstrap checks the same equality
(`mutex_api.c:154–164`).

The plain-spin/rwlock lane already has exact physical owners, non-sleeping
waits, synchronous owner-release ACK, native preemption depth and original
stack restoration. `native_entry.c:138–178` reconciles W's local preemption
count with open atomic grants. `include/native_resume.S` restores the source
stack/frame chain before the final normal `preempt_enable`. Those facilities
are selected by the root's fixed atomic lane. They are not a native PTL
service under a sleepable rwsem runtime.

The distinction matters in control code: `episode.c:173–196` may schedule
when the root owner-progress configuration is sleepable. Owner tracking
rejects a batch whose atomic flag differs from that root
(`owner_progress.c:34–54`). `jit.c:607–655` constructs each call's family,
physical mode and atomic requirements from its driver. Removing only the
family check would leave these control paths inconsistent with a held PTL.
The maintained design explicitly excludes mixed families from the current
plain-spin lane (`01_lock_protocol.md:610–647`).

## Actual first context effects

The exported native path enters RCU before acquiring the PTL:

- `mm/pgtable-generic.c:283–305`: `__pte_offset_map` enters RCU before
  reading/mapping the table and exits RCU on its failed-map branch.
- The successful `pte_offset_map_lock` path calls that helper first, then
  takes `spin_lock(ptl)` and validates the PMD. Retry uses
  `pte_unmap_unlock` (`pgtable-generic.c:391–409`).
- `include/linux/pgtable.h:101–118`: `pte_unmap` performs the matching RCU
  release, including the selected non-HIGHPTE form.

Fresh kernel8 disassembly makes the physical effects concrete:

- `_raw_spin_lock`: GS `__preempt_count` increment at
  `0xffffffff8276ccf5`, native lock-word CMPXCHG at
  `0xffffffff8276cd03`, and the indirect paravirtual slow-path CALL at
  `0xffffffff8276cd2a` after preemption has already changed.
- `__rcu_read_lock`: actual current_task load at
  `0xffffffff81566f35` and task nesting-field write at
  `0xffffffff81566f4a`.
- The source CALL to `__rcu_read_lock` is at `0xffffffff81841237`.
  The later PTL `_raw_spin_lock` CALL at `0xffffffff8184159c` is therefore
  too late to serve as the first unchanged-context frontier.

Current native-frontier export automatically covers the callable Linux
rwsem targets (`runtime.c:588–648`). It does not automatically add RCU,
preemption or native spin API targets. The normal backend must not simply
translate these bodies and treat GS substitution as physical context:
general GS accesses use origin GS, while recognized current_task reads use
logical W. Neither changes physical executor C's scheduler/preemption/RCU
state. This is explicit in `02_jit_contract.md:274–286`.

## Smallest generic correction versus full continuation

The smallest correct boundary mechanism is a generic native-context
pre-operation cut before the first RCU/preemption/IRQ/lock effect. For this
actual image a cut before the RCU operation is required, not only before the
later spin slow path. Existing exact source-site SPECIAL metadata can
represent an inline pre-effect cut; exact normal API entry metadata can
represent a callable one. This must identify a generic API/context boundary,
not assign special execution semantics to `pte_offset_map_lock`, zap or
another MM helper. Native W then resumes at the first unexecuted instruction
with the same S_W and outer grant. This correction supplies prefix evidence
only and does not complete the full generated protected-MM goal.

Continuing through that boundary requires generic context service composition:

1. **Entry and exact completion.** Resolve the actual API before its CALL or
   inline context effect. Apply it once on the physical actor that will run
   the protected source. Preserve original arguments, result/flags, CALL word
   and post-operation cursor. Use the existing source packet and typed
   operation bridge, not a copied packet or another source executor.
2. **Separate physical context custody.** Retain each actual native lock,
   preemption/IRQ/BH/RCU scope and its physical task/CPU, phase and matching
   release. A logical grant or numerical depth is not a replacement for
   those records. Outer rwsem custody remains separate. The present fixed
   `owners.atomic_spin` flag is not this ledger.
3. **Control legality.** While a native PTL/preemption scope is open, every
   control path must avoid the sleepable rwsem pump and sleeping allocation.
   It must service required releases without starting unrelated borrowed
   work under that physical scope. Reusing existing spin polling/ACK machinery
   is possible only after its per-task/per-frame composition is explicit.
4. **Release and lifetime.** Match the exact native lock/context operation,
   not just its object address. Release on the actor that owns the physical
   obligation, and preserve its control/source/native-stack/code backing
   through final ACK and callback return. `mmgrab` retains the mm allocation,
   not by itself the PTE page, derived PTL pointer or a read-side critical
   section. The existing `pte_unmap_unlock` ordering and RCU duty remain
   necessary. Current queue-only deferred-exit storage cannot be reused as
   permission to exit with these physical duties still open
   (`task_state.c:229–242`).

## Unimplemented escape contract for a live physical scope

A later ordinary missing CALL, unsupported instruction or resource exit is
allowed by the bounded compiler contract. Current `episode.c:669–700`
materializes state and transfers it to native W immediately. The actual
path has indirect/flush calls after context entry, so an escape inside the
scope is a concrete obligation, not a hypothetical whole-kernel question.

The existing requirements already settle no replay, no early physical unlock
and native W handback at the first unexecuted instruction. They do not need a
new user decision. The native-context implementation is missing. Two generic
design directions need distinct proofs; this audit does not select a new one:

- **Retain physical C and service matching native W releases.** W receives
  canonical source authority at the exact first unexecuted instruction,
  while C retains its actual PTL/context duty. W requires its own valid
  local execution context, and each matching native API release must route
  to the retained physical actor with exact ACK. Native unmodified lock
  words do not already provide the KD release-owner bridge. C must retain
  a legal CPU/progress route while W executes its suffix; the existing
  all-atomic fixture progress assumptions do not prove this mixed route.
  RCU must retain the original read-side duty for the pointer's lifetime.
- **Enter only a context interval whose completion/escape routes are already
  established.** Before entering, establish every allowed exit from the
  bounded generated region, including ordinary misses and resource exits.
  A contract that merely promises no miss does not implement the existing
  first-unexecuted-handback requirement. If the interval cannot be admitted,
  the valid result is the generic pre-effect native handback above, which
  remains a prefix and cannot be promoted to full protected completion.

Following the existing retained-physical-owner pattern is an implementation
direction consistent with those selected invariants, not evidence that its
native-context progress proof already exists. A proposal that instead delays
an otherwise required escape or moves CPU/task context custody would introduce
a real contract choice. This note does not presume such a change is wanted.

Releasing the PTL early, dropping RCU and reacquiring on W is not an existing
valid route: it changes the native critical interval and can expose mutable
page-table state between already-performed source effects. Copying C's IRQ
flags to W or changing a depth counter does not transfer CPU-local context.
Likewise, starting a new RCU section on W is not by itself proof for a
pointer acquired under C's earlier section. The exported `rcupdate.h:801–824`
explicitly permits callbacks alongside new read-side sections. A real
transfer/preservation argument is required, not assumed from overlap.

## Narrow next implementation boundary

First make the generic pre-context boundary explicit and preserve actual
frontier evidence. To advance full MM execution beyond it, specify the chosen
cross-task escape/release protocol and physical actor progress while an
inner native scope remains live. Then compose dynamic family/context
handling, exact actors and preallocated capacity with the existing packet,
operation and release mechanisms. The new proof must include a deliberate
ordinary miss while holding the inner scope and exact native continuation,
followed by matching context release and final retirement. Ordinary MM source
and the one JIT/GS backend stay unchanged.

Same CPU, same mm, original GS, a successful syscall or an image publication
alone establishes none of the missing physical context/escape properties.
No performance, broad mixed-family, IRQ/BH/NMI or context-equivalence result
is supplied by this source audit.
