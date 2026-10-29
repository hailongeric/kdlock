# Native kernel critical-section semantic map

This is an analysis before implementation, based on maintained KD commit
`24b7a80591a3c8367398cc7375ae0c5952069bfb` and the unpromoted mutex candidate
`2dbcd7afbf141dd63dcf0086b65fd0da4b32d6f7`. The latter changes waiter scheduling
and eligible ownership transfer; it does not establish general kernel API
replacement. Native references are Ubuntu `linux=7.0.0-38.38`, upstream 7.0.14,
and existing objects from `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`.

The [fixed audit](../../bench/results/10.176.26.71/tests/kernel-cs-semantics-20261030/README.md)
records exact file hashes, native source lines, object offsets and separate
implementation versions. **Verified** below means inspected source/object
behavior. **Observed** means an existing named receipt, not a new run.
**Candidate** means a semantic feasibility inference requiring integration and
execution evidence. No runtime changes, builds, tests or timing accompany this
analysis. The normal kernel still has the mmap backend disabled.

## Decision rule

Replace a lock's API only after binding its entire object lifecycle and every
participant to one protocol. KD and Linux queue encodings, ownership records and
layouts are not interchangeable, even where a spin word has the same size.
An existing native call also lacks KD's compiler clobber-entry agreement unless
its source call shell is adapted. Arbitrary binary symbol redirection is not a
substitute for that agreement.

Within a correctly bound object, delegate the paths whose operations and context
are supported. A conditional difficult branch does not justify rejecting the
other paths. If execution reaches an operation requiring the original task,
retain the completed prefix and continue at the exact native position under
the correct physical ownership. Never replay effects. Reads under rwsem and
rwlock remain local; an exclusive spinlock or mutex protecting a read-only query
can still delegate that query.

The permanent [syscall testing contract](../BENCHMARK_WORKLOADS.md#permanent-testing-constraint)
requires unchanged native bodies and surrounding semantics. The existing
function-substitution adapters are useful scoped evidence but do not establish
that stricter form of replacement. The current MM integration remains local;
the possibilities below do not authorize reviving operation-specific MM bodies.

## What is actually observed as contended

The real-API catalog deliberately shares the objects listed below. Its retained
returned-JIT counters establish execution of the scoped adapters, not a profile
ranking every lock in an unchanged application. For example, the frozen
[pipebytes n128 audit](../../bench/results/10.176.26.71/bench/catalog-linux70-trusted-20261028/pipebytes-query-n128/audit.json)
has 19 returned-JIT and two local KD points, with 17,776,429 matched completions.
That is older provider evidence, not a real-API run of `2dbcd7afbf141dd63dcf0086b65fd0da4b32d6f7`.

There is no current Linux 7 lock profile of the exact will-it-scale targets.
Consequently `mmap_lock` is the primary shared-mm contention candidate from the
call graph; PTLs, anon-vma, allocator and folio locks must not be reported as
measured hotspots. The existing actual-MM experiment changes only `mmap_lock`
for shared 4 KiB device mappings. Its separate diagnostic proves a sleeping
writer chain in that test; its 42 timing points do not measure `mmap1`, and
Native wins at all 21 matched counts. The private-fault experiment instead
changes `mf_mapping.lock`, a private backing rwsem for Native/KD (TCLock uses
its separate rwlock); actual `mmap_lock` and page-table locks remain Native.

Pinned will-it-scale reference `75f66e45697e6f5f49c33dd950c4e6b289198f8f`
distinguishes two workloads:

- [`mmap1`](https://github.com/antonblanchard/will-it-scale/blob/75f66e45697e6f5f49c33dd950c4e6b289198f8f/tests/mmap1.c)
  maps and unmaps an **untouched 128 MiB anonymous private range**. Its mmap-lock
  operations are writers, not read-side page faults.
- [`page_fault1`](https://github.com/antonblanchard/will-it-scale/blob/75f66e45697e6f5f49c33dd950c4e6b289198f8f/tests/page_fault1.c)
  also writes one byte per page before unmapping. It includes mapping writers,
  fault paths and teardown; it is not isolated fault latency.

Shared-mm threads and independent processes are different contention topologies.
`MAP_PRIVATE` does not give each thread a separate mm. Configured THP support
does not prove a particular run used huge pages; fault type, runtime policy and
actual lock addresses still need attribution.

## Selected real-API critical sections

Native paths/lines in this table refer to the captured Ubuntu source. Full
participant lists and exact emitted call sites are in the fixed
[real-API audit](../../bench/results/10.176.26.71/tests/kernel-cs-semantics-20261030/real-api.md).
None of the seven existing adapters is an all-users conversion.

| API and exact native lock | Protected interval and mandatory work | Delegation and replacement assessment |
| --- | --- | --- |
| OFD GETLK: `file_lock_context.flc_lock`, spinlock | `fs/locks.c:1026–1045`, `posix_test_lock`: owner/type/range/list checks and conflict-result copy. | **Candidate:** ordinary callback-free exclusive query can delegate. Expiry and owner callbacks are conditional; preserve a reached prefix and exact unlock/callback/retry path instead of rejecting every query. Current adapter uses the actual native spin storage with frozen OFD records and excludes callbacks. Conversion must also cover lock mutations, leases, teardown and observers on that object. |
| F_SETFD: `files_struct.file_lock`, spinlock | `fs/file.c:1278–1283`, `set_close_on_exec`: current/files lookup before lock; bitmap set or test-and-clear inside. | **Candidate:** small task-context writer with no identified mandatory task/mm service in the body. Native object uses ordinary BTS/BT/BTR, not LOCK-prefixed instructions. Current adapter uses native spin storage but excludes close/dup/resize; those participants and initialization must use the same protocol in a real conversion. F_GETFD is a separate RCU lookup. |
| FIONREAD: `pipe_inode_info.mutex`, mutex | `fs/pipe.c:626–635`, `pipe_ioctl`: ring head/tail, buffer lengths and sum; `put_user` is after unlock. | **Candidate:** exclusive query can delegate; no mandatory user fault, sleep or IRQ transition in this branch. The existing KD adapter uses a private mutex and copied loop. Convert pipe read/write/splice/open/close/fasync/resize participants too; their conditional fault/wait paths may stay local. |
| F_GETPIPE_SZ: same pipe mutex | `fs/pipe.c:1436–1450`, `pipe_fcntl`: selected GET branch loads capacity and shifts by page size. | **Candidate:** protected GET branch can delegate. F_SETPIPE_SZ's accounting, allocation and IRQ-sensitive resize are conditional sibling work, not reasons to reject GET. Keep the original command switch and route reached difficult operations; current adapter specializes it away. |
| SEEK_SET/SEEK_END: `file.f_pos_lock`, mutex | Acquisition in `fdget_pos`, `fs/file.c:1262`; returns into `ksys_lseek`, `fs/read_write.c:395–409`; indirect tmpfs llseek, bounds/offset update; cleanup calls `__f_unlock_pos`, `fs/file.c:1269`. | **Candidate body, unvalidated continuation:** the selected arithmetic/store has no identified mandatory CPU/mm operation. The root RET across functions, indirect filesystem method and cleanup unlock need an exact supported graph. The copied locally paired adapter does not prove it. DATA/HOLE's inode rwsem and CUR's `f_lock` are conditional. All fd_pos users of this file must share the conversion. |
| UTS: global `uts_sem`, **rwsem** | `kernel/sys.c:1370–1372` uname read; host/domain writers `1449–1455,1503–1509`: namespace lookup, copy/zero, **in-lock `uts_proc_notify()`** on every successful setter. | **Readers local. Candidate writer prefix:** copy/zero can potentially delegate, then notify and remaining suffix run on the waiter if needed. The current private KD rwlock, fixed-length body and notification-after-unlock adapter do **not** preserve the native lock type, global scope or ordering. A faithful conversion needs KD rwsem, every UTS/sysctl/namespace participant and unchanged notification placement. |
| Xattr get: `simple_xattrs.lock`, **rwlock** | `fs/xattr.c:1289–1301`, `simple_xattr_get`: rb-tree search/strcmp, size/error or kernel-buffer copy. | **Local shared reads only**, as required; all 168 KD catalog points are local NO_JIT. Set/add writers (`1331–1405,1513–1518`) are separate candidate tree-update sections; allocation is before write lock. They were not measured. Current private-lock/frozen-tree binding does not convert concurrent setters/list/free. |

For plain task-context setfd/OFD and pipe queries, compatible executor/origin
state is feasible in principle. That is not proof of arbitrary externally
IRQ-disabled callers. UTS notification's internal wake/IRQ locks and broader
pipe/seek participants require their own context handling; an initial missing
CALL is not a permanent guarantee that later learning will keep them local.

## MM critical sections

The fixed [MM audit](../../bench/results/10.176.26.71/tests/kernel-cs-semantics-20261030/mm.md)
maps the native sites and configuration. These rows distinguish API replacement
with local execution from delegated execution; neither implies a performance
gain. Rwsem read bodies never delegate.

| Lock and exact native section | Type / native semantics | Current replacement and delegation verdict |
| --- | --- | --- |
| `mm->mmap_lock`: `vm_mmap_pgoff`, `mm/util.c:579–583`, covering `do_mmap` and `mmap_region` | Rwsem **killable writer**. Address selection, VMA merge/allocation, maple/accounting updates. Population and userfault completion are after unlock. | Existing enabled adapter can replace the backend **locally**. No current delegated killable writer. Future delegation requires cancellation/phase commit and exact reached helper/context boundaries. File callbacks and populate branches are not mandatory anonymous mmap1 work. |
| Same lock: `__vm_munmap`, `mm/vma.c:3266–3272`; `vms_complete_munmap_vmas:1311–1350` | Killable writer; successful mapped-range removal **downgrades to read** at1320, then teardown, then read-unlock1347. Error/empty-range releases differ. | Local KD adapter preserves the protocol. Prepared delegated writer's no-downgrade/lexical contract cannot cover this path. Need atomic transfer into a local read phase and exact callee release routing; never change killable to ordinary acquisition merely to enable JIT. |
| Same lock: fault fallback `lock_mm_and_find_vma`, `mm/mmap_lock.c:442–544`; `arch/x86/mm/fault.c:1370–1413` | Rwsem read-try/killable read, possibly released inside fault handling on RETRY/COMPLETED. Stack growth drops read, takes killable write, revalidates, then downgrades. | **Reads local, never delegated.** Existing local adapter is applicable within its validated scope. Stack growth is a distinct writer opportunity requiring cancellation/downgrade support; it is not an atomic read-to-write upgrade and not mandatory for new anonymous ranges. |
| Per-VMA `vm_refcnt`/`vm_lock_seq` and mm sequence/wait state: `vma_start_read`, `mm/mmap_lock.c:212–289`; `__vma_start_write:139–164`; `include/linux/mmap_lock.h:620–637` | Refcount/sequence/RCU/rcuwait protocol, **not rwsem**. Readers retain lifetime; writes exclude/drain readers and release collectively when the mmap writer sequence ends. | No ordinary KD lock substitution. Leave this protocol intact when converting mmap_lock. A delegated outer writer must preserve real origin reader-drain/wait and sequence ordering; a local read path remains local. |
| PMD-table lock: `pmd_install`, `mm/memory.c:438–461`, `ptdesc->ptl` or configured upper-level lock | Spinlock: recheck absence, account initialized table, publish, unlock. Allocation precedes this interval. | **Candidate narrow interval**, unvalidated. No mandatory TLB flush for absent-table publication; x86 smp_wmb is a compiler barrier. Actual object includes paravirt calls and LOCK accounting, so exact callee graph still matters. Convert all users and table lifetime, not only this call. |
| Split PTE lock: zero-page and allocated-page branches of `do_anonymous_page`, `mm/memory.c:5268–5354` | Exclusive spinlock even for a userspace read fault. Revalidate absent PTE, stable mm/userfault state, then install; allocated-page branch also updates rmap/LRU/accounting. | **Candidate prefixes**, unvalidated. Fresh accepted installs have no old translation to invalidate. Zero-page/read and allocated-page/write branches differ; no universal folio lock or userfault callback is mandatory. Rmap/LRU nested context and prior PTE-map/RCU lifetime need support. |
| PTE lock: present access update, `handle_pte_fault`, `mm/memory.c:6355–6376` | Spinlock: revalidate PTE, dirty/young/access update, unlock/unmap. COW is a separate branch. | Candidate simple update subject to architecture helper/context proof. Do not treat all present-entry updates as either fresh installs or full COW replacement. |
| PTE lock: accepted COW replacement, `wp_page_copy`, `mm/memory.c:3846–3914` | Spinlock: revalidate, **clear/flush old PTE before new PTE**, rmap update, unlock. Allocation/copy and notifier start precede this reacquisition; references/notifier end outlive it. | No current general delegated support. A prefix may delegate before a proved native flush boundary. The actual local TLB operation cannot run on an arbitrary combiner merely because IF matches. This is mandatory on the accepted replacement branch, not every fault or untouched mmap1 operation. |
| PTE lock: `zap_pte_range`, `mm/memory.c:1931–1975` | Spinlock: pending flush, lazy-MMU mode, clear entries/rmap/rss, conditional force-flush **before unlock**. Gather freeing and cond_resched follow unlock. Distinct PMD trylock can nest. | No current general delegated support. Empty-entry and useful prefix paths should remain candidates; populated flush, nested locks, RCU/table retirement and physical context need exact transitions. Never move the in-lock flush or post-lock scheduling boundary. |
| Folio `PG_locked`: `filemap_fault`, `mm/filemap.c:3576–3637`; `folio_unlock:1505` | Atomic bit + hashed sleeping wait protocol, **not mutex/rwsem**. Callback can return VM_FAULT_LOCKED to a different caller; completion can unlock in interrupt context. | No direct KD mutex substitution: owner/lifetime/release semantics differ. Preserve Native bit protocol or design a separate compatible one. Cached file-fault work can be a future translation candidate, but is not part of untouched anonymous mmap1 or the ordinary fresh-anonymous page_fault1 path. |

PTE mapping itself precedes acquisition: `pte_offset_map_lock`,
`mm/pgtable-generic.c:391–409`, maps under RCU, acquires the selected lock and
revalidates the PMD. Unlock/unmap releases both lock and mapping lifetime.
On the captured PREEMPT_RCU configuration, a spin preemption count of one alone
does not prove that this pre-existing reader lifetime is safe to proxy.

The same mm is also used by brk, fork/dup_mmap, exit, advice, proc/GUP and BPF.
Fork nests old/new-mm writers; BPF can release a read share through IRQ work on
another context. The enabled local adapter has a reserved single-use read token
and mm reference for its declared BPF path; live BPF/IRQ/NMI coverage remains
unvalidated. No generic delegated MM ownership follows from that wrapper.

Additional reachable locks are separate objects; none is an observed hotspot in
the exact reference workloads here:

| Lock / native critical section | Type and current delegation assessment |
| --- | --- |
| `anon_vma->root->rwsem`: `__anon_vma_prepare`, `mm/rmap.c:208–220`; `unlink_anon_vmas:493–523` | Rwsem ordinary writers. Link/unlink and interval/count updates are **candidate prefixes**, with nested `mm->page_table_lock` during first binding. Need whole-root lifetime, nested spin and exact graph support. Unfaulted VMA unlink is an explicit no-op; first anonymous write faults can establish the association. |
| Same root: `folio_lock_anon_vma_read`, `mm/rmap.c:633–701`; `rmap_walk_anon:2976–3002` | Rwsem read/tryread, **local**. RCU/reference validation, optional blocking and caller-supplied ownership must survive conversion. Reverse mapping/reclaim is not mandatory on every new anonymous fault. |
| `address_space.i_mmap_rwsem`: `vma_prepare`/`vma_complete`, `mm/vma.c:297–368`; batch unlink `1774–1785` | Rwsem writers. Simple batch removal is a candidate; split prepare/complete may also nest an anon-vma writer and needs cross-function ownership plus currently unsupported translated rwsem nesting. File-mapping tree, absent for the declared anonymous ranges. Mapping-tree reads in `unmap_mapping_pages`, `mm/memory.c:4359–4363`, and `__rmap_walk_file`, `mm/rmap.c:3037–3065`, stay local even when callbacks change PTEs. |
| `address_space.invalidate_lock`: `filemap_fault`, `mm/filemap.c:3543–3667`; `filemap_invalidate_inode:4535–4550` | Rwsem shared fault paths stay **local**, and uptodate cache hits may skip acquisition. Ordinary writer's empty/no-pages path is a candidate; populated invalidation nests mapping/PTL/folio/I/O work requiring exact native boundaries. Two-mapping users also nest writers. Not part of anonymous-private mmap1/page_fault1 ranges. |

Allocator spin/raw-spin/bit/local locks are reachable through VMA/chain/page
allocation. This audit does not claim a complete allocator lock census or
measured contention. Their actual CPU-local/IRQ contract must be established
before delegating a reached allocator path; do not infer eligibility from the
outer lock's type.

Two catalog names also need a source-version distinction. `taskname` is a
synthetic locked snapshot extracted from Linux 6.1; Linux 7's `get_task_comm`
explicitly reads without task_lock (`include/linux/sched.h:2008–2026`). There is
no corresponding current reader lock to replace. `argbounds` has a current
analogue: `mm->arg_lock`, a spinlock around four boundary loads in
`fs/proc/base.c:293–298`; remote-memory reads and user copying follow unlock.
That small exclusive snapshot is a candidate, but all prctl/update participants
and mm lifetime must match. Neither synthetic result is a current procfs syscall
hotspot profile.

## Mandatory instructions and operations

“Mandatory” is relative to a specified path. An instruction inside a conditional
retry loop is required on each taken iteration, not on every syscall. Do not
infer instruction frequency from its presence in an object.

| Site or operation | Verified native/emitter fact | Consequence |
| --- | --- | --- |
| Selected setfd, FIONREAD and GETPIPE_SZ protected branches | Inspected native slices have no PAUSE or mandatory hardware fence; FIONREAD and setfd have no protected-body CALL. | No per-iteration runtime escape is inherent in these bodies. External lock helpers and sibling branches are separate. |
| UTS successful setter | `uts_proc_notify()` is before up_write and is mandatory with CONFIG_PROC_SYSCTL. Actual wake work can be conditional. | If notification stays native, every successful writer transfers its suffix. This is a cost to measure, not grounds to reject the copy prefix or move notification after unlock. |
| PAUSE / `cpu_relax()` | Captured Miasm `arch/x86/arch.py:3911` comments out PAUSE registration; F3 is a prefix and opcode90 is the NOP alias (`4085`); `core/cpu.py:1279–1294` prefers that alias. KD `disassem/special_inst.py:105–108` emits bare NOP for `line.name == "NOP"`, discarding that prefix. | **New source-level fidelity gap:** F3 90's spin hint is lost through this alias path. Preserve it as an instruction; runtime exit per spin iteration would defeat delegated waiting. No new decoder/JIT execution test was run. |
| MM/native waiting and retry paths | Existing objects contain PAUSE in `do_wp_page`, rmap helpers and `flush_tlb_mm_range`; qspinlock source has cpu_relax in taken wait loops. | These are conditional paths, not mandatory instructions in every mmap1 iteration. A learned inner wait loop must retain each PAUSE and correct context; otherwise exit before entering that path. |
| LFENCE/MFENCE/SFENCE and LOCK atomics | Decoder registers fences; normal assembly emission retains their mnemonic and LOCK prefix (`disassem/normal.py:119–159`, `assist.py:97–108`). This pipeline emits assembly, not optimized semantic IR. | They should execute directly and in order, with no runtime call per occurrence. This is source-path evidence, not new generated-image validation for every encoding/address. |
| Page-table publication `smp_wmb()` | On this x86-64 configuration it is a compiler barrier; some full barriers use LOCK arithmetic. | Do not invent a mandatory SFENCE/MFENCE from the C name. Preserve emitted instructions and publication order. |
| TLB invalidate / CR3 / IPI and CPU-local operations | Native MM objects contain conditional INVLPG/INVPCID/CR3 paths; their effects belong to hardware CPU/mm state. | Matching IF alone cannot make them origin-equivalent. Keep the reached operation on its required CPU/task or provide a separately proved service; generic instruction fallback is absent. |

The [instruction/context audit](../../bench/results/10.176.26.71/tests/kernel-cs-semantics-20261030/jit-context.md)
contains opcode offsets and dependency hashes. The PAUSE observation concerns
translated native bodies; it does not establish that the compiled mutex
provider's own polling loop loses PAUSE, nor explain any prior benchmark loss.

## IRQ, preemption and execution-context compatibility

The user's saved-waiter-state comparison is a reasonable **proposed gate** for
eligible shared-memory spin sections. Capture state before the API changes it,
derive the state required while held, and compare it with the actual executor.
At least task/softirq/hardirq/NMI class, IF, preemption/BH/migration nesting,
prior locks and CPU-local dependencies matter. Restore each participant's own
state exactly; do not copy a preempt count or saved flags into another CPU and
call that equivalent. A failed comparison must use local ownership for that
request within the same lock protocol.

**Current code does not implement that complete gate.** Plain spin root admission
checks task/softirq/migration state and `preempt_count()==1`, but lacks a saved
waiter/executor IF comparison (`kernel_module/spin/entry.inc:145–180`). Explicit
IRQ/BH pairs execute locally (`include/kd_spin_direct.h:117–174`). Frames carry
logical task/GS information, not a complete saved IRQ/preempt/active-mm context.
GS-relative address substitution is not a scheduler or hardware-mm switch.
Arithmetic-flag restoration at an escape does not install IF/DF/AC from the
executor on the waiter.

For a section protecting only shared object memory, compatible task context can
make delegation feasible. For a section whose exclusion protects a particular
CPU's allocator/runqueue/IRQ data or whose body performs local TLB operations,
equal numerical flags are insufficient. Refuse delegation of that specific
incompatible interval and retain a supported original-task continuation. Do not
reject an earlier independent prefix solely because that interval is reachable.

The TCLock paper's kernel discussion motivates treating task/per-CPU context
as part of transparent delegation; it uses conservative context restrictions.
It does not establish this proposed saved-state comparison or KD's support for
it. Only the paper's ideas were consulted, not TCLock source.
([TCLocks, §4.2](https://www.usenix.org/system/files/osdi23-gupta.pdf))

## Where CALL-level continuation is a cost or a blocker

Conditional branches remain conditional. A reached missing ordinary CALL can
transfer its callee and **the entire remaining suffix** to the original waiter,
preserving prior effects. It does not return from that arbitrary native callee
to this invocation's JIT. Learning may extend a future image. For pipe GET or a
UTS copy prefix this can be a useful partial episode; if the mandatory first
helper escapes, it may leave almost no delegated work. That is a performance
cost if the exact continuation is supported.

Several present limits are semantic blockers, not just overhead:

- A generic unsupported instruction, unknown RET/indirect target or progressed
  execution error is not a safe automatic bailout. The exact instruction-marker
  allowlist is limited. Seek's split native root return and MM's release inside
  callees need explicit graph/ownership evidence.
- A reached supported instruction marker disables that entry for its registry
  lifetime (`kernel_module/execution/wrapper_entry.inc:237–248`). Current code
  does not retain a permanently hot JIT path after a rare marker branch.
- Native inner `_raw_spin_lock`, `mutex_lock`, `down_read` and `down_write` are
  not KD controls. Their first missing CALL may run locally, but trusted learning
  can later import their bodies. There is no permanent Native-lock/context
  boundary. The implemented one-CAS **KD mutex→KD spin** path is a different,
  narrower contract; it does not certify arbitrary untouched Native inner locks.
- Full source decoding/lowering and root marker graph restrictions can prevent
  publication even where a difficult branch is cold. Source trust skips semantic
  admission, not these backend requirements.

An exact terminal instruction/basic-block exit is a plausible next capability:
retain source RIP, virtual stack, live operands/flags, physical owners and phase,
then execute the native suffix without replay. Returning to JIT after arbitrary
native code needs a stronger, separate merge/continuation contract. Neither
requires moving normal PAUSE, fences or atomics into runtime handlers.

## Additional support exposed by this map

These are specific integration requirements beyond declaring a lock API name
available. They are not completed work or new permissions to rewrite native MM.

1. **Faithful hot instruction paths:** preserve prefixed PAUSE; validate fences,
   atomics and relevant CPU/context instructions in actual generated images.
   Add precise reached exits where required, preserving hot-path eligibility
   after a rare exit rather than permanently disabling the entry.
2. **Stable Native-inner boundaries and context gating:** identify intentionally
   local Native lock/scheduler/IRQ operations across learned generations;
   implement saved context comparison for eligible spin sections. Origin CPU
   dependencies still require local execution, not only matching IF.
3. **Cross-function acquisition/release:** support or prove fd_pos root returns,
   indirect llseek and cleanup, and MM's release/retry/completed paths without
   losing an acquisition or replaying effects.
4. **Delegated mmap writers:** killable cancellation before execution, exact
   commit/ownership transfer, writer-sequence/per-VMA ordering and atomic
   write-to-local-read downgrade. Current local KD support for these APIs does
   not make their writers delegatable. Fairness redesign remains out of scope.
5. **PTL/nested MM lifetime and physical context:** preserve PTE-map/RCU lifetime,
   nested locks, allocator/CPU-local behavior and TLB shootdown obligations.
   User-access exception handling, active mm and asynchronous read release need
   explicit contracts where reached; a generic GS/current substitution is
   insufficient. The existing MM read-token wrapper covers only its stated scope.
6. **Whole-object integration:** initialization, layout/binding, all local and
   delegated users, callable/try/signal variants and destruction. UTS requires
   restoring native rwsem scope and notification order; per-VMA and folio locks
   require their own protocols, not an ordinary lock macro substitution.

The most bounded first candidates are setfd and pipe query sections, followed by
callback-free OFD and a proved seek continuation. MM writer delegation requires
the additional phase/cancellation/context work above. First obtain exact
unchanged-application lock-address/wait-site profiles before prioritizing PTLs
or folio-related work. Any later implementation still needs basic and affected
correctness checks and a separately matched nano comparison; this static audit
establishes neither a speedup nor a no-regression result. PREEMPT_RT,
DEBUG_MUTEXES and DEBUG_LOCK_ALLOC/lockdep remain explicitly unsupported.

## October 30 implementation plan and acceptance gates

The user authorized implementation after this audit, in the order below.
This section is a plan, not a claim that any gap is already repaired. Start
from `acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f`; preserve the unpromoted
`2dbcd7afbf141dd63dcf0086b65fd0da4b32d6f7` optimization and its failed nano gate
as separate evidence. Do not promote that regression as an implementation base.
Keep independent candidate commits until their required checks pass. The
maintained source-trust policy, two-word wrapper ABI, 1024/1024 limits and exact
physical owner/source/frame/unlock-ACK records remain requirements.

| Order | Concrete work | Gate before advancing |
| --- | --- | --- |
| 1a | Preserve exact F3 90 PAUSE while retaining ordinary fences/atomics. Change supported reached instruction exits from registry-wide disable to per-invocation native continuation, with immutable image/source lifetime and repeated-exit behavior intact. | Generated-byte/behavior checks; cold → taken → cold → taken live phases, exact prefix/suffix/flags/owner results and normal retirement. No permanent loss of cold-path JIT eligibility. |
| 1b | Add saved origin/executor context admission for supported task-context spin intervals. Keep incompatible IRQ/BH/preempt/CPU-local paths on the origin with the same KD physical protocol. Establish explicit Native-inner/context CALL boundaries that learning cannot silently cross. Extend exact instruction boundaries only with corresponding state/ownership proofs. | Context-matched delegation and mismatched local completion; no replay, lost pin, changed IF, double release or invalid native stack. A terminal native suffix is distinguished from a resumable typed runtime operation. |
| 1c | Prepare minimal lock-call/binding integration for `files_struct.file_lock` and `pipe_inode_info.mutex`, first for setfd and FIONREAD/F_GETPIPE_SZ. Preserve original function bodies, command branches and user-copy position. Every other participant on a bound object uses the same KD object with local semantics where delegation is unsupported. | Initialization/quiescent binding, callable/try/local routing and teardown checks; actual syscall result/concurrency checks, including operations outside the proxied subset. A copied/specialized adapter is not acceptance evidence for unchanged bodies. |
| 2 | Freeze baseline/candidate inputs. Run the ten maintained nano profiles, then the bounded real syscall cases. Use Native/KD and a supported TCLock arm only where its scope is equivalent. | One measurement round per point. Publish correctness, returned-JIT/local counts, drain and throughput separately. Any measured nano regression fails promotion and requires diagnosis plus optimization or path-specific rollback; no averaging across versions or topologies. |
| 3 | Validate the localized mmap backend and run the existing shared-mm mapping workload with exact original-task reader/phase/lifetime behavior. Prepare unchanged pinned will-it-scale mmap1 as a distinct driver. | Basic plus affected API, mapping, fault and completed-fault checks; explicit kernel/backend/boot identity; one-round localized Native/KD comparison. Device mapping is not relabelled mmap1. |
| 4 | Integrate the corresponding kernel object groups and all required local/delegated API participants. For mmap writers preserve killable cancellation, writer/per-VMA sequence ordering, downgrade and asynchronous read-token lifetime. Keep unsupported bit/per-VMA protocols Native. | Exact source diff restricted to lock API and necessary binding/lifetime glue; unchanged native bodies; fresh recovery/boot identity and directly affected execution checks. Native suffixes retain every acquired lock and committed effect. |
| 5 | Run unchanged will-it-scale mmap1 against matched Native/KD kernels, shared-mm thread mode first and independent processes as a separate control. Recheck affected nano/syscall cases for the final source/kernel generation. | Correct data/progress/drain and measured mmap1 performance. Publish every one-round point; require measured parity or improvement against Native at the declared shared-mm points and no nano regression. One round supplies no variance estimate or statistical guarantee. |

Source edits, Git and static/archive inspection run on 380G10. All compilation,
unit/live checks and timing run in the designated VM. Synchronize only while
idle; freeze the running generation. Before module/JIT or kernel work verify a
real recovery snapshot and bound every remote command. The user authorized
kernel build/install/reboot for this task; no unreviewed native-body rewrite is
authorized by that permission. Preserve unrelated work and every failed attempt.

The initial comparison grid uses the maintained `1..8,12..60` worker counts,
CPUs `0..N-1`, collector63, fixed host policy and one two-second measurement
round per coordinate. Freeze the exact workload parameters and source/kernel
identities in each campaign before execution. Diagnostic runs are separate from
timing and cannot replace a failed coordinate. Oversubscription and rwsem
fairness redesign remain deferred. Full suites require a separate explicit
request; use basic plus directly affected checks.

The first functional milestones deliberately distinguish persistent eligibility
from arbitrary re-entry: after a reached exact native exit, that invocation can
finish its native suffix without disabling later requests. Resuming the same
JIT after a native interval additionally requires a validated return/state merge
and acquisition contract. Preserve actual CALL/RET words; do not create a fake
general native return bridge to satisfy a coverage count. Any remaining coarse
fallback or unsupported context must stay explicit in the completion report.
