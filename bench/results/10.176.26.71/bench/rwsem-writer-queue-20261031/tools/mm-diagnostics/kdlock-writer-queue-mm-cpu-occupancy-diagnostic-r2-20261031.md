# Whole-lifetime mmap1 CPU accounting with separate diagnostic generations

Create a new copy of the reviewed CPU reader. Preserve the original reader and
all comparison outputs. This revision only admits the explicitly separated
baseline, compatibility replay and candidate diagnostic identities produced by
the reviewed diagnostic-r2 comparator. It retains the original 84 point reads,
42 paired rows, arithmetic, model separation and raw fields unchanged.

The baseline harness is `7814c61a0be20f5db3b9fb41b6079ef6d2938b5f`, the replay
harness is `9d10ae77290873df23804293f364862a2b55f385`, and the candidate diagnostic
harness is `de5e4f06a6d60e531a8b329d3c7f2c5335d5e707`. The validated comparison must
bind the exact baseline and candidate configurations and the completed diagnostic
provenance record `2196af5157c900d9faf9ea61b7d51d3f6852d9c3cba6351654d593d88a5ad364`.
This does not reinterpret a failed diagnostic attempt or repeat baseline timing.

For every original point, retain `process_elapsed_ns`, `user_cpu_seconds`,
`system_cpu_seconds`, `workers` and `cpu_time_scope`. Compute aggregate CPU
equivalents as `(user + system) / (process_elapsed_ns / 1e9)` and divide by
configured workers for occupancy. The interval includes six upstream warmups,
the collector process, startup/shutdown and accounted reaped workers. It differs
from the two-second scored interval. Values remain unclamped. These records do
not count parking, spinning or OSQ operations and cannot establish their causal
contribution to performance.

After the paired comparison passes, execute only on 380G10:

```sh
python3 /tmp/kdlock-writer-queue-mm-cpu-occupancy-diagnostic-r2-20261031.py \
  --comparison /dev/shm/ACTUAL-MM-COMPARISON \
  --validation-sha256 ACTUAL_VALIDATION_SHA256 \
  --points-sha256 ACTUAL_POINTS_SHA256 \
  --inputs /dev/shm/ACTUAL-MM-INPUTS.json \
  --inputs-sha256 ACTUAL_INPUTS_SHA256 \
  --output /dev/shm/writer-queue-mm-cpu-occupancy-diagnostic-r2-20261031
```

Use the actual finalized hashes and a new output directory. Original archive
indices, compressed groups and all selected point receipts remain verified by
the unchanged reader. No VM action, measurement, score change or acceptance is
part of this diagnostic. Preparation is source-only; execution is pending.

Independent source/schema review passed at script SHA
`4c9f786639d2a08ca105cf139a6f2d1c08d8a10eea2cf8c5fdc58757f5502907`.
All helper functions and the entire data-reading, arithmetic and output block
are AST-identical to the original reader. The change is limited to generation
admission and receipt provenance. No diagnostic execution was performed during
preparation or review.
