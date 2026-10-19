# Fresh embedded-state pipe comparison

These drivers collect two separate source blocks, `embedded32` and `old256`.
Each block runs pipebytes/query with 8 and 60 workers, three repetitions per
point, a 2000 ms measured interval, and collector CPU 63. Workers use CPUs
0 through N−1. Warmup and admission options match the previous plain pipe
comparison. The configured helper waves are unused by the pipe runner. There
are no profiles or synthetic workloads in this round. Prior-round rates are
not pooled with these measurements.

All collection, builds, tests and finalization run in the recovery VM. The
source host may inspect source and run the two inert offline audits after
archives arrive. Root orchestration owns every VM operation. Existing failed
or partial output directories must remain intact; a retry needs a new name and
an explicit mapping in finalization/audit commands.

The actual snapshot, 64 vCPU pins, host policy and guest boot are captured in
`host-before.json` and `guest-before.log`. `run-build.py` is the separately
retained initial frozen production build; its `build-initial` directory must
be included in the archive even if a stage fails. It is not the focused check
receipt and does not substitute for `run-checks.py`.

## VM collection

Use the pinned translation environment and the already verified recovery
snapshot. Substitute the committed source revision for `EMBEDDED_REV` and
the frozen original 256-byte revision for `OLD_REV`. Run from the maintained
guest checkout, `/root/host_fs/kdlock`. `RUN` below denotes
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-embedded-20261019`.

```sh
python3 "$RUN/remove-obsolete.py" --target embedded32 --receipt "$RUN/remove-aux-before-checks.json"
python3 "$RUN/run-checks.py" --commit EMBEDDED_REV --output "$RUN/checks-embedded32"
python3 "$RUN/run-matrix.py" --version embedded32 --commit EMBEDDED_REV --base "$RUN"
```

The focused check snapshot contains private `.inc` files, the embedded-state
fixture and all directly consumed probe/runner inputs. It selects two basic
tests plus twelve affected drivers, then runs the ordinary mutex local probe,
rwsem probe and instruction-exit probe. The local probe supplies live 32-byte
size and 8-byte alignment evidence, physical-ring cancellation/handoff checks,
and address reuse without caller destruction. Unit mutation outcomes are
parsed from the actual frozen dictionaries rather than a guessed count.

After verified drain, synchronize the reviewed original source. This repository's
synchronizer does not delete obsolete paths. The helper permits unlinking only
explicit reviewed paths with exact captured hashes, rejects symlinks and checks
idle before and after. Update its expected state-header hash only after static
review if that header changed before the transition.

```sh
python3 "$RUN/remove-obsolete.py" --target old256 --receipt "$RUN/remove-state-before-old256.json"
python3 "$RUN/run-matrix.py" --version old256 --commit OLD_REV --base "$RUN"
```

Restore the checked embedded source while idle. Do not edit frozen collection
inputs. Record any required runner-only overlays explicitly for the later
source audit; production inputs have no exception mechanism.

## Finalization and preservation

At the idle boundary, capture the benchmark host using `capture-host.py`
(sudo may be needed to read the monitor socket). This helper sends only
`info snapshots` and disconnects. It is an exact source copy of the earlier
screen-round helper used for `host-before.json`; redirect its JSON stdout to
a new `host-after.json`. Finalization compares the two QEMU identities and
frequency/NUMA policies. Copy the new capture into the guest evidence tree.
Copy the reviewed report helpers
into `RUN` before finalization, then leave them unchanged through archiving.

```sh
python3 "$RUN/run-finalize.py" > /tmp/mutex32-embedded-finalize.log 2>&1
python3 bench/archive_run.py --base "$RUN" --output "${RUN}-archives" \
  --health "$RUN/health.json" \
  --group embedded32=embedded32 --group old256=old256 \
  --group checks=checks-embedded32 --group initial=build-initial \
  > /tmp/mutex32-embedded-archive.log 2>&1
```

Finalization and archive stdout must be outside the evidence tree because
the strict idle predicate rejects writable descriptors into that tree.
`run-finalize.py` retains actual analysis exit statuses. It refuses to replace
an earlier final-analysis command receipt; preserve a failed attempt before a
new attempt. All remaining top-level files, including cleanup and source-sync
receipts, are retained in the archiver's metadata group. Include additional
failed build/check directories as separately named groups if any exist.

`comparison.json` keeps measured API body entries and matching returned JIT
counts separate. Its whole-session counters include warmup and checks and
are never used as measured-phase fallback fractions. A complete timing group
needs all three repeats with the same source, identity and execution class;
cross-arm policy/instrumentation identity must also match. Missing or invalid
rows stay explicit, and a NORMAL image is not accepted as returned JIT proof.

## Offline review after transfer

Preserve the archive files, `archives.json` and `input-inventory.json` together
under the new raw report directory. Copy compact metadata and command receipts
into this report directory. On the source host, substitute the two concrete
revisions and the revision matching the initial frozen build:

```sh
python3 "$REPORT/offline-archive-review.py" --repo "$REPO" --raw "$RAW" --report "$REPORT" \
  --expect embedded32=EMBEDDED_REV --expect old256=OLD_REV \
  --extra-source build-initial=INITIAL_BUILD_REV
python3 "$REPORT/offline-statistics-review.py" --raw "$RAW" --report "$REPORT" \
  --arms embedded32 old256
```

The archive audit reads tar members and Git objects without extraction or
execution. It validates inventory, source, binary, JIT and receipt bindings,
including live embedded layout evidence. If a reviewed runner-only overlay
was necessary, name its exact path with `--allow-ancillary`; the audit reports
every exception and forbids production exceptions. The arithmetic audit
independently reconstructs every whole/peak window, group median/range,
measured returned-JIT fraction and whole-session pipe accounting. Suppressed
per-CPU ratio rows remain unknown, with partial observed sums kept separate.
Neither audit imports or executes archived Python or binaries.

No performance conclusions are recorded here before completed fresh evidence
and independent archive/arithmetic review.
