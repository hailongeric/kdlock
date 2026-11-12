# Source review of the next bounded MM prefix

This is a source-only review in `/home/eric/vm/vm-shared/kdlock-main`, observed
at HEAD `08454c4e2412a8821461ea596c04d5cbc1add45d`, with clean source status at
the initial inspection. No repository edit, project import, test, build, VM
operation or Git mutation was performed. The review reads existing source and
saved compiled-object metadata with the Python standard library. It proposes
no new execution engine, native execution on a combiner, CPU reservation or MM
body change.

The smallest supported next step is a **new cold source-region configuration**
that adds `do_mmap`, while keeping the existing original JIT, GS lowering,
canonical S_W, generic rwsem query handling and immediate exact native handback.
No missing generic implementation was found before this additional prefix's
first native-context frontier. This is not an execution or completion result.

## Source extent and conditional first cuts

The linked kernel8 inputs describe this five-region candidate:

| Region | Start | Bytes |
| --- | --- | ---: |
| `vm_mmap_pgoff` | `0xffffffff817ef350` | 804 |
| `__vm_munmap` | `0xffffffff8185ae30` | 746 |
| `do_mmap` | `0xffffffff818321c0` | 1,656 |
| `its_return_thunk` | `0xffffffff8276eee0` | 2 |
| `__x86_return_thunk` | `0xffffffff8276eef0` | 6 |

Total source is 3,214 bytes, leaving 882 bytes within the existing 4,096-byte
source-byte capacity. The 1,656-byte `do_mmap` region ends at
`0xffffffff81832838` (exclusive). These are linked extent/planning inputs, not a
new live-text export or activated configuration. The earlier five-region
proposal remains `SOURCE_ONLY_NONDISPATCHABLE_PROPOSAL`; its old null
identities/contracts, proxy limit and declared-control values are not current
run inputs and should not be reused as such.

The saved linked `do_mmap` disassembly starts with a CALL to `__fentry__` at
`0xffffffff818321c0`, targeting `0xffffffff81405880`. The actual earlier live
wrapper exports demonstrate that linked fentry CALL bytes can instead be
patched NOPs. A new candidate must use its own actual provider-copied live
bytes and exact source version. This review does not turn the linked CALL into
a NOP or admit `__fentry__` by assumption. If the live CALL remains and its
callee is omitted, the ordinary exact CALL_STAGED handback remains available.

Conditional on the actual `do_mmap` entry being a NOP, the admitted successful
anonymous mapping prefix reaches the existing typed writer-held query:

- source query CALL `0xffffffff81832246` targets
  `kd_linux_rwsem_is_write_locked_entry_asm`, `0xffffffff8152f810`;
- the exact post-query continuation is `0xffffffff8183224b`;
- after that continuation has been admitted through the existing observed
  reentry workflow, the next ordinary omitted helper on this path is CALL
  `0xffffffff81832349` to `__get_unmapped_area`, `0xffffffff818313c0`.

Keep that helper omitted for this step. Its source CALL would stage its real
return word and native handback would begin at the unexecuted callee entry;
the CALL must not be replayed. Other actual source branches can stop earlier.
Fresh bytes, decoding, lowering, admission and actual observations decide the
reached first cut; the linked path is not a guarantee of reach.

For munmap, the closed actual source CALL identifies the target
`do_vmi_munmap` at `0xffffffff81858430`. No standalone linked extent or live
entry bytes for that function were found in the retained context export.
Do not guess its length, entry patching or next compiled helper target. Exact
preserved source `mm/vma.c:1611-1633` describes validation, then `vma_find`, then
`do_vmi_align_munmap`. It does not establish where those operations are inlined
or which instruction first needs native context. Adding only `do_mmap` leaves
the munmap omission unchanged. A later two-callee configuration needs the
corresponding bounded byte/source review first.

Saved references:

- `tests/evidence/kernel8-mm-context-review-20261111/export/disassembly/do_mmap.txt:7-43`
  contains entry/fentry, GS-current and the typed query; line 100 contains
  `__get_unmapped_area` and line 310 the later `mmap_region` CALL.
- `tests/evidence/kernel8-mm-context-review-20261111/supporting-mm/source/mm/vma.c:1611-1633`
  is the preserved native `do_vmi_munmap` source, not an extracted-body test.
- `/tmp/kdlock-kernel8-mm-prefix-five-region-proposal-20261111.json` supplies the
  linked 1,656-byte extent and the historical non-dispatchable plan status.

## Existing provider and compiler already support the step

`tests/kernel/mmap_api/payload/mmap_jit_profile.inc:244-257` accepts explicit
exact region starts and lengths and enforces the caller's total source-byte
capacity. Lines 365-374 construct the existing immutable source provider.
Its dependency list retains this module and identifies other declared text as
built in (lines 363-364). `kernel/source_provider.c:76-105` copies the actual
source bytes and binds them to the source epoch. No helper-specific provider
or change to the public syscall path is required.

This remains the explicit immutable-text provider contract in
`kernel/source_provider.h:8-14`, including exclusion of tracing, static-call,
alternative and probe changes through the final source/native/feedback user.
Neither a module reference nor a copied hash alone establishes that contract.
The new source extent needs fresh version/configuration/load bindings. The
existing source snapshot cannot be expanded silently during an active epoch.

`disassem/compiler.py:471-474` distinguishes an omitted source address from
supplied bytes. Lines 532-545 already discover supplied direct callees under
the explicit discovery limit. `disassem/lowering.py:188-224` preserves an
ordinary unavailable-target frontier and exact phase; lines 238-288 retain
ordinary backend lowering and a pre-instruction refusal for unsupported
representations. The direct CALL path uses the original source return address
(lines 243-262 and 418-420). Existing GS-current matching is exact and uses the
original instruction EA in `disassem/backend/normal.py:39-58`; GS translation
does not establish physical RCU, preemption or PTL context.

Keep the permanent generic context frontiers in
`tests/kernel/payload/native_context_boundaries.inc:10-25`: preemptible RCU and
plain spin entries are SPECIAL before their effects. Its comment explicitly
requires separate exact metadata for inline effects and other context
variants. The RCU CALL shown in one later normal-PTE interval is not proof of
the first context effect in the complete preceding MM path. This step does
not admit that preceding helper chain or translate through its context scope.

## Query return and facts need no new learner mechanism

The existing branch `kernel/episode.c:842-866` prepares the query, emits its
observation, executes `kd_jit_query`, reports the exact predicate and loops.
`kernel/jit.c:978-1013` performs the physical-gate predicate and the existing
canonical operation completion/return. `kernel/state.c:176-196,230-277`
stages and consumes the real source CALL word and commits the integer result
once. The query does not create a child acquisition or recursively execute
another source episode.

The first expanded image normally declares only the two actual acquisition
roots. `kernel/jit.c:122-127` therefore refuses a later entry at the initially
undeclared `0xffffffff8183224b`, preserving the exact native continuation.
The unchanged runner already accepts an exact observed query return as a new
entry (`tests/kernel/mmap_api/runner.py:658-707`) and forces a later candidate
when a new reentry is found (lines 834-843). Three existing rounds can provide
the cold-root round, a query/observed-reentry round and a later prefix round.
That is source-supported sequencing, not a guarantee of delegation or reach.
There is no reason to add an unobserved initial query-return root or modify
the ordinary direct-CALL learner for this step.

Current direct-CALL misses are intentionally non-observations:
`disassem/feedback.py:240-242` returns `DIRECT_CALL` without an indirect-target
observation. SPECIAL frontiers are likewise non-observations (lines 207-217).
`disassem/compiler.py:135-144` fixes source bytes and source classification for
the snapshot version; `disassem/learning.py:581-584` compiles that snapshot.
Repeated feedback cannot supply missing callee text or remove a permanent
context cut. Advancing beyond the first ordinary omission therefore requires
the caller's next explicit source admission, not synthetic coverage ACKs or
replaying a previous invocation. Existing exact facts/archive/settlement
semantics remain unchanged.

## Fresh AUX query-branch scope review

The original four-region source review explicitly excluded typed queries.
This section is a new source-shape review of the additional query branch. It
does not rewrite that historical scope or claim its conditional artifact
already covered this input.

The simultaneous combiner prefix has these ten named KD source functions:

1. `mutex_api.c::run_native`
2. `episode.c::kd_episode_acquire_root`
3. `jit.c::kd_jit_acquire`
4. `rw.c::kd_rw_write_acquire`
5. `mutex.c::kd_mutex_acquire`
6. `mutex.c::kd_mutex_await`
7. `mutex.c::serve_writer_cohort`
8. `jit.c::execute_selected`
9. `jit.c::kd_jit_mutex_drive`
10. `episode.c::run`

The deepest added paths have at most 16 named KD source functions. One witness
adds `kd_jit_prepare_operation -> drop_pending_exit -> pending_image ->
kd_state_is_jit_current -> kd_state_is_current -> kd_state_current_binding`.
The image-check alternative adds `kd_jit_prepare_operation ->
drop_pending_exit -> pending_image -> kd_jit_image_use_check_exit ->
exit_matches_locked -> current_locked`, also reaching 16. The query-return
alternative adds `kd_jit_query -> kd_operation_return -> operation_matches ->
kd_state_is_jit_current -> kd_state_is_current -> kd_state_current_binding`,
again reaching 16. These are conservative source-function counts, including
functions the compiler inlines; they are not measurements of 16 hardware
frames. The source stack `read_word`/`write_word -> stack_word` alternatives
are shorter and have fixed callbacks, not arbitrary source callbacks.

`kernel/linux_rwsem.c:86-97` returns immediately for the typed query in its
pre-operation readiness check. The physical predicate
`kernel/rw_native.c:554-563,578-589` reads under the existing paired raw guard.
`kernel/image.c:178-220` and `121-130` check/unlink the exact pending exit use;
this path does not synchronously free an image, compile code or call a cold
source finalizer. The new observation rows use the same admitted trace
listener, not an additional observer. Each query helper returns before the
next generated entry. Loop iterations and proxy_limit two add no recursive
query frames.

Existing saved weights contain the new control functions:

| Compiled function | Fixed reservation including entry word | Local check |
| --- | ---: | --- |
| `kd_jit_prepare_operation` | 120 | closed |
| `kd_jit_query` | 72 | closed |
| `pending_image`, `drop_pending_exit` | 56 each | closed |
| `kd_jit_image_use_check_exit`, `kd_jit_image_use_finish_exit` | 56 / 48 | closed |
| `kd_operation_begin`, `kd_operation_stage_call` | 64 / 48 | closed |
| `kd_operation_enter`, `kd_operation_complete_int_result` | 16 each | closed |
| `kd_operation_return` | 48 | closed |
| `kd_state_is_current`, `kd_state_is_jit_current` | 16 each | closed |
| `kd_rw_native_is_write_locked`, `kd_rw_native_is_locked` | 32 / 40 | closed |
| source `read_word`, `write_word` | 40 / 48 | closed |

All listed functions have empty unknown-RSP and local-CFG-error lists. The
underlying metadata remains the existing fixed-reservation analysis, including
separate source closure of return thunks, inherited-context cold transfers and
excluded contract-failure diagnostics. It is not newly generated disassembly
or an executed query test.

The prior compiled bound includes **all 30 KD C units**, including these
functions, with a maximum of 392 bytes per source-function group after
conservatively adding all clone/cold reservations. It also charges the maximum
whole-unit alternative positive-RSP sum of 16 bytes at every named KD depth.
The newly examined query branches' maximum depth of 16 is below the existing
27-depth allowance. Their additional provider/trace callbacks and generated
physical temporary fit the already separate fixed charges. The translated
`do_mmap` prologue, source CALL and source frame changes occur on W's canonical
source stack, not as native C calls on AUX.

Consequently a **fresh five-region conditional scope receipt** can retain the
same conservative formula without increasing its numerical requirement:

`27 * (392 + 16) + 32 + 48 + 16 + 144 + 2 * 16384 = 44,024 bytes`.

The declared control requirement remains 65,536 bytes, with a 21,512-byte
margin, within 131,072 bytes of auxiliary storage. This arithmetic remains
conditional on the explicit experimental native-helper and interrupt-entry
allowances. Raw-guard unlock/preemption/scheduler and instrumentation callbacks
remain within the same unmeasured inclusive 16 KiB native-helper premise; this
review neither measures those complete trees nor adds a new callback set.
It does not prove the complete AUX requirement or establish a live query
result. Preserve the original conditional artifact's false flags and the
separate user's experimental admission unchanged.

## Pinned saved analysis inputs

| Input | SHA-256 |
| --- | --- |
| `/tmp/kdlock-kernel8-aux-stack-weights-20261111-04.json` | `d1c66e94efed9670ecd2a4a541f8437fa7547064434e703eca7a687bde0a1078` |
| `/tmp/kdlock-kernel8-narrow-aux-stack-budget-20261111-04.json` | `bdcab02965bc43fb2134e5ef13087a0ecec92ee9fbfaef98ae62b657a8bf35b2` |
| `/tmp/kdlock-kernel8-narrow-aux-source-0798c1ab-01.md` | `09b024482b28b30dd6f1b94ac5d64f23e3cae7a06819d4d7b5f06852d4b5fbdc` |
| `/tmp/kdlock-kernel8-mm-prefix-five-region-proposal-20261111.json` | `fad67063934aa81b60da6ff3017d49455621962e71c713d6a26dbf5fd059810c` |

The source-only review found a supported configuration step and no engine fix
to implement before its context frontier. Actual byte capture/admission,
bounded construction and a separately authorized future syscall run remain
distinct work and evidence. No independent query-delta peer result is claimed
in this draft.
