# Final mmap1 comparison: candidate remains unaccepted

Both archived arms passed read-only source, identity, raw-log and score replay:
84 points, 42 matched pairs, one round per point. Threads and processes remain
separate. The metric is completed mmap/munmap pairs per nominal second: the sum
of the two post-marker integer samples divided by 2. It is not a joined-wall
rate or individual syscall count.

Threads gained at 16 points and lost at 5; processes gained at 2 and lost at 19.
The strict host comparison passed. The prospective `mmap-functional-v1` policy
does not qualify these data as a strict performance acceptance result:
`performance_qualified=false`, `strict_qualified=false`, and
`performance_accepted=false`. The original candidate strict mapping failure
remains failed; the later ordinary writer observation remains inconclusive.
The artificial held-writer proof is separate. The nano gate also remains failed.

Selected worker counts:

| Model | Workers | f7 pairs/s | 22d pairs/s | Change |
| --- | ---: | ---: | ---: | ---: |
| threads | 20 | 37,599.0 | 88,506.0 | +135.394558% |
| threads | 32 | 23,790.5 | 40,086.0 | +68.495828% |
| threads | 60 | 6,610.5 | 12,458.5 | +88.465320% |
| processes | 20 | 1,869,420.0 | 1,856,219.0 | -0.706155% |
| processes | 32 | 1,796,532.5 | 1,767,165.5 | -1.634649% |
| processes | 60 | 1,415,688.0 | 1,260,001.0 | -10.997268% |

Every observed loss (no threshold or omission):

| Model | Workers | f7 pairs/s | 22d pairs/s | Change |
| --- | ---: | ---: | ---: | ---: |
| threads | 1 | 288,828.5 | 287,028.0 | -0.623380% |
| threads | 2 | 189,394.5 | 105,239.0 | -44.433972% |
| threads | 3 | 158,315.0 | 101,738.0 | -35.736980% |
| threads | 4 | 123,993.5 | 102,623.5 | -17.234774% |
| threads | 5 | 102,748.5 | 97,873.5 | -4.744595% |
| processes | 1 | 352,615.0 | 346,119.5 | -1.842094% |
| processes | 3 | 964,474.0 | 953,212.5 | -1.167631% |
| processes | 4 | 1,273,053.0 | 1,266,723.5 | -0.497191% |
| processes | 5 | 1,574,236.0 | 1,571,149.5 | -0.196063% |
| processes | 6 | 1,868,720.5 | 1,802,611.5 | -3.537661% |
| processes | 7 | 2,062,805.5 | 2,020,518.5 | -2.049975% |
| processes | 8 | 1,929,302.5 | 1,915,904.0 | -0.694474% |
| processes | 12 | 1,910,660.5 | 1,906,226.5 | -0.232066% |
| processes | 16 | 1,910,924.0 | 1,902,698.5 | -0.430446% |
| processes | 20 | 1,869,420.0 | 1,856,219.0 | -0.706155% |
| processes | 28 | 1,826,474.0 | 1,801,743.5 | -1.354002% |
| processes | 32 | 1,796,532.5 | 1,767,165.5 | -1.634649% |
| processes | 36 | 1,583,077.5 | 1,576,372.5 | -0.423542% |
| processes | 40 | 1,457,383.0 | 1,456,759.0 | -0.042816% |
| processes | 44 | 1,388,436.5 | 1,384,311.5 | -0.297097% |
| processes | 48 | 1,338,873.0 | 1,334,523.0 | -0.324900% |
| processes | 52 | 1,303,100.5 | 1,302,024.0 | -0.082611% |
| processes | 56 | 1,279,239.5 | 1,276,630.0 | -0.203988% |
| processes | 60 | 1,415,688.0 | 1,260,001.0 | -10.997268% |

The full 42 rows are retained in [threads.csv](threads.csv),
[processes.csv](processes.csv) and [comparisons.json](comparisons.json).
[observed-losses.json](observed-losses.json) retains all 24 negative rows.
The [full validation](validation.json), [independent raw arithmetic](independent-raw-arithmetic.json)
and [independent final-row review](independent-final-review.json) are separate evidence.

Verified source behavior confines the change to bounded killable phase
admission. An uncontended reservation succeeds on its first probe. Improved
contended thread points are consistent with avoiding some wait transitions;
these measurements do not establish a parking fraction or a causal attribution.
The 19 process losses cannot be attributed to spending the full spin budget
when independent-mm admission succeeds immediately. Their cause remains
unresolved by this single round. No loss is dismissed as noise. There is no
fresh Linux Native parity comparison and no historical rate pooling.

The first replay failed before scoring because its common-source heuristic
mistook `strict-hold/source/README.md` for the harness root README. Its exact
[failed receipt](failed-replay/validation.json) and [old reader](failed-replay/mmap_compare.py)
remain unchanged. The [reviewed correction](tools/README.md) binds only the six
diagnostic leaves to the exact diagnostic manifest and Git commit before common
source matching. Other source checks and scoring are unchanged. Corrected replay
was offline only; it repeated no VM work or measurement.
