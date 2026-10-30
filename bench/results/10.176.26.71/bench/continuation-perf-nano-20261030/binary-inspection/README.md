# f7a84065 built-provider inspection

The actual fetched provider has the intended mutex wake layout, smaller spin
batch/stack/initialization, and terminal context-refresh bypass. Static branch
review found no blocker to the separately planned live checks. This is not a
performance result or a substitute for live validation.

Candidate source: `f7a84065e84474380faa37eeadfdf534abd72a68`.
Provider SHA256: `93a892843297888e1a000d41dcc560de4fd9fabd74d3d90f95ef68406b3b3c6d`.
The supplied completed unit/build owner is
`/tmp/kdlock-continuation-f7a84065-unit-owner.json`, SHA256
`2356a8d0ee6a5ffd9be052a1a33db0845faada3e47b15b77fbf55a3662fbc70f`;
its source and provider hashes match. It records three fresh checks and six
reused checks, not nine fresh checks. The reference is the previously identified
8617 unit provider whose executable/allocated bytes and relocations were already
matched to all ten measured 8617 providers.

| Actual built property | 8617e97c | f7a84065 |
| --- | ---: | ---: |
| `__kd_mutex_lock_slowpath` bytes | 1170 | 1145 |
| `native_resume==0` branch | Taken `je` | Fall-through; nonzero takes `jne` |
| DWARF `kd_spin_batch` bytes | 208 | 200 |
| `counter` / `proxy_context` offsets | 184 / 180 | 180 / 182 |
| `queue_end` / `saved_tail` offsets | 192 / 200 | 184 / 192 |
| Main spin-combiner stack reservation | 0x120 | 0x110 |
| REP initialization qwords, both sites | 25 | 24 |
| `run_combiner` bytes | 5169 | 5207 |
| `kd_exe_dispatch` bytes | 12016 | 12016 |
| Provider `.text` bytes | 134694 | 134694 |

All 19 inspected rwsem routines, `kd_exe_dispatch` and
`kd_mutex_run_combiner` retain identical raw instruction bytes and normalized
listings. The shared writer dependency on the mutex slowpath still changes.
`kd_mutex=32`, `kd_mutex_node=320`, `kd_spin_node=128` and
`kd_exec_frame=656` are unchanged. Smaller stack/initialization does not mean a
smaller spin function: the actual function grows 38 bytes, while total provider
text size is unchanged. No throughput improvement is inferred.

## Manual control-flow review

All addresses below are offsets in the candidate ELF `.text`, not runtime load
addresses. Relocation/source-line listings accompany the ordinary disassembly;
unresolved ET_REL branch displacements must not be read as final targets.

The repeated mutex poll remains PAUSE at `0x1307a`, byte load of node offset
`0x131` at `0x1307c`, test and backward `jne` at `0x13087`. The following
`native_resume` load uses the unchanged DWARF offset `0x132`; `0x13094` is now
`jne 0x13323`. Zero falls directly into the completed-byte check at `0x1309a`.
The nonzero branch retains the outcome-2 discriminator and native outcome-1
handling. Its outcome-2 relocation leads to the cold service at `0x20609`, calls
`kd_mutex_origin_instruction_waiter` at `0x2060c`, then relocates back to the
locked-node read at `0x1307c`. The helper/ACK protocol was not changed.

The two source generic-dispatch paths merge into one physical `execute_cs` call
at `0x15367`. The pending-FULL path installs its hook at `0x15358`; the fresh
generic path joins through `0x156d0` to `0x1535f`.

- On return, `lea -2` and unsigned comparison at `0x1536f–0x15375` identify
  NO_RUN=2 and RUN_ERROR=3 and jump to `0x156f0`, before physical-context reads.
  That path restores the speculative NUMA tail and returns through the existing
  native-handoff/splice handling. The optional NO_RUN logging jump has a
  relocation to `run_combiner.cold` at `0x20a11`; its return relocation resumes
  at `0x1573d`. It does not fall into the unrelated next-node scan shown by the
  placeholder displacement in an unrelocated listing.
- The outer-released byte is tested at `0x1537b`; `jne 0x1574c` precedes context
  capture. Native-done skips duplicate completion; other completed outcomes
  pass through `0x153ab`. Both reach the outer-reclaim exit at `0x15756`, without
  entering another root or refreshing a discarded context cache.
- All other generic returns execute the preemption read at `0x15386`. Valid
  count-one state continues through current-task/migration/RCU checks at
  `0x158b8`; IRQ flags are read via the `pv_ops` relocation at `0x158dc`.
  Ineligible state produces zero. Every path stores the resulting context byte
  at `0x1539e`, before completion/refill and another root.
- A later ordinary root compares its saved context with that refreshed byte at
  `0x15620–0x15635`; mismatch or zero branches to refusal at `0x1578c`. The
  existing virtual-continuation branch remains distinct. The unchanged
  completed-simple-JIT path does not gain a context capture.

The counter increment is now `addw` at `0x15416`. Its cap check uses the high
byte (`cmpb $4` at `0x153d9`), equivalent to unsigned counter >=1024 for this
bounded 16-bit value. The counter starts at zero, and the existing check stops
before another root once 1024 bodies have been counted. The separate NUMA scan
budget remains a 16-bit field at offset178 and has its independent decrement.

## Evidence and limits

`comparison.json` contains exact function hashes/sizes, normalized comparison,
DWARF member offsets and branch windows. The `.relocations-lines.dis` files bind
the optimized paths to source lines and relocation targets. Extra cold listings
and `cold-relocations.json` retain the manual tail review. Normalization does
not establish runtime-address/cache equality or complete relocation identity.

The prepared tool was run once against the supplied hash and completed without
an inspection failure. Its exact arguments/tool hash are in
`inspection-receipt.json`; `manual-review-receipt.json` binds this additional
review and the source/build owner. No inspected ELF was executed. No build,
unit test, timing, VM action or repository edit was performed by this review.
