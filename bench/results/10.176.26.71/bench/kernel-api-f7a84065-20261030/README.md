# Original-body syscall comparison: f7

All 126 measured sessions and 63 Native/KD pairs passed the offline identity,
completion and retirement checks. KD was faster at 40 points and slower at 23;
there were no missing, invalid or unqualified points. **Performance acceptance
remains false.** The outstanding nano losses and final unchanged `mmap1`
comparison remain separate gates.

| Workload | KD gains / losses | Lowest KD/Native | Highest KD/Native |
| --- | ---: | ---: | ---: |
| `setfd`: F_SETFD + F_GETFD | 18 / 3 | 0.9683× at 3 workers (−3.171%) | 2.5526× at 56 (+155.264%) |
| `pipebytes`: FIONREAD, 16 filled pages | 7 / 14 | 0.5471× at 5 (−45.293%) | 1.4356× at 4 (+43.563%) |
| `pipecap`: F_GETPIPE_SZ, 16-page pipe | 15 / 6 | 0.7545× at 6 (−24.550%) | 1.9586× at 60 (+95.862%) |

At 20 workers:

| Workload | Native Mops/s | KD Mops/s | KD/Native | Change |
| --- | ---: | ---: | ---: | ---: |
| F_SETFD + F_GETFD | 3.388391 | 5.185315 | 1.5303× | +53.032% |
| FIONREAD | 3.292182 | 2.302197 | 0.6993× | −30.071% |
| F_GETPIPE_SZ | 3.575341 | 4.198061 | 1.1742× | +17.417% |

Every negative point is retained. The loss counts are workers 1, 2, 3 for
`setfd`; 1, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44 for `pipebytes`;
and 1, 2, 3, 5, 6, 7 for `pipecap`. The complete
[126-point table](analysis/points.csv), [63-pair table](analysis/pairs.csv),
[ratios](analysis/ratios.csv) and [summary](analysis/summary.json) preserve the
unrounded values and validation status. [The generated table](analysis/README.md)
lists all 63 comparisons. CSV bytes are copied unchanged.

## Scope and identity

| Input | Exact identity |
| --- | --- |
| KD source/provider generation | `f7a84065e84474380faa37eeadfdf534abd72a68` |
| Kernel integration recipe | `8446f4ecb08816380a4c233197a8ce5e4d333aac` |
| Running kernel | `7.0.0-38-kdscope1` |
| Kernel Build ID | `a17d565ee157601e030d1b3c77c13e63fa62c994` |
| Native-A boot | `2e0ea0fa-ff34-4416-9175-b4b0ede3f63b` |
| API controller SHA-256 | `35495b774fd74872cd204140ef76fe4cdcc34b2235cbac051d05999c9101bf6c` |
| Measured result SHA-256 | `0a8ca4188be7d9d32f96b8e43c0f9935e0a037e94636eade062adb62618da488` |

Both arms use this same enabled-API kernel in `kd_mmap=off` mode, with
`preempt=lazy`, `nokaslr` and `nopvspin`. The kernel recipe and provider generation
are different inputs, authenticated separately. The [installation record](../../tests/kernel-scope-install-20261030/README.md)
retains the build and linked API-site evidence; the [generation record](provenance/generation-record.json)
binds the later provider to the frozen kernel interface. The provider, syscall
client, daemon and guard binaries prepared for the functional phase were reused
unchanged for all timed points. The offline analyzer checked their archived
hashes, complete source bindings, kernel bundle, entry bindings and exact argv.

The test invokes actual userspace syscalls on bound kernel objects. Kernel
changes are confined to lock calls and required binding/routing/lifetime glue;
the selected Native bodies remain in place. Every participant on a bound object
uses its selected protocol. `setfd` exercises `files_struct.file_lock`; both pipe
cases exercise `pipe_inode_info.mutex`. This is a scoped object conversion, not
arbitrary whole-kernel replacement. The [source audit](../../../../../docs/design/kernel_cs_semantics.md)
and linked installation evidence delimit those claims. No extracted-body or
TCLock result is substituted.

The grid uses workers 1–8 and 12–60 in steps of four, CPUs `0..N-1`, collector
CPU 63, Native then KD at each coordinate, and one measured round (`r00`) of
2,000 ms. Throughput is completed operations divided by actual joined wall time,
not a peak interval. One `setfd` operation includes F_SETFD and its F_GETFD oracle;
each pipe operation is one syscall. Setup, translation and warmup are unscored.
Timed body-completion, JIT timing and hotlock observations are disabled. There is
no confidence interval, repetition selection or pooling with another source,
boot, workload, topology, call shell or instrumentation setting.

## Functional execution and endpoint evidence

The separate [four-family basic result](receipts/basic-result.json) and
[four object-semantic sessions](receipts/objects-result.json) passed. The object
checks include participants outside the proxied subset. Publication in those
semantic tests is not counted as returned-body proof.

The [six-session functional result](receipts/functional-result.json), at 16
workers, observed matching KD JIT entries and returns:

| Workload | KD entries | KD returns | Native entries / returns |
| --- | ---: | ---: | ---: |
| `setfd` | 4,890,200 | 4,890,200 | 0 / 0 |
| `pipebytes` | 2,168,993 | 2,168,993 | 0 / 0 |
| `pipecap` | 3,893,743 | 3,893,743 | 0 / 0 |

All six retired with `state=2, modules=0, frames=0, writers=0`. Timed sessions
do not observe JIT completion; their successful image publication is not used
to claim returned JIT bodies or a delegated fraction. These checks do not
validate arbitrary Native CALL reentry or unsupported lock/context cases.

The separate [endpoint receipt](receipts/endpoint-receipt.json) passed strict
host task identity: the same 131 QEMU tasks, no added or retired worker, and the
fixed 2 GHz policy. It binds the completed measure owner and exact captured
policy/reference hashes. This is endpoint identity evidence, not proof of
uninterrupted isolation. Its nested generic `host_endpoint=PENDING` field is
preserved unchanged; the enclosing receipt records endpoint completion. The
offline numerical summary deliberately leaves endpoint assessment separate.
[Final health](receipts/final-health.json) records actual idle and the four
phase owner/result bindings. Neither receipt changes performance acceptance.

## Interpretation and remaining work

The strong contended `setfd` results coexist with small low-count losses.
F_GETPIPE_SZ also improves at larger counts but loses at six low-count points.
FIONREAD remains the clearest gap: it loses at every measured count from 5
through 44, then records small positive differences at 48–60.

The audited FIONREAD body sums ring-buffer lengths, whereas F_GETPIPE_SZ loads
capacity and shifts it. Additional translated loop work is therefore a plausible
contributor to their different behavior. This is a source-backed hypothesis,
not a measured attribution: the scored run does not measure parks, executed JIT
fractions, combiner cycles, cache traffic or physical page placement. It cannot
establish those as causes. FIONREAD's user copy remains after unlock; none of
these three selected protected bodies requires general CALL-return reentry.

The user authorized subsequent localized-MM and unchanged `mmap1` comparisons
on this isolated candidate despite the nano losses. Those results are pending
in this record. This API campaign does not close the nano no-regression gate,
the remaining API losses, generic branch-only Native continuation, or final
application acceptance.

## Preservation and reproduction

The [initial preservation owner](receipts/preservation-failed.json) records a
source-host space refusal after successful endpoint capture and guest archiving.
Its fixed 1 GiB reserve did not fit. The separately reviewed
[fetch-only continuation](receipts/fetch-only-complete.json) retained the failure,
used the exact archive/cache allocation budget plus 256 MiB headroom, and
completed. No measurement, endpoint or guest archive was repeated. The
[transfer receipt](receipts/transfer.json) binds the original archive bytes.
The [offline analysis run](receipts/analysis-run.json) completed on its first
attempt without modifying raw inputs.

The raw source-host archive is
`bench/results/10.176.26.71/raw/tests/kdscope1-api-f7a84065-20261030/`.
It retains the five grouped archives (40,616,996 compressed bytes), full input
inventory, source/binaries, every session/log and transport bytes. The archived
guest campaign is
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kdscope1-api-f7a84065-20261030`.
[The archive index](provenance/archives.json), [archive owner](receipts/archive-owner.json)
and [provenance](provenance/archive-provenance.json) bind that external evidence.
Large session caches, full derived point JSON and raw binaries are not duplicated
in this Git record. [The copy manifest](copy-manifest.json) records every selected
file's exact origin and SHA-256; [analysis inputs](analysis/read-files-sha256.json)
retain the validator's complete read bindings.

To reproduce offline into a new output directory on 380G10, use the retained
[analyzer](tools/analyze.py), [owner hashes](provenance/owner-hashes.json) and
the unchanged [archive reader](../continuation-perf-nano-20261030/tools/nano_core.py):

```sh
python3 tools/analyze.py \
  --archives /home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/kdscope1-api-f7a84065-20261030/kdscope1-api-f7a84065-20261030-archives \
  --archive-helper ../continuation-perf-nano-20261030/tools/nano_core.py \
  --owner-hashes provenance/owner-hashes.json \
  --output /tmp/kdlock-api-f7-offline-new-output
```

Run from this report directory. This reads and authenticates the retained
archives; it starts no guest work. Endpoint evidence remains a separate receipt.
