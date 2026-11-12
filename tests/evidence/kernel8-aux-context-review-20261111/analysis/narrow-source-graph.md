# Narrow four-region AUX control callgraph review

Source-only review at `0798c1abf422017cfc93647a2649be0e5a73c75a`.
No build, project import, test, object execution, VM operation or source edit was
performed for this review. This closes the admitted KD control shape; it does
not supply an AUX byte bound without compiled frames and the external leaves.

## Admitted source shape

The proposed image contains only:

| Region | Start | Bytes |
| --- | --- | --- |
| vm_mmap_pgoff | 0xffffffff817ef350 | 804 |
| __vm_munmap | 0xffffffff8185ae30 | 746 |
| its_return_thunk | 0xffffffff8276eee0 | 2 |
| __x86_return_thunk | 0xffffffff8276eef0 | 6 |

Total 1,558 source bytes. Root acquisition continuations are 0xffffffff817ef5ea
and 0xffffffff8185b00e. do_mmap and do_vmi_munmap are omitted. The first missing
body CALLs are 0xffffffff817ef4d3 and 0xffffffff8185af54; the optional acquired
trace CALL sites can hand back earlier. These are explicit input assumptions
for this review, not new runtime observations.

With this source frontier there is no admitted callee or nested typed source
operation. episode.c `run()`'s child preparation/acquire/drive branch (lines
865-940), typed query/unlock/downgrade branches and deferred-child recursion do
not execute. Native MM suffixes run on their original task's source stack.
They are not callees nested under the combiner's AUX frames.

proxy_limit=2 limits sequential cohort service. In mutex.c
`serve_writer_cohort()` (785-886), execute_proxy returns, the result is published,
wait_cohort_release returns, and only then can another successor be selected.
The second borrower repeats the same stack shape; it does not retain the first
borrower's driver frames. Owner list walks, request/frame scans, MCS link polls,
wait loops, callback-list iteration and feedback scans also add iterations,
not recursive frames. This observation is not a progress/time bound.

## Original stack and AUX boundary

Before switching: linux_rwsem.c prepare_down_write[_killable]_current ->
source_root_ready -> mutex_api.c kd_rwsem_prepare_source_current ->
prepare_current -> task_progress_native / episode_prepare_root ->
native_entry.c kd_mutex_prepare_entry. These admission C frames are on the
original source stack and unwind before the clobber entry. The live aux_entry
rejects a second original-root bootstrap before touching borrowed core state.

include/mutex_entry.S `kd_mutex_entry_asm` changes RSP to the admitted control_top
before its sole indirect CALL to run_native. The source CALL continuation and
source BP are passed explicitly. No original wrapper C frames remain beneath
that AUX CALL. The terminal original-task route is run_native ->
kd_episode_native_binding -> kd_episode_root_done -> kd_mutex_resume_entry ->
kd_episode_native_done -> kd_native_resume. The final C frames are abandoned;
include/native_resume.S restores original RSP, temporarily pushes exact IP,
restores registers and RETs at unchanged canonical source SP. Ordinary rwsem
uses no spin-native-resume/unpin branch.

## Main source-level paths

Acquisition prefix on AUX:

`run_native -> kd_episode_acquire_root -> kd_jit_acquire ->
kd_rw_write_acquire -> kd_mutex_acquire -> kd_mutex_await`.

The local-head branch uses start_batch -> kd_rw_writer_enter -> source wait
callbacks; after local grant, episode_acquire_root calls kd_jit_mutex_drive.
The root's current==origin path in episode.run forwards to native without
executing the generated image. It is separate from actual borrowed JIT.

The writer-cohort branch is:

`kd_mutex_await -> serve_writer_cohort -> execute_selected ->
finish_acquisition` followed by `kd_jit_mutex_drive -> episode.run`.

`episode.run` calls collect and pump sequentially, then readiness, image-use
extension, kd_jit_enter and image.entry. A generated return is processed before
a new entry. Coverage/target classification, feedback copy and forward/native
transfer happen after image.entry has returned. The pure generated prefix has
its own compiled prologue reservation; count that at image.entry, not as an
additional source C callee chain.

The largest reviewed named KD C chain is the canceled-successor cleanup tail
below (27 functions, counting source-level wrappers even when inlined). This is
a conservative source call-shape witness, not a statement that all 27 compile
to frames or that a source count alone bounds bytes. The normal callback and
retirement alternatives are shorter; Linux inline/external helpers and trace
bridges must be weighted separately from actual object code.

1. mutex_api.c::run_native
2. episode.c::kd_episode_acquire_root
3. jit.c::kd_jit_acquire
4. rw.c::kd_rw_write_acquire
5. mutex.c::kd_mutex_acquire
6. mutex.c::kd_mutex_await
7. mutex.c::serve_writer_cohort
8. mutex.c::wait_cohort_release
9. mutex.c::progress_wait
10. jit.c::progress_wait
11. episode.c::wait_progress
12. owner_progress.c::kd_owner_progress_run
13. mutex.c::kd_mutex_finish_batch
14. mutex_release.c::kd_mutex_release_finish_physical
15. mutex.c::mcs_physical_unlock
16. mutex.c::cancel_queue_depart
17. mutex.c::cancel_actor_done
18. jit.c::cancel_departed
19. episode.c::cancel_departed
20. episode.c::finish_cancel_queue
21. task_storage.c::kd_task_cancel_actor_finish
22. request_pool.c::kd_request_user_finish
23. request_pool.c::drop_user
24. request_pool.c::reusable_locked
25. request_pool.c::controls_idle
26. request_pool.c::components_idle
27. request_pool.c::image_idle (or user_idle)

The prefix through owner_progress_run has an equal-depth alternative:
serve_writer_cohort -> execute_selected -> kd_jit_mutex_drive -> episode.run ->
pump -> owner_progress_run. The owner pump never executes another proxy. It
handles ready release controls, finishes physical batches, then reaps exact
users. Physical callback and reap are sequential branches.

For trace-stack weighting, drop_user -> free_locked is another tail. Its scalar
argument computations return before trace dispatch; controls_idle/component
checks are not simultaneously live with the listener's frames. Do not add both
tails as though one called the other. mcs_physical_unlock's rw_writer_exit ->
wake_up_all branch and its canceled queue cleanup branch are likewise separate.

## Indirect callback bindings

| Call site / pointer | Bound target for this configuration |
| --- | --- |
| mutex_entry.S entry.run | mutex_api.c::run_native |
| source node ops.selected_local | jit.c::accept_local -> episode.c::selected_local -> kd_owner_progress_track |
| source node ops.execute_proxy | jit.c::execute_selected |
| source node ops.wait_progress | jit.c::progress_wait -> episode.c::wait_progress -> kd_owner_progress_run |
| source node ops.wait_ready | jit.c::progress_ready -> episode.c::wait_ready -> kd_owner_progress_ready |
| source node ops.cancel_departed | jit.c::cancel_departed -> episode.c::cancel_departed -> finish_cancel_queue |
| driver.run | episode.c::run |
| driver.granted | episode.c::granted -> finish_cancel_queue |
| driver.exported | episode.c::exported -> owner_progress_control_stopped, empty deferred/child lists |
| driver.selected_local | episode.c::selected_local |
| driver.wait_progress / wait_ready / cancel_departed | Episode functions above |
| source grant.drop | jit.c::drop_grant -> kd_mutex_grant_unlinked |
| release owner.unlock | mutex.c::mcs_physical_unlock |
| resources.config.resolve | runtime.c::resolve_operation -> mutex/spin/rw exact target tables |
| resources.config.classify_target | runtime.c::classify_target -> native target table / boundary and region loops |
| resources.config.report | runtime.c::report_exit, a no-op |
| resources.config.execution_ready | mmap_jit_profile.inc::jit_execution_ready, same-mm scalar checks only |
| image.entry | Exact generated pure prefix; no admitted C callee/nested source operation |
| source stack read_word / write_word | source_stack.c::read_word / write_word -> stack_word |
| kd_mutex_resume_entry done | episode.c::kd_episode_native_done |
| kdlock_observe tracepoint callback | provider.c::observe -> mmap_jit_profile.inc::jit_observe, if this is the admitted listener set |

runtime's episode stack starts NULL, then task storage installs the exact
held source-stack ops. No operation uses a guessed source-stack callback.
Image use drops unlink users; they do not synchronously compile/free code or
invoke arbitrary native callees. Source/native lifetime finalizers and image
publication/RCU destruction run in their separate cold lifecycle/control paths,
not as a nested image.entry callee. A detached canceled task can queue its
retirement work; queue_work's immediate call path belongs in the bound, while
the later retire_cancelled_work body runs on a workqueue task's own stack.

## External leaves still required for a byte bound

The following calls can occur on AUX and cannot be replaced by KD-only frame
sizes. Use exact existing-object disassembly/configuration and actual admitted
callbacks to close them:

- schedule / cond_resched, including the actual dynamic-preemption target,
  __schedule, context switch and finish_task_switch paths. Scheduler-class
  pick/enqueue/preemption callbacks and any active perf/trace hooks are external
  indirect branches; sched/core.o alone does not close their callees.
- prepare_to_wait / finish_wait and wake_up_all -> __wake_up, including wait
  entry.func. DEFINE_WAIT selects autoremove_wake_function ->
  default_wake_function -> try_to_wake_up for the writer wait shown here.
  The shared wait queue can contain other supported reader/native waiters;
  its actual admitted waiter functions must be accounted for.
- wake_up_process -> try_to_wake_up, scheduler-class enqueue/preemption paths,
  task references and possible final __put_task_struct/deferred-free leaves.
- raw spin lock/unlock and irqsave/restore helpers, including actual
  preempt-enable scheduling branches after unlock; cpu_relax is not a frame.
- queue_work/system_unbound_wq for the detached-canceled-storage branch.
- RCU read-unlock callbacks in image use admission, and the enabled observation
  tracepoint bridge/iterator plus provider observe -> jit_observe. Listener
  iteration is sequential, but an additional listener requires its own bound.
- Compiler/kernel instrumentation visible in the exact objects: stack checks,
  tracing/profiling hooks and return thunks. Do not use a frame-pointer CFA alone
  as the complete RSP reservation or assume hand-written/generated assembly has
  the compiler's mitigation instrumentation.

Normal KD control does not format log messages. The enabled observation listener
copies one scalar row under its guard. BUG_ON/ud2 paths are contract failures,
not a claimed bounded normal-execution continuation; do not convert those into
an operational logging stack budget or hide a reached failure.

Thus the narrow KD control shape is finite and has no admitted recursion, but
the AUX byte bound is not closed by this source review. The precise remaining
branch is compiled KD/generated-entry frame weighting plus the scheduler/wakeup,
trace/listener and instrumentation leaves above. Claiming a numerical margin
before those leaves close would overstate the current evidence.
