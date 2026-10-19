# Fresh mutex count and phase comparison

Root orchestration owns VM execution. This report collects fresh `embedded32`
(the shared phase/count baseline), `old256`, then `candidate` source blocks.
The arm names displayed by summary tools are labels, not chronological order;
actual command start/finish receipts establish collection order. Prior report
directories and their evidence remain unchanged.

Each block runs six plain pipebytes/query timings: 8 and 60 workers, three
repetitions, 2000 ms measurement, 48000 operations/1000 ms minimum warmup,
workers 0 through N−1 and collector CPU63. Two separate profiles follow the
plain runs, one per worker count. No synthetic or other API workload is part
of this round. Configured helper waves remain unused by pipe. Do not pool
source versions, worker counts, instrumentation settings or earlier rounds.

## Collection commands

`RUN` denotes the new external guest path
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-packed-20261019`. From the idle
maintained guest checkout, with the pinned environment and verified recovery
snapshot, run the reviewed copied drivers:

```sh
python3 "$RUN/run-matrix.py" --version embedded32 --commit cb0e8e6 --base "$RUN"
python3 "$RUN/run-matrix.py" --version old256 --commit OLD_REV --base "$RUN"
python3 "$RUN/run-checks.py" --commit 35718f5 --output "$RUN/checks-candidate-r2"
python3 "$RUN/run-matrix.py" --version candidate --commit CANDIDATE_REV --base "$RUN"
```

Each source transition requires verified idle state and reviewed synchronization
before its command. `run-matrix.py` and the same copied `mutex_profile.py` must
remain unchanged across all arms. The matrix command has a 900-second bound
per plain/profile subprocess. A timeout does not establish drain, and existing
outputs must be preserved rather than retried in place.

Candidate checks select two basic tests plus thirteen affected drivers,
including `test_mutex_state.py` and the new `test_mutex_count.py`, followed by
ordinary mutex local, rwsem and instruction-exit live probes. Snapshots include
private `.inc` inputs, including the candidate's `mutex/count.inc`. The local
probe provides public 32-byte size and 8-byte alignment evidence. Removed or
candidate-only production files must not survive a switch to an older source;
review their exact bytes before any path-specific unlink. The copied obsolete
cleanup helper contains only already reviewed historical hashes, so it is not
authorization to remove an arbitrary new candidate file.

The initial `checks-candidate` attempt at `c2f0d9c` is a retained failure:
the provider build passed, but the unit result was 14/15 because the affected
shadow-stack fixture lacked the `u64` typedef. This was a fixture compile
failure, not a pass or skip. Test-only fix `35718f5` leaves production bytes
unchanged and is checked in the new `checks-candidate-r2` directory; the
candidate benchmark also records `35718f5`. Finalization uses the second
attempt, and preservation/audit includes both attempts with their exact source
revisions. The initial attempt never reached its live probes.

## Profiling method and useful limits

The profile driver attaches perf to the idle API client before measured workers
are created, inherits those threads, and requires FIFO enable/disable/stop
acknowledgements. It records flat `cycles:k` samples at **199 Hz**, without
unwinding or additional PMU events. Recording, report and script operations use
the exact retained `ARM/profile/tools/perf` binary. Symbol resolution completes
while modules remain loaded. Every diagnostic is unscored and requires actual
returned JIT, retained source/binary evidence and successful drain.

The bounded per-arm invocation is already the matrix's second command:

```sh
python3 "$RUN/mutex_profile.py" --source-root /root/host_fs/kdlock \
  --commit ARM_REV --output "$RUN/ARM/profile"
```

Do not rerun that command into an existing directory. Profile analysis keeps
all client-kernel and exact `sc_worker` period denominators separate, reports
lost/unparsed/zero-sample cases, and compares each profile's measured returned
JIT fraction with its own validated three-repeat plain cohort. Past pipe8
profiles changed admission markedly; a completed profile alone does not prove
that it represents uninstrumented contention.

Gate/count operations are frequently inlined. The report therefore includes
enclosing entry/slowpath, claim/release and combiner scopes and weighted sampled
offsets. A missing standalone helper is not evidence of zero cost. Notification
polling can dominate worker periods; a sample immediately after a locked
instruction can reflect skid. These profiles do **not** count gate-CAS retries,
locked operations, cache-line transfers or cycles charged to a single RMW.
Read-only ELF/offset inspection on the source host can identify nearby code but
cannot remove those limitations.

The cleanest measurement of the proposed change is the fresh plain throughput
comparison, measured returned-JIT fractions and independently bounded whole-
session accounting. Generic perf-stat counts could supply aggregate kernel
cycles/instructions in another diagnostic run, but still include waiting and
do not isolate sharing. Model-specific locked/HITM or precise memory events
must first be demonstrated to work in this actual guest PMU. This tooling does
not silently request unsupported events or count `<not supported>` as evidence.
Exact retry counters would require a separate instrumented source variant and
its own comparisons; they are not part of the current timing arms.

## Finalization and offline review

Retain host before/after policy captures and guest boot evidence. Once all arms
and candidate checks are complete and idle, copy final reviewed analysis
helpers to `RUN`, preserving the already used matrix/profile driver bytes:

```sh
python3 "$RUN/run-finalize.py" > /tmp/mutex32-packed-finalize.log 2>&1
python3 bench/archive_run.py --base "$RUN" --output "${RUN}-archives" \
  --health "$RUN/health.json" --group embedded32=embedded32 \
  --group old256=old256 --group candidate=candidate --group checks=checks-candidate-r2 \
  --group failed_checks=checks-candidate \
  > /tmp/mutex32-packed-archive.log 2>&1
python3 "$RUN/export-compact.py" --base "$RUN" --archives "${RUN}-archives" \
  --output "${RUN}-compact" > /tmp/mutex32-packed-export.log 2>&1
```

Add any separately retained failed/preliminary build/check directories as
explicit archive groups. Finalization validates 18 plain and six diagnostic
sessions, exact command scope, source identities, profile loss/parse results,
retained perf bytes, kernel logs and final idle state. Stdout must remain
outside the evidence tree so it does not violate the archiver's writable-FD
guard. All remaining top-level inputs become archive metadata.

After transfer, source-host audits read tar members and Git objects as inert
data. They never execute archived Python, binaries or modules:

```sh
python3 "$REPORT/offline-archive-review.py" --repo "$REPO" --raw "$RAW" --report "$REPORT" \
  --expect embedded32=cb0e8e6 --expect candidate=35718f5 --expect old256=OLD_REV \
  --extra-source checks-candidate=c2f0d9c
python3 "$REPORT/offline-statistics-review.py" --raw "$RAW" --report "$REPORT" \
  --arms embedded32 candidate old256
```

Declare exact reviewed runner-only overlays with `--allow-ancillary` if needed;
production differences have no exception. The arithmetic audit reconstructs
all 24 whole/peak windows, plain cohort statistics, measured API fractions,
whole-session diagnostics and period-weighted profile totals/offsets. Missing
suppressed CPU ratio rows remain unknown. `offline-offset-review.py` separately
binds a copied ELF and flat samples to an instruction-offset receipt; such
static receipts are postprocessing, not extra runtime measurements.
