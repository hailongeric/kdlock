# will-it-scale on 64 CPUs: page faults, mmap, brk

Four unchanged will-it-scale tests, `threads` and `processes`, with
`mm->mmap_lock` as a native `rw_semaphore` or as a `struct kd_rwsem`. The
`kd_mm` parameter decides which backend a *new* `mm` gets, so both run on the
same kernel and the same boot and the runner alternates them per point. This is
the data behind [`../../../docs/MMAP_LOCKS.md`](../../../docs/MMAP_LOCKS.md).

## Identity

| | |
|---|---|
| guest | `kdclaude`, 64 vCPUs as 2 nodes of 32, 24 GiB |
| host | Xeon Gold 6438N, all 64 host CPUs fixed at 2.7 GHz, turbo on, governor performance |
| kernel | `7.0.0-38-kdclaude1` `#72 SMP PREEMPT_DYNAMIC Sun Nov 15 07:26:18 UTC 2026`, `CONFIG_KDLOCK_MM=y`, `CONFIG_PER_VMA_LOCK=y` |
| defaults | `kd_batch` 4096, `kd_vdown` 1, `kd_cldemote` 3, `kd_rwsem_rphase_ns` 1000, `kd_rwsem_rspin_ns` 50000, delegation on |
| runner | `bench/run_mmap1.py --models threads processes --workers 1 2 4 8 16 32 64 --backends native kd --rounds 2 --samples 3` |
| points | 4 tests x 2 models x 7 counts x 2 backends x 2 rounds = 224, 0 failed, no kernel complaints |

The tests (`bench/wis/tests/`, TCLocks' copy, unchanged):

| test | body of one iteration |
|---|---|
| `mmap1` | map 128 MiB anonymous private, unmap it **untouched** |
| `mmap2` | the same with a `MAP_PRIVATE` **file** mapping of 128 MiB |
| `page_fault1` | map 128 MiB anonymous, store to **every page**, unmap |
| `brk1` | `brk` one page up, one page down |

## Files

| file | content |
|---|---|
| `wis_<test>.jsonl` | one record per point: rate, identity, kdlock counter deltas |
| `wis_<test>.log` | the runner's live output |
| `wis.md`, `wis.csv` | all four tests as tables; regenerate with `python3 bench/wis_table.py <dir>/wis_*.jsonl [--format csv]` |
| `pf_base.jsonl`, `pf_rspin0.jsonl`, `pf_rp0.jsonl` | the `page_fault1` attribution run below |
| `mm2_vd0.jsonl` | `mmap2` with the virtual downgrade off |

## Threads: the four tests side by side

kd/Native, median of two rounds; the counters are the medians of the kd rounds.

| workers | `mmap1` | `mmap2` | `page_fault1` | `brk1` |
|---|---|---|---|---|
| 1 | 0.98 | 1.00 | 1.00 | 0.99 |
| 2 | 1.05 | 0.98 | 0.91 | 1.04 |
| 4 | **1.25** | **0.78** | 0.88 | 0.84 |
| 8 | **1.37** | **0.83** | 0.84 | 0.95 |
| 16 | **1.30** | **0.80** | 0.86 | 1.04 |
| 32 | **1.33** | **0.83** | 1.02 | 1.07 |
| 64 | **2.06** | **0.86** | 1.06 | 0.91 |

| test | delegated bodies per run | sessions | handback | what the counters say |
|---|---|---|---|---|
| `mmap1` | 6.7-7.0 M | 1.7-4.2 k | 19-1168 | ~3500 waiter sections per session: the mechanism working |
| `mmap2` | 15-35 | 1.16-1.35 M | = sessions, all `hb_frontier` | every session stops at the first instruction it may not run |
| `page_fault1` | 0-253 | 1-146 | 1-94 | delegation is not happening at all |
| `brk1` | 83-1362 | 72-1385 | ~= sessions | the section reaches a frontier at once |

`processes` gives every worker its own `mm`, so there is nothing to delegate:
all 28 ratios are 0.95-1.11 and the counters are three digits at most. The one
number worth keeping from it is `page_fault1 / processes` at 64 workers,
7.64 M vs 7.31 M faults/s (0.957): that is the price of the indirection alone,
with no contention anywhere.

## page_fault1: there is no mmap_lock in the fault path

`CONFIG_PER_VMA_LOCK=y` and `arch/x86/mm/fault.c:1325` calls
`lock_vma_under_rcu()`, so a page fault normally takes no `mmap_lock` at all.
The counters agree: about a hundred delegated bodies in a nine-second run. The
9-17% loss at 2-16 threads is therefore **not** a delegation cost; it is the
cost of `mm->mmap_lock` being a kd rwsem while the test's `munmap` of a fully
populated 128 MiB region holds the write side for milliseconds.

### page_fault1 attribution

`threads`, both rounds printed, same boot, build #72. `kd_rwsem_rspin_ns` is
how long a reader that finds the write side held spins before it deregisters
and queues on `->m` to sleep (`kernel/kd_rwsem.c`, `kd_down_read_admit`);
`kd_rwsem_rphase_ns` is the window a releasing writer leaves the readers.

| workers | Native | kd, defaults | kd, `rspin_ns` 0 | kd, `rphase_ns` 0 |
|---|---|---|---|---|
| 2 | 1.124 / 1.108 | 1.028 / 1.017 | 1.022 / 1.008 | 1.013 / 1.007 |
| 8 | 2.777 / 2.749 | 2.253 / 2.243 | **2.563 / 2.587** | 2.339 / 2.362 |
| 16 | 3.020 / 3.043 | 2.412 / 2.400 | **2.783 / 2.631** | 2.406 / 2.584 |

M faults/s. Turning reader spinning off recovers about two thirds of the gap at
8 and 16 threads (0.81 -> 0.93, 0.80 -> 0.90 of Native); the reader phase has
no effect. So the loss is readers burning a 50 us spin budget against a write
holder that will not leave for milliseconds, and hammering the counter line
the writer is using while they do it.

This is not a reason to lower the default: reader spinning is what the
reader-heavy rwsem profiles of round 10 live on. What it needs is a rule - a
reader that registered behind an *active* writer has no reason to keep spinning
once it has seen the phase counter stand still - not a different constant. That
is open work.

## mmap2: one nested lock ends every session

`mmap1` and `mmap2` differ in one thing: the file. In `vma_prepare()`
(`mm/vma.c:297`) a file mapping takes `i_mmap_lock_write(vp->mapping)`, which
is `down_write(&mapping->i_mmap_rwsem)`, and `down_write` is in the
translator's frontier list - a native sleeping lock's slow path prepares to
sleep for its own task, so only the origin may run it. The counters show the
result exactly: at 16 threads, 1 279 253 sessions, 1 279 244 handbacks, **all
of them `hb_frontier`**, and 16 bodies delegated. Each session pays for an
offer, a packet, a queue node and a handback, and executes nothing.

`mmap1` escapes this because an untouched anonymous mapping has no file, no
`anon_vma` to lock in `vma_prepare`, no present PTEs and no page tables, so
`tlb_flush_mmu_tlbonly()` returns at its first test and no shootdown IPI (also
a frontier) is sent.

### mmap2 with the virtual downgrade off

`vdown` is 1.279 M of the 1.279 M sessions and `vdown_hb` 1.278 M, i.e. the
handback happens while the combiner holds the write side at a downgrade, so the
downgrade is worth ruling out as the cost. `mm2_vd0.jsonl`, `threads`, both
rounds, same boot:

| workers | Native | kd, `vdown` 1 | kd, `vdown` 0 |
|---|---|---|---|
| 4 | 315 / 335 (vd1), 293 / 308 (vd0) | 252 / 253 (0.78) | 273 / 255 (0.88) |
| 16 | 312 / 325 (vd1), 310 / 303 (vd0) | 252 / 260 (0.80) | 257 / 253 (0.83) |

Thousands of ops/s; the ratio is against that run's own Native. Turning the
downgrade off takes back about half of the loss at 4 threads and nothing at 16,
and the handback count does not change (1.29-1.38 M, still all at the
frontier). So the downgrade is a minor part of it: what costs is opening a
session that cannot execute anything. `mmap2` needs
`mapping->i_mmap_rwsem` handled, not a tunable - see
[`../../../docs/MMAP_LOCKS.md`](../../../docs/MMAP_LOCKS.md).

Note that `mmap2`'s Native rate itself moves by 7% between these runs, which is
why every ratio here is taken against the Native points of the same run.

## brk1

`brk` write-locks `mmap_lock` on every call, but the section reaches a frontier
almost at once (the shrink path flushes the TLB), so sessions and handbacks are
equal and nothing is delegated. The rate stays inside the run-to-run spread:
the kd rounds at 4 threads are 715 k and 652 k, a 10% spread by themselves, so
the 0.84 in the table above is not a result. `brk1` is parity, not a gain and
not a loss.
