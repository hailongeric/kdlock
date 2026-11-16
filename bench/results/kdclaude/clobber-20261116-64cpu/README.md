# Clobber entries (`kd_*_cl()`): what two fewer packet lines buy

The user asked on 2026-11-16 for a macro form of the lock API whose call
declares the callee-saved registers lost, so that a waiter's continuation is
a few words and the combiner reads fewer of the waiter's cache lines. The
mechanism is LOCKS 8; this directory has its measurements.

| | |
|---|---|
| kernels | `#83 SMP PREEMPT_DYNAMIC Mon Nov 16 16:04:00 UTC 2026` (A/B, correctness), `#84 ... 16:31:32` (the same plus the `cl_offered`/`cl_done` counters; correctness again) |
| host | as round 12: 64 vCPUs as 2 nodes of 32, fixed at 2.7 GHz |
| defaults | as round 12; `CONFIG_KDLOCK_CLOBBER_ENTRY=y` |

## Correctness

* `run_corr.py` with eight new bodies (spin, mutex, rwlock and rwsem through
  the clobber macros; a handback body each for spin and rwsem; a body that
  alternates a clobber lock with an ordinary release and the reverse; the
  nesting body with a clobber outer lock), Native, kd and TCLock: 586 points,
  0 failed, 0 kernel complaints, on #83 (`corr83.jsonl`) and on #84
  (`corr84.jsonl`). The single-task API check passes.
* What the counters say (#84, 32 workers, `b84-counters.txt`):

| body | delegated | `cl_offered` | `cl_done` |
|---|---|---|---|
| spin, mutex (ordinary entries) | 6.74 M, 4.03 M | 0 | 0 |
| spin, mutex (clobber) | 6.63 M, 3.93 M | 6.63 M, 3.93 M | = delegated |
| rwlock, rwsem writers (clobber) | 1.06 M, 1.59 M | 1.88 M, 1.62 M | = delegated |
| spin with a handback every 16th section | 5.47 M | 5.83 M | 5.47 M: the 0.36 M handed back left with a full state |
| spin, clobber at one end only | 6.14 M | 3.04 M | 3.10 M: compact exactly where the release is a clobber one |
| nesting with a clobber outer lock | 2.16 M | 2.16 M | 2.16 M |

The ordinary entries never produce a compact state, and a section ends
compact only at a clobber release.

## Performance (`cl83.jsonl`, `cl83ref.jsonl`)

In-boot A/B on #83, kd only: each profile through the ordinary entries and
through the clobber macros, the two runs one after the other, 3 rounds of
1 s. Rate through the clobber entries over the rate through the ordinary
ones (median of 3; the three rounds of each side in the file):

| profile | 4 | 8 | 16 | 32 | 48 | 64 |
|---|---|---|---|---|---|---|
| spin c01 | 0.997 | **1.022** | **1.034** | **1.032** | **1.033** | **1.029** |
| spin c08 | **0.998** | **1.049** | **1.021** | 1.001 | **1.006** | 1.001 |
| rwlock c01, writers only | **1.015** | **1.023** | **1.032** | **1.032** | **1.038** | **1.028** |
| rwlock c16, 20% writes | 0.996 | 0.998 | 1.003 | 1.002 | 1.028 | 1.000 |
| rwsem c01, writers only | **1.021** | **1.010** | 1.005 | **1.018** | 1.007 | **1.010** |
| rwsem c16, 20% writes | **1.007** | **1.017** | **1.017** | **1.021** | **1.016** | **1.013** |
| mutex c01 | **0.995** | 1.060 | 1.004 | 1.005 | **1.005** | **1.018** |
| mutex c16 | **0.997** | **1.011** | 0.999 | **0.995** | **0.992** | 0.997 |

Bold: the three rounds of the two sides do not overlap. At 4 workers the
locks are mostly in plain mode and nothing is published, so what shows there
is the cost or gain of the call sites themselves.

* The gain is real and small: 2-4% where the section is one line (spin and
  rwlock writers, from 8 workers), 0.5-2% for the rwsem, up to 2% for the
  mutex from 48 workers, and -0.5 to -0.8% for the mutex with sixteen lines
  at 32 and 48 workers.
* Per section, spin c01 at 32 workers: 155 ns through the ordinary entries,
  150 ns through the clobber ones, so the two packet lines that are no
  longer fetched cost about 2.5 ns each. They were already requested one
  section ahead and, for the spin class, demoted by the waiter (CLDEMOTE),
  so what they cost was bandwidth and coherence work more than latency.
* The mutex with sixteen lines loses because the price moves to the caller:
  the body function now saves five registers in its prologue and reloads
  what it keeps across the lock and release calls, on every call, delegated
  or not.

The ordinary entries on #83 against round 12 (#82): the packet layout
changed for them as well (same four lines, different order, one more byte
store). Across two boots only ratios to the references are comparable, and
the references themselves moved by up to 7% between the boots; kd/TCLock for
the spin class is unchanged (spin c01 1.36-1.44 -> 1.38-1.46, rwlock
writers 1.50-1.94 -> 1.50-1.98), and no change beyond that spread is
visible elsewhere.

## Would the continuation in the queue node save more?

The remaining compact state is lines 0 and 1 of the packet: `rsp`, `rbp`,
`rip`, flags, `task`, `canary`, `stack_top` (line 0) and the execution
bookkeeping the combiner and the origin both write (line 1: preempt and RCU
depth, nesting roots, `site`, `jit_resume`). The node line holds 32 bytes of
queue fields and, in `nodes[0]`, the per-CPU fields the plain path depends on
(they were moved there because a separate line cost the plain path 4-12% at
3 to 5 workers). Line 0 does not fit beside them, and line 1 cannot go away
because the origin reads it when it resumes. At the measured 2.5 ns per line,
moving line 0 into the node would be worth about 1.5% for one-line sections
and would cost the plain path a line of its own again. It is not done.
