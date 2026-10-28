# Mutex producer preemption

The production-extraction unit driver is
`mutex/test_mutex_proxy_pin.py`. It checks scheduling before selection, the
origin's pin acknowledgement, ordinary head handoff, same-CPU refusal and
physical acquisition with scheduling enabled. Negative mutations must fail.

The live payload first performs 400,000 lock acquisitions under contention on CPUs 0–3
with the matching `target_process=kd_proxy`. It then holds a KD mutex on CPU 0,
lets CPU 2 reserve the delegation gate, publishes a head on CPU 1 and a second
producer on CPU 3, and schedules a witness on CPU 3. The witness must run before
the owner releases. The owner has a five-second release deadline, every created
thread is joined and all four protected effects plus final lock drain are
checked. Exact published waiter counts prevent a local sleeping path from
passing as delegation waiting. This distinguishes preemptible queued waiting from the former pinned
wait without treating oversubscription as a supported general design.

Run only in the verified recovery VM through `run.py --output <new-external-path>`.
It freezes inputs, builds provider and payload, checks the exact kernel result
and retires sources before unloading. The payload deliberately prepares no JIT
image. Proxy execution and retirement require the separate affected basic/JIT
checks; this scheduling probe alone cannot establish them.

## Strict current-request preparation overlap candidate

This separate candidate starts from the archived
`658b918a05cb930d52ccf7307b8d44d54c6d6265` strict pin implementation. It has no
permission to pin a successor or a selected group. The combiner publishes
`KD_MUTEX_PROXY_REQUEST` for its one current ABI2 MINIMAL request only after
the existing ready-image and executor-context checks. While that origin prepares
its pin acknowledgement, the executor initializes its own frame from stable
published node metadata. It then acquire-observes `KD_MUTEX_PROXY_PINNED` before
image/call preparation, fallback dispatch or generated execution. Origin GS and
native stack contents are never accessed during the overlap. Legacy stack
decoding now obtains its pin acknowledgement before its first stack read.

Even when the short frame preparation returns NULL, the executor must consume
the requested pin acknowledgement before fallback or cancellation. It cannot
withdraw REQUEST while an origin may still publish PINNED. If later setup or
dispatch refuses the request, the existing frame retirement precedes the WAIT
publication and queue handoff. Private frame construction retains its source-open
check; final image/call preparation and dispatch checks stay after the ACK. The
surrounding batch lease keeps published source storage resident. No ACK
timeout authorizes cancellation. Node geometry, queue order, 1024/1024 limits,
polling/scheduling behavior and the two-word ABI are unchanged.

The pointer distinction is explicit: `&node->regs` addresses the reserved queue
packet, whose IP/SP/BP and task/GS address values were published by the origin.
Copying those values does not dereference the original stack or access its GS
storage. `kd_exec_frame_push_mutex_batch` selects the executor's `this_cpu`
context; `kd_source_is_open` reads provider state. Its optional context/frame
validators walk executor frame and lock-ledger metadata, without dereferencing
the borrowed packet's SP or the saved GS address. Actual legacy stack decoding,
generic frame handling and wrapper execution remain after PINNED. The existing
successor prefetch still issues cache hints for published stack addresses before
selection; those hints consume no stack values and are unchanged here.

After a successful legacy pin, an invalid decoded return, absent ready image or
busy executor context returns without constructing a frame. The sole caller,
`kd_mutex_run_combiner`, handles every such nonzero refusal through its common
PINNED-to-WAIT publication before queue rejoin. A failed generic frame push takes
the same path; a constructed-frame refusal first aborts/pops that frame. An
origin observing WAIT enables preemption and resumes queued polling. If immediate
native head publication replaces WAIT with zero before the origin observes it,
the waiter returns with one pin and `kd_mutex_wait_and_lock_node` enables
preemption before its physical-owner wait. Neither path leaves a queued origin
pinned indefinitely. These availability and ownership checks do not change the
trusted-source translation policy.

The archived candidate lost 42–54% at the measured contended c01/c16 points.
At 20 workers, c01 ran entirely within NUMA node 0 and returned-JIT share rose
from 99.2823% to 99.6205%; reduced delegation does not explain that loss. The
strict protocol adds a serialized REQUEST/ACK round trip per body. Overlapping
private preparation can hide some of that wait, but it does not remove the
round trip or establish throughput parity. This candidate is source-only until
its own checks and matched timings are recorded; archived passes and failures
remain evidence for their original source version.

Focused VM validation is basic plus `mutex/test_mutex_proxy_pin.py`,
`mutex/test_mutex_outer_progress.py`, `mutex/test_mutex_terminal.py`,
`mutex/test_mutex_policy.py`, `mutex/test_mutex_resources.py`,
`mutex/test_mutex_head.py` and `mutex/test_mutex_wait_clobber.py`. The first
fixture covers successful and failed private preparation, request refusal and
ACK ordering with mutation checks. The outer-progress fixture compiles the real
caller and combiner, including failed generic preparation and an unstarted
dispatch refusal whose frame must retire before WAIT. Scheduler/frame/JIT
primitives remain explicit substitutes. Follow with the live scheduling probe
and the existing returned-JIT basic check before a separate matched c01/c16
timing round. No kernel build or real-world API run is required.
