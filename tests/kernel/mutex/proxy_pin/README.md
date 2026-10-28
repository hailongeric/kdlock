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
