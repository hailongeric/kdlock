# QEMU auxiliary-worker admission, qemu-workers-v1

This explicitly selected admission policy compares the same VM and includes
its observed QEMU auxiliary-worker activity. It does not declare workers
harmless, attribute their I/O to a guest operation, or alter historical
qualification. The corrected small validation was authorized after the
82-task Native admission refusal; that refusal demonstrated a mismatch with
the empty role manifest, not a kdlock defect. The 15 extra workers were
observed after boot; the evidence does not prove boot created each worker.

The retained captures identify QEMU PID 257489, process start ticks 42969155,
command SHA-256
`08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917`.
The 64 vCPU task identities/pins and three fixed service tasks stay exact.
CPU/NUMA placement, memory bindings, frequency policy, two qcow2 drives and
the rest of the QEMU command remain unchanged. The initial 67-task, rejected
82-task and final recovery 68-task captures are retained in the
[stopped-screen record](../results/10.176.26.71/bench/mmap-window-screen-20261026/README.md).

Only auxiliary tasks read beneath that bound QEMU process, with matching
`Pid`/`Tgid` status, `comm=worker`, and affinity exactly `[63]`, match the
`qemu_worker` role. A name alone never establishes membership. Process
identity is checked before and after each complete scan. Between complete
scans the role may gain or lose task lifetimes; TID reuse creates a distinct
`(tid,start_ticks)` record. Core identity changes, unknown roles, affinity
drift, counter regression and incomplete/inconsistent scans still fail.

CPU, scheduling and I/O activity is recorded per observed lifetime without a
zero-activity requirement. First/last counters do not cover time before first
observation, after departure or tasks entirely missed between scans. A task
disappearing during a scan produces retained incomplete evidence and a stop,
not an inferred harmless retirement. Fixed policy `fixed-aux-v1` retains its
frozen auxiliary inventory and existing inactive/expected-service classes.

Native and KD bind the same role manifest and unchanged image, workload,
placement and instrumentation. Each arm waits a recorded 90 seconds after
timed-payload setup and before launching the unchanged client. The interval
is scheduled once, not repeated until a capture passes; existing control
barriers and window deadlines remain. Guest idle and single-owner checks
remain required. QEMU task membership is not proof that unrelated host jobs
are absent; independent host isolation/competing-work checks remain necessary.

Report worker lifetimes and activity beside each rate. One validation pair
has no variability estimate or optimization conclusion. Repeated matched
pairs are needed for ranges and sample CV. Old failures cannot be accepted
under this new policy because they lack its complete bound evidence.
