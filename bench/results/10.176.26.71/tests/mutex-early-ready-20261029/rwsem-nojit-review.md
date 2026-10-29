# Offline review of rwsem c01/w1/t8 (October 29)

The saved evidence does **not** identify a cause for the retained candidate's
24.91% loss. It rules out several simple explanations: changed workload machine
code, changed recorded virtual lock/data addresses, changed requested/observed
worker CPUs, and execution of the new mutex delegation waiter/combiner protocol.
The exact local rwsem instruction streams are unchanged from the preceding
single-current candidate, but their placement in provider text changes. Physical
page placement, cache/coherence costs and local waiting were not sampled.

## Exact measured point

All rows are the separate, single-round `rwsem-cacheline-c01-kdlock-w001-t08-r00`
session, using the public prepared ABI2 writer shell, bulk ioctl, 1% evenly spaced
writes, 256 post-work rounds and a 2-second interval. These are mechanism/nano
measurements, not real-world API evidence.

| Version | Whole Mops/s | Peak Mops/s | JIT bodies/completions |
| --- | ---: | ---: | ---: |
| `1c86d6d1` | 11.595956 | 11.630582 | 0 / 0 |
| `82bfc1006c25767d7a319fcf175c548dcf24824a` | 11.335999 | 11.414088 | 0 / 0 |
| `2af70f39a7091c34b5ccab98452f0726336cb2c0` | 8.707519 | 8.759482 | 0 / 0 |

The retained loss is present in both whole and peak intervals. It is not explained
by the small whole-run collector tail. All eight retained workers made less
progress; this is not one missing worker. Each worker consumed approximately
2 seconds of thread CPU time, with totals 16.000277, 15.997608 and 16.000651 CPU
seconds respectively. This argues against a large off-CPU/parking loss; it does
not measure short sleeps, spinning, memory stalls or host-side VM scheduling.

## Verified placement and workload equivalence

- Requested and observed workers are CPUs 0–7, all recorded as NUMA node 0;
  the collector is CPU 63. Data checks and exact final drain pass in all rows.
- Recorded lock and gate are both `0xffffffffc0ba45c0`, and the continuation entry
  is `0xffffffffc09ea03b`, in all three sessions. The decoded source bindings in
  saved `jit.S` identify the touched value at `0xffffffffc0ba4140` in all three.
  Both data and lock are 64-byte aligned, separated by `0x480` bytes. These are
  virtual addresses; no physical-page, page-NUMA, LLC-slice or cache-state record
  accompanies them.
- Exact archived workload ELFs have identical `.text` (5959 bytes), `.rela.text`,
  `.data`, `.rela.data`, `.rodata`, `.rela.rodata`, alternative instructions and
  selected metadata bytes. BSS size/alignment and symbol offsets match, including
  `rb_lock` (320 bytes), `rb_values`, progress slots and control fields. Whole ELF
  hashes differ; that is not a changed executable workload.
- Reader and writer call shells, parameter values, one-cacheline payload,
  1024/1024 provider policy and disabled UBSAN match. Published JIT image hashes
  differ between the baseline and later versions, but those images were not
  executed at this point.

## What the zero-JIT result establishes

`NO_JIT` alone would not exclude delegation admission or fallback. Here the final
per-load kernel receipts additionally report `slowpath=0`, `combiner=0`,
`handoff=0`, `max_waiters_per_cpu=0`, `origin_acquires=0` and no native escapes in
all three loads. `kd_mutex_lock_slowpath` increments its counter unconditionally
before the queue slowpath, and the final report sums all possible CPUs after
drain. The counter is not gated by optional diagnostics or `hotlock_stats`.
Thus the changed publication/READY/CLAIMED execution did not run in these loads.

The writer still calls `kd_rwsem_down_write_clobber_v1`; a prepared writer can
use the local fast owner path. The rwsem phase protocol, reader OSQ admission,
reader drainage and physical mutex paths remain relevant. Zero delegation
counters do not establish zero local contention or zero waitqueue activity.

The separate hotlock final receipts provide a narrower additional observation:
all eight CPUs have `checks=0` and `last_entries=0`, so their current mutex
observation windows were never reset. Summed entries are 236114/231742/178885,
exactly warmup plus measured writes; failed-CAS contention observations total
35/3/0. In particular, the retained public writer path recorded no failed
physical-mutex fast CAS. These are diagnostic observations, not owner records;
they do not count rwsem phase/reader-drain/reader-OSQ waiting. They offer no
support for physical-mutex parking as the cause of this point's loss.

## Provider code evidence and limits

Independent inspection of the exact archived nano providers finds that the
current-to-retained rwsem helpers have identical bytes and relocation records,
including read acquire/release, writer entry, delegate admission/exit, reader
drainage and write release. They move by `0x500` bytes. Local mutex and OSQ paths
are also unchanged, apart from relocation/displacement changes to unchanged
targets. The direct mutex clobber fast entry and unlock wrapper remain unchanged.
The provider companion JSON records exact function offsets, hashes and comparison
scope. A placement change is an observation, not proof that instruction-cache,
predictor or page effects caused the loss.

For example, `kd_down_read` moves from `0x1f520` to `0x1fa20` (820 bytes), and
`kd_up_read` from `0x1e7a0` to `0x1eca0` (36 bytes). The `0x500` shift preserves
their cacheline alignment; neither newly straddles a relative 4KiB boundary.
The optional `a46bf63c44bc81a32901dfd55e3c88a16954e262` build-gate provider keeps
these same retained offsets and bytes. That optional comparison is not a nano
timing result. Baseline-to-current also changes other gate/protocol code; selected
function equivalence does not mean all three providers are interchangeable.

Nearby saved points do not reproduce a general 25% local-path loss: c01/w1/t1
stays approximately 1.787 Mops/s; c01/w1/t20 is 8.390/8.525/8.608; c16/w1/t8 is
10.405/10.425/10.316; c01/w20/t8 is 5.976/5.866/5.968. This is contextual evidence,
not a substitute for repetition of the anomalous point.

The cheapest next discriminating measurement would be a matched, alternating
repeat of this exact point with frozen providers, followed only if reproducible
by unscored local-path/PMU and off-CPU observations. Existing receipts cannot
choose between code/data placement effects, local spinning/coherence, or run
variation. No fairness change or protocol optimization follows from this review.

## Reproducibility and validation scope

`/tmp/kdlock-rwsem-nojit-layout-review-20261029.json` contains numeric receipts.
`/tmp/kdlock-rwsem-nojit-layout-inputs-20261029/inputs.json` maps extracted files to
their exact archive members and SHA-256 hashes. The workload section comparison
and disassembly are retained beside those inputs. The companion provider review
is `/tmp/kdlock-rwsem-nojit-provider-review-20261029.json`.

Only static source/ELF inspection and offline archive/JSON analysis were performed.
No repository source was changed, and no build, test, VM command or timing was run.
