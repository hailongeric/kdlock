# More threads than CPUs (build #82)

The user asked on 2026-11-16 whether kdlock is affected when there are more
threads than CPUs. `bench/run_oversub.py` runs the nano bodies with 1, 2, 4
and 8 workers per CPU (worker *i* bound to CPU *i mod cpus*), on 8 and on 16
CPUs of node 0, Native and kd alternating, 2 rounds of 2 s each.

| | |
|---|---|
| kernel | `7.0.0-38-kdclaude1` `#82 SMP PREEMPT_DYNAMIC Mon Nov 16 01:37:01 UTC 2026`, commit `9ac62b01` |
| host | as round 12: 64 vCPUs as 2 nodes of 32, fixed at 2.7 GHz |
| points | 224 (8 profiles x 7 placements x 2 backends x 2 rounds), all data checks passed, no worker without operations, kernel log clean |
| files | `os82.jsonl` (per point: rate, least/most operations per worker and per CPU, `starved`, kdlock counter deltas), `os82.log` |

## TCLock

TCLock is not in the table. Its mutex and rwsem adapters allow one
registered task per CPU. Its spinlock, with two workers per CPU, crashed the
guest twice within seconds of starting the point:

```
Kernel panic - not syncing: stack-protector: Kernel stack is corrupted in: __schedule+0x198b/0x19c0
CPU: 1 PID: 6009 Comm: kdb/1.1 ... 7.0.0-38-kdclaude1 #82
```

The second time nothing else ran: five runs of the same point with the kd
backend had just completed with their data checks passed, and the panic
came during the first TCLock run that followed. `kdb/1.1` is the second
worker of CPU 1. The serial logs of both are kept on the host
(`/home/eric/vm/qemu-claude-serial-panic-b82-*.log`). TCLock is the
unchanged reference implementation and is not changed here; the runner skips
it wherever a CPU has more than one worker.

## Results

kd/Native, median of 2 rounds. *fair* is the least over the most operations
per worker; *del/ses* the sections a kd session executed on average.

| profile | CPUs | x1 | x2 | x4 | x8 |
|---|---|---|---|---|---|
| spin c01 | 8 | 0.99 | 1.01 | 1.01 | 1.01 |
| spin c01 | 16 | 1.38 | 1.38 | 1.37 | - |
| spin c08 | 8 | 1.08 | 1.08 | 1.08 | 1.08 |
| spin c08 | 16 | 1.19 | 1.17 | 1.17 | - |
| rwlock writers | 8 | 1.38 | 1.38 | 1.39 | 1.38 |
| rwlock writers | 16 | 1.68 | 1.69 | 1.69 | - |
| rwlock 20% writes | 8 | 0.90 | 0.90 | 0.90 | 0.90 |
| rwlock 20% writes | 16 | 0.91 | 0.91 | 0.91 | - |
| mutex c01 | 8 | 1.14 | 1.38 | 1.30 | 1.20 |
| mutex c01 | 16 | 1.11 | 1.62 | 1.53 | - |
| mutex c16 | 8 | 1.34 | 1.31 | 1.18 | 1.16 |
| mutex c16 | 16 | 1.40 | 1.46 | 1.43 | - |
| rwsem writers | 8 | 1.09 | 1.41 | 1.33 | 1.31 |
| rwsem writers | 16 | 1.04 | 1.50 | 1.50 | - |
| rwsem 20% writes | 8 | 2.71 | 2.59 | 2.66 | 2.64 |
| rwsem 20% writes | 16 | 2.80 | 2.83 | 2.73 | - |

### Spin class: no effect

Spinlock and rwlock rates, Native and kd alike, are the same from one to
eight workers per CPU. A spin-class waiter and holder run with preemption
off, so at any time only one thread of a CPU takes part in the lock; the
others wait on the run queue and the lock never sees them. The only change in
kd is that sessions end at `need_resched()` more often (`stop_resched` 1-22
per run with one worker per CPU, 225-3900 with more), because the CPU of a
combiner now has other work. With 4000-section sessions that is invisible
(16 CPUs: 4000 -> 3500 sections per session).

### Sleepable class: both lose, kd less

Mutex and rwsem holders and waiters can lose their CPU. Native's rate falls
by 20-38% from one worker per CPU to two; kd's by 16-22% for the mutex. kd's
lead over Native grows: 1.04-1.40 with one worker per CPU, 1.16-1.62 with
more.

What it costs kd is the length of its sessions. A waiter that queued with
its continuation spins with preemption off; when its CPU has another task to
run it withdraws and sleeps (`abandon` 200-500 per run, `parked` 1250-3300),
a queue head whose holder lost its CPU sleeps (`head_sleep`), and a caller
that finds the holder off its CPU does not queue (`no_spin`). The mutex goes
from about 3900 sections per session to 1000-2900.

The rwsem with writers only is hit hardest: 11-33 sections per session
instead of about 3900, because a writer that took the lock by the fast path
and was then preempted keeps the queue head waiting through its whole spin
budget (`kd_rwsem_wspin_ns`) before it sleeps holding the queue. It is still
1.31-1.50 times Native, but its shares per worker are less even than
Native's (least over most per worker with four per CPU: 0.35-0.51 against
0.50-0.70). With 20% writes kd is the more even of the two (0.45-0.91
against 0.26-0.57).

No worker went without operations in any point.

### Open

The rwsem writer session collapse under oversubscription: a queue head
could stop spinning for a writer bit whose holder is off its CPU, as
`kd_mutex_can_spin()` does for the mutex owner. The rwsem's writer bit has
no owner field to look at; recording one would cost the fast path a store.
