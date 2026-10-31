# The fresh 60-process result

The recovery candidate scored 1,274,306 mmap/munmap pairs per nominal second,
versus 1,436,012.5 for the promoted provider: **-11.260800%**. Both complete
points remain in the comparison. The original application and its arguments
were unchanged, and each point ran once.

| Arm / post-marker sample | Minimum worker count | Maximum worker count | Total |
| --- | ---: | ---: | ---: |
| Promoted / 1 | 18,650 | 314,879 | 1,435,940 |
| Promoted / 2 | 18,483 | 313,054 | 1,436,085 |
| Recovery / 1 | 20,846 | 22,129 | 1,276,451 |
| Recovery / 2 | 20,845 | 21,665 | 1,272,161 |

The promoted arm's largest worker contributed approximately 21.9% and 21.8%
of the sample totals. Recovery was nearly uniform. The average of the remaining
59 counts, obtained by subtracting each sample's maximum, was about 19.0k for
promoted and 21.2k for recovery. This calculation describes the distribution;
it does not replace or adjust the full aggregate score. The output does not
identify the maximum's worker or establish that it was the same worker in both
samples.

Summed user/system CPU time divided by 60 times whole application lifetime
was 98.51% for promoted and 98.36% for recovery. These lifetime totals include
warmup and reaped workers, whereas the score uses two post-marker samples.
They do not support a large aggregate increase in off-CPU time, but cannot
exclude individual scheduling events, spinning costs or cache effects. No timed
scheduling-event trace or per-worker sample vector was collected.

The [earlier investigation](../../mm-investigation.md) recorded a similarly
skewed historical f7a84065 run and nearly uniform historical 1b6f256b run.
The current promoted 1b6f256b run itself is skewed, so this distribution is not
unique to f7a84065. These are separate cohorts; their throughput values are not
pooled, and no cross-cohort recovery ratio is calculated.

Current-source inference remains that forked workers have distinct mm objects
and mmap gates in steady state. Shared commitment accounting is a candidate
for attribution, not an observed hotspot. Restoring reader entry has not fixed
the 60-process problem. Further source changes require evidence about where
the workers spend their CPU time and why one worker dominates a sample.

The [original point records](promoted-point.json), [recovery record](recovery-point.json)
and [derived inspection](inspection.json) retain the input values and source-result
hashes. Original upstream logs remain in both verified raw archives.
