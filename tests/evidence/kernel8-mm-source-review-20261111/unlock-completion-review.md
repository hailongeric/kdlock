# Five-region MM source scope: early return, root unlock and completion

Source-only supplement at `08454c4e2412a8821461ea596c04d5cbc1add45d`.
This review reads current source and saved compiled-object analysis. It runs no
project import, compiler, test, build, VM command, provider or syscall, and changes
no execution code or selected protocol. The earlier query-only note is preserved
unchanged. Its 16-function query maximum does not by itself cover this additional
root-unlock branch.

## Scope and newly reachable alternatives

The proposed source adds only `do_mmap` to the four previously retained regions.
It does not add `__get_unmapped_area`, another native helper body, a nested source
lock operation or `do_vmi_munmap`. The actual capture still decides whether fentry
is a patched NOP or an earlier ordinary callee miss. Every existing context
SPECIAL entry and exact first-unexecuted handback remains in force.

The linked `do_mmap` has early error returns before the omitted
`__get_unmapped_area` CALL at `0xffffffff81832349`. For example, its zero-length
test reaches the common return at `0xffffffff8183254a`; other range/map-count
checks also reach it. See
`tests/evidence/kernel8-mm-context-review-20261111/export/disassembly/do_mmap.txt`
lines 39-100 and 217-237. This review does not assume these branches are
impossible for the workload. The common return resumes the already admitted
outer `vm_mmap_pgoff` after its real CALL word. The outer writer-state query,
mmap sequence update and typed UP_WRITE are in
`export/disassembly/vm_mmap_pgoff.txt:120-145` and the following lines. Therefore
the fresh scope must include typed root unlock and completion, even though its
intended successful prefix stops at the omitted address-selection helper.

Missing source/cold targets or unsupported instructions remain ordinary exact
handback alternatives. No new error return, CALL or completed query is replayed.

## Source chain and release route

The simultaneous combiner prefix is the same ten named KD source functions:

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

`episode.c:939-988` finds the exact typed root grant, prepares the existing
operation, calls `kd_jit_unlock`, marks the target source closed and loops.
`jit.c:918-945` enters that operation, calls `release_grant`, completes the
operation and consumes its exact return word. Preparation uses the same
pending-image/state/stack callbacks reviewed in the 16-function query scope.

In this root-only source scope, `active` is the current call's batch and the
matching target is that same root acquisition. There is no admitted child lock
or downgrade. `mutex.c:1113-1146` therefore selects OWNER routing; the
`synchronous_outer && active_batch != node->batch` alternative is false. The
mutex-only deferred-parent branch at `episode.c:954-959`, native READ release,
retained-read terminal release and atomic-spin source release are not introduced
by these five source regions. This is a structural scope restriction, not an
assumption that early errors never occur.

The direct release path is:

`episode.run -> kd_jit_unlock -> release_grant -> kd_mutex_source_unlock ->
kd_mutex_release_request / kd_mutex_release_owner_handle`.

The request and handle calls are sequential, not nested in each other.
`mutex_release.c:122-162,240-262` changes only exact guarded release state and
emits the existing observation. It does not call physical backend unlock or a
new finalizer. `state.c:462-506` closes the logical grant after OWNER_HANDLED;
the source user remains retained until physical ACK and exact unlink.

The grant-lookup alternative reaches 16 named KD functions including the ten
prefix functions:

`kd_jit_unlock -> release_grant -> kd_state_find_operation_grant ->
kd_state_find_grant_typed -> kd_state_is_current -> kd_state_current_binding`.

The return/state checks and fixed source-word callbacks are no deeper. The
source-grant unlink/observation alternative is at most 17 named functions.

## Collection, physical finish and final control

After typed UP_WRITE, the next `run` iteration calls `kd_episode_collect` and
the owner pump before observing `source_closed` and returning EPISODE_DONE:
`episode.c:718-741`. The conservative additional collection witness has **19
total named KD source functions**, including the ten-function prefix:

11. `episode.c::kd_episode_collect`
12. `episode.c::finish_image_actor`
13. `episode.c::finish_user`
14. `request_pool.c::kd_request_user_finish`
15. `request_pool.c::drop_user`
16. `request_pool.c::reusable_locked`
17. `request_pool.c::controls_idle`
18. `request_pool.c::components_idle`
19. `request_pool.c::image_idle` (or the shorter `user_idle` alternative)

The source references are `episode.c:22-34,249-288` and
`request_pool.c:16-92,441-483`. This is a conservative source-function count,
including wrappers that compile inline and component checks that can return
earlier while another exact user remains. It is not a count of 19 hardware
frames. The `drop_user -> free_locked -> observation` alternative is separate
from its completed `reusable_locked` call; their frames must not be summed as
though the observer ran inside the component-idle checks.

The other collection branch is
`kd_episode_collect -> kd_jit_collect_grants -> kd_state_unlink_grant ->
drop_grant -> kd_mutex_grant_unlinked -> kd_mutex_release_drop_source ->
observe_release`, at most 17 total with the ten-function prefix. Grant unlink
waits for physical ACK (`state.c:509-546`); `drop_grant` is the exact installed
callback (`jit.c:359-377`). The callback does not free the source allocation or
invoke an arbitrary provider. The root has no read-credit branch here.

The owner pump does not execute another proxy. Physical finish and canceled
successor cleanup rejoin the previously reviewed **27-function** tail through
`pump -> kd_owner_progress_run -> kd_mutex_finish_batch ->
kd_mutex_release_finish_physical -> mcs_physical_unlock -> cancel_queue_depart ->
cancel_actor_done -> jit.cancel_departed -> episode.cancel_departed ->
finish_cancel_queue -> kd_task_cancel_actor_finish -> kd_request_user_finish ->
drop_user -> reusable_locked -> controls_idle -> components_idle -> image_idle`.
The count includes the ten-function prefix and `pump` at position 11. It is the
same tail retained in the historical source graph; query/unlock frames have
returned before it runs. Source-only closure of the added branches does not
retroactively enlarge the historical four-region scope.

`owner_progress.c:131-147` prevents physical finish of an active cohort without
its close condition. Its blocked test at 246-255 applies only to a stopped
terminal-foreign owner. It does not force a source-closed active callback to
wait for its own export. After `run` returns, `kd_jit_mutex_drive` transfers the
current source state and invokes `exported` sequentially (`jit.c:525-548`).
`episode.c:1027-1048` calls control-stopped and closes the empty child list;
its deferred list is empty for this root-only RWSEM scope. The existing cohort
then publishes the result and drains/releases using its old progress paths
(`mutex.c:831-859`). A second cohort service is sequential.

Original-task final control runs after the acquisition call has returned:
`run_native -> kd_episode_root_done -> finish_image_actor / finish_user`, then
`kd_mutex_resume_entry -> kd_episode_native_done -> finish_user` and exact
native resume. These are shorter than the conservative collection witness.
See `mutex_api.c:112-139`, `episode.c:1115-1145` and `native_entry.c:165-203`.
They do not retain the earlier combiner/query/unlock call frames.

## Compiled units and fixed callbacks

No new C object is required. The additional reachable functions are in the
already captured `jit.o`, `state.o`, `mutex.o`, `mutex_release.o`, `episode.o`,
`request_pool.o`, `owner_progress.o` and `native_entry.o`; source-word callbacks
remain in `source_stack.o`. These units were part of all 30 KD C units used for
the grouped maximum. Their source code has not changed since the compiled
kernel8 capture. Their reach is newly included in this source scope.

Saved `analysis/weights-04.json.gz` records these fixed reservations, including
the entry return word:

| Function or fixed alternative | Saved bytes |
| --- | ---: |
| `kd_jit_unlock`, `release_grant`, `kd_jit_collect_grants`, `drop_grant` | 72 / 80 / 64 / 32 |
| `kd_state_find_operation_grant`, `kd_state_find_grant_typed` | 32 / 72 |
| `kd_state_close_grant`, `kd_state_unlink_grant` | 48 / 48 |
| `kd_mutex_source_unlock`, `kd_mutex_grant_unlinked` | 72 / 48 |
| `kd_mutex_release_request`, `kd_mutex_release_owner_handle`, `kd_mutex_release_drop_source` | 72 / 40 / 48 |
| `observe_release.part.0` | 192 |
| `kd_episode_collect`, `finish_image_actor`, `finish_user` | 56 / 32 / 40 |
| `kd_request_user_finish`, `drop_user`, `reusable_locked`, `components_idle`, `image_idle` | 16 / 72 / 48 / 24 / 8 |
| `free_locked` | 216 |
| `exported`, `kd_owner_progress_control_stopped` | 32 / 208 |
| `kd_episode_root_done`, `kd_episode_native_done`, `kd_mutex_resume_entry` | 32 / 32 / 64 |

These real hot functions have closed local stack checks and no unknown RSP or
local CFG error. Their retained clone/cold groups remain below the global
392-byte grouped charge. The existing whole-unit alternative charge remains
16 bytes per named depth. The synthetic pre-symbol
`observe_release.part.0-0x10` range is not a new callable body; its historical
prefix/alternative treatment remains the one explicitly preserved in conditional
analysis 04. This review does not silently count that synthetic fallthrough as
a successfully analyzed function.

The preserved grouped unit maxima are `state.o` 80, `mutex_release.o` 216,
`request_pool.o` 240, `jit.o` 144, `mutex.o` 272 and `episode.o` 392 bytes.
For example, clone/cold addition makes `kd_state_find_grant_typed` 80,
`kd_episode_collect` 64, `finish_image_actor` 40, `finish_user` 48, `drop_user` 80,
`reusable_locked` 56, `image_idle` 40 and `free_locked` 224 bytes. The table above
reports the hot entries separately. Independent source-only saved-weight peer
inspection agrees that these real hot/cold entries are locally closed and that
the inlined-parent and grouped-unit charges cover the added source paths.

`release_lock` is inlined into its closed release callers; `controls_idle` is
inlined into closed `reusable_locked`; `unlink_user_locked` is inlined into
closed `drop_user`. The source-depth calculation nevertheless charges a full
grouped maximum for the counted wrappers. It does not assign missing symbols
zero cost. The existing parser and manual cold/return-transfer closures are
unchanged.

The relevant indirect callbacks are fixed:

| Callback | Bound target / timing |
| --- | --- |
| operation resolver | `episode.c::cached_resolve`; read-only cached exact target |
| source read/write | `source_stack.c::read_word/write_word -> stack_word` |
| source grant drop | `jit.c::drop_grant -> kd_mutex_grant_unlinked` |
| image exit finish / image use put | Check/unlink exact users; no synchronous image destruction or compilation |
| physical backend unlock | Existing `mutex.c::mcs_physical_unlock`; old 27-function finish tail |
| canceled queue callback | Existing `jit.cancel_departed -> episode.cancel_departed` tail |
| driver export | `episode.c::exported`; no child/deferred recursion in this scope |
| native entry done | `episode.c::kd_episode_native_done` |
| observation listener | Same admitted provider observer and trace bridge; no additional listener |

`request_pool.c::drop_user` unlinks users and may mark a fixed slot reusable;
it has no synchronous cold native-storage finalizer. The separate canceled-task
storage finalization route remains the historical one, including its external
queue-work leaf; no new finalizer is introduced by typed root UP_WRITE.

## Fresh conditional conclusion and limits

The fresh five-region source scope includes query paths of at most 16 named
functions, the newly reviewed collection/finish path of at most 19, and the old
physical/canceled-successor maximum of 27. The old numeric depth charge of 27
therefore remains conservative for this enlarged finite scope. The same source
and compiled-unit alternative maxima permit the unchanged formula:

`27 * (392 + 16) + 32 + 48 + 16 + 144 + 2 * 16384 = 44,024 bytes`.

The 65,536-byte declared control requirement leaves 21,512 bytes, within the
131,072-byte allocation. The translated helper prologue/CALL/RET uses W's
canonical source stack rather than adding native `do_mmap` frames to C's AUX.
The existing exact source-stack, source/code lifetime and construction/resource
contracts still apply; this is not proof of every native source-stack path.

Native raw-guard lock/unlock, irqsave/restore, wakeup, preemption/scheduler,
instrumentation and their inclusive callbacks remain within the same explicitly
unmeasured experimental native-helper allowance. Interrupt entry retains its
separate 16 KiB experimental allowance. The same 96-byte observation/readiness
charge and 144-byte generated-wrapper/temporary charge apply. This review
neither measures those native trees nor establishes a complete AUX requirement,
an activated five-region image, a new behavioral pass or full protected-MM JIT
completion. It changes no handback, native-context, cancellation or replay rule.

Pinned saved analysis inputs remain weights 04
`d1c66e94efed9670ecd2a4a541f8437fa7547064434e703eca7a687bde0a1078`, conditional 04
`bdcab02965bc43fb2134e5ef13087a0ecec92ee9fbfaef98ae62b657a8bf35b2`, parser
`0e5f7f7fc0d0c6debbd19885b0cc9bbffaedaf0a91cd4e1c5136da00d969fba9` and original
source graph `09b024482b28b30dd6f1b94ac5d64f23e3cae7a06819d4d7b5f06852d4b5fbdc`.
The historical artifacts and their false full-proof flags remain unchanged.
