# Bounded generation-four mmap1 follow-up

Runner `00413a9ae078234b14933f4ed9a385f48d26e05c` changes only the allowed
count sequence and documentation. Runtime and translator bytes match
validated provider `eabe454b4ee51ea6962a73525372b4b09679c737`; its build and
focused checks were reused. No lock, continuation, backend, GS, discovery,
source-limit or image-publication implementation changed.

The prior retained generation-four images were verified against their recorded
hashes. They contain actual bodies for `unmapped_area_topdown` and `mas_mab_cp`,
and the caller paths push the real return word once before jumping into those
bodies. These images were inspected, not imported into the new epoch.

One fresh processes session used `[1,2,4,6,8]`, once per point, with a
900-second learning deadline and unchanged application lifetime checks. Four
priming applications precede the single final observation. Unchanged
will-it-scale `75f66e45697e6f5f49c33dd950c4e6b289198f8f` runs `-t N -s 2 -m`,
six warmup plus two measured samples. Kernel is `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, lazy preemption,
64 vCPUs and 24 GiB. Requesters use `0..N-1` on node 0; executors use 0–61
across both nodes and collector 63. Host policy is fixed 2 GHz.

Compilation and selected counters remain active. These are unscored learning
observations, not steady JIT performance. Counters include all warmup and
measurement; rates use the final two nominal samples. Results from different
learning schedules are not pooled. No new provider build, full suite or Nano
run was needed for the runner-only change.

| Processes | Pairs/s | JIT entries mmap/munmap | Fully delegated returns mmap/munmap |
| ---: | ---: | ---: | ---: |
| 1 | 220615.0 | 0/0 | 0/0 |
| 2 | 327626.5 | 2/2 | 0/0 |
| 4 | 380204.0 | 4/4 | 0/0 |
| 6 | 389485.5 | 6/6 | 0/0 |
| 8 | 391778.5 | 8/8 | 0/0 |

All five applications passed and drained. Both selected entries were generation
four before the final eight-process application and generation five afterward.
For mmap, 3134843 selected acquisitions comprised 3134835 local/no-image
acquisitions and eight JIT requests; munmap had 3134839 selected, 3134831
local/no-image and eight JIT requests. Each root had eight completed handbacks,
zero wholly delegated returns and zero cancellations. Observation conservation
passed. Generation five is unrun. These counts do not establish full delegated
MM completion or a delegated downgrade/read tail.

The eight-process rate is 76.86% below the preserved Native control of
1692926 pairs/s from
[the earlier comparison](../mmap1-scaling-f9fdaa2a/README.md).
That control used runner `14cc632d8e84010448ee84a6411f8bf8f5220a01`, the
same kernel Build ID with `kd_mmap=off`, and was not rerun here. Active learning
and selected observations distinguish this candidate run from a steady-image
score. No performance gain or acceptance is claimed. Prior runs, including
their decreases, remain in their separate reports.

## Why the next CALL misses recur

The final histories newly record `mas_wr_node_store` (`0xffffffff826b4a80`)
for mmap and `mas_leaf_max_gap` (`0xffffffff826b2720`) for munmap. The captured
generation-four source-comment graphs put each target at minimum direct-CALL
depth six from that generation's entry/history seeds, with the caller at
depth five. Here a direct CALL costs one; branches and caller continuations
cost zero. Minimum depth is recomputed over the shared graph, including all
initial seeds, rather than counting only the displayed path.

The initial seeds were:

| Root | Entry/history seeds, each at depth zero |
| --- | --- |
| mmap | `0xffffffff817b6f68`, `0xffffffff814f4a38`, `0xffffffffc0e32bb0`, `0xffffffff8181c0e0` |
| munmap | `0xffffffff8181c73b`, `0xffffffff814f4a38`, `0xffffffffc0e32bb0`, `0xffffffff826f0560` |

The newly recorded miss is excluded from these generation-four seeds. The
minimum structural chains are:

| CALL depth | mmap | munmap |
| ---: | --- | --- |
| 0 | `vm_mmap_pgoff+0x118` (`0xffffffff817b6f68`) | `__vm_munmap+0xbb` (`0xffffffff8181c73b`) |
| 1 | `do_mmap` (`0xffffffff817f7c10`) | `do_vmi_munmap` (`0xffffffff8181a5e0`) |
| 2 | `mmap_region` (`0xffffffff8181ba90`) | `do_vmi_align_munmap` (`0xffffffff8181a3c0`) |
| 3 | `__mmap_region` (`0xffffffff81819230`) | `mas_store_gfp` (`0xffffffff826c7340`) |
| 4 | `mas_store_prealloc` (`0xffffffff826c5620`) | `mas_wr_store_entry` (`0xffffffff826c4d50`) |
| 5 | `mas_wr_store_entry` (`0xffffffff826c4d50`) | `mas_update_gap.part.0` (`0xffffffff826b4850`) |
| 6 | `mas_wr_node_store` (`0xffffffff826b4a80`) | `mas_leaf_max_gap` (`0xffffffff826b2720`) |

The target visits are dynamically observed in the histories. These chains are
inferred paths in the selected source graph, not dynamic branch traces; they
neither establish the actual intermediate branch choices nor attribute all
eight handbacks. The retained archive analysis includes every zero-cost
transition and CALL edge, input hashes, seeds, source-line references and a
reproducible read-only script in `depth-review/`. No complete-kernel graph or
dynamic call-chain trace is claimed.

This matches the configured discovery boundary. `disassem/memread.py:194–207`
imports history targets; `disassem/disassem.py:369–370` fixes the initial
`call_roots`; `disassem/translation_scope.py:166–184` discovers a new callee
only while its caller depth is below five. Discovery and scope selection in
`disassem/disassem.py:556–567` retain the existing absent-callee boundary in
`disassem/context_policy.py:89–96`. New descendants do not become depth-zero
roots within the same compile. Learning a helper extends that helper's paths;
it does not reset callers or unrelated later work. Five is a discovery bound,
not a universal image-depth or runtime stack limit: already decoded bodies
can remain reachable beyond that depth.

The selected mmap caller block `0xffffffff826c5057` (source image line
151971) pushes return word `0xffffffff826c5062`; munmap block
`0xffffffff826b491b` (line 63789) pushes `0xffffffff826b4924`. Each jumps
to an exit-1 stub at its newly reached callee (lines 161156 / 97531).
Existing handback retains that real CALL word and starts at the callee; it
does not replay the CALL push. This is a coverage boundary, not evidence that
either helper is inherently non-delegable.

Both previous learned seeds have actual decoded bodies. The selected mmap
generation-four SHA256 is
`d4e19779467a04124b4fff43104c62bee10af4e896ec0c01d37e3e4d8dea107d`,
matching the image reviewed before this run. Fresh munmap priming instead
learned `__memcpy` at `0xffffffff826f0560`; its generation-four SHA256 is
`82fbe543c420a552627c4ada1cac67b3dd7f94a65affde3d1f9fe74c18e5d46f`.
This differs from the prior `mas_mab_cp` image. The current image contains
the `__memcpy` body, while `mas_mab_cp` remains a stub. Do not claim that the
earlier munmap body was executed, or equate generations across sessions.

All ten compiler jobs returned zero, with no `CONTEXT_NATIVE_ONLY` report.
The last generation-four coverage rows show mmap at 18 decode passes,
847872 cached bytes and 16742 decoded instructions; munmap at 16 passes,
434176 bytes and 10525 instructions. Both have zero pending targets and
incomplete blocks. Generation five completed at 24 / 21 passes and 909312 /
544768 cached bytes. These remain within the existing 33-pass / 1-MiB limits.
The two recurrences therefore support ordinary bounded learning, with no
evidence here of lost seeds, incorrect release clipping or capacity refusal.
No source or protocol correction follows from this narrow diagnosis.

## Retirement and remaining limits

Exact retirement reached `state=2, modules=0, frames=0, writers=0`, with
`retirement_passed=true` and `final_idle=true`. The original result retains
`STOPPED_RETIREMENT_PENDING` and no error; the separate finalizer records
successful retirement while leaving `campaign_complete=false` and
`passed=false`. Application/drain success is distinct from performance and
delegation acceptance.

Normal `7.0.0-38-kdlock1` was restored at boot
`f33f1bdf-38dd-49cc-a319-654d5989777b`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`. Idle state and an empty one-shot
boot entry were verified. The bounded live series stops here; no additional
run, runtime change or master merge is included. Separate child images remain
a design item, initially scoped to selected KD acquisitions; allocator and
other Native locks keep their existing instruction-service handling.

Exact generations, local and handback counts, compiler outcomes, histories,
retirement and normal-kernel recovery are retained in `analysis.json`.
Actual CLI/STI hits and physical batch lengths remain unmeasured. Existing
flags, SIMD and IRQ-context limits remain; publication or an entry count does
not prove complete MM execution or general architectural equivalence.

Raw records are retained under
`../../raw/bench/mmap1-generation4-00413a9a/`, with sizes and SHA256 values
in `retained-files.json`. Original VM run files remain intact. Original
campaign outcomes and separate finalizers preserve the distinction between
workload/drain success and performance acceptance.
