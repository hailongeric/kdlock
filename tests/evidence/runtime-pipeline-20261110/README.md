# Focused runtime-pipeline checks, 2026-11-10

All 12 cases in `tests/test_runtime_pipeline.py` passed in the designated VM on
committed source `c6becf81987ae29a97000a641d76a0ff2e300860`. The command returned
0 with no skips. This is focused compiler, transport-format, archive and GNU
image-construction evidence. It is not kernel-core compilation, loaded-image
publication/ACK, generated machine-code execution, ordinary kernel mutex
execution, performance evidence or execution of acceptance cases T01–T56.

## Source and environment

- Source archive SHA256:
  `5be656f42ea85526e44d292b6929dcd6ee826e395e36dd5b91a50e25750b3a52`.
- The Git archive contained 99 files. Every file matched the retained manifest
  before and after the run; no extra source files appeared. The archive excludes
  the separately recorded worktree changes and untracked kernel fixture.
- Frozen input:
  `/mnt/kdlock-builds/kdlock-main-work/run-c6becf81-01a1bc4f/input`.
- Guest: `root@10.176.26.71:2222`, kernel `7.0.0-38-kdlock1`, x86_64.
- Boot ID before and after:
  `3d32656f-6162-4a0a-9304-bf383d34298d`; taint before and after: `0`.
- Python: `3.14.4`, through
  `/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python`.
- Explicit configuration SHA256:
  `7d9a87957e0ec4e9b06b63fcd5dafb331dfe0324149905392d65a130ffe8d72a`.
  The previous run configuration was copied with only its run-directory prefix
  changed. Finite compiler, ledger, wire, archive, tool, size and time bounds
  are retained in `pipeline-config.json`; they are test inputs, not defaults.
- GNU tool paths are explicit in that configuration. Tool version banners and
  installed package versions were not separately captured by this run.

The raw command receipt records start time `1794321256.7714372` Unix seconds
(14:34:16.771 UTC). The result was written at 14:34:17.549 UTC. The runner elapsed
0.7748 seconds; unittest reported 12 tests in 0.145 seconds. The before/after
activity checks found no competing build/test/trim process and no remaining test
process. A later independent process check also found the focused run idle.

## Exact invocation

From the frozen input directory, the runner used:

```sh
KDLOCK_PIPELINE_TEST_CONFIG=/mnt/kdlock-builds/kdlock-main-work/run-c6becf81-01a1bc4f/receipts/pipeline-config.json \
PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python \
-m unittest discover -s tests -p test_runtime_pipeline.py -v
```

The remote runner imposed a 180-second subprocess bound and saved combined
stdout/stderr. The test module requires its explicit JSON configuration and
translation dependencies; absence or skips are not treated as passes. Each test
scratch directory remains under the run's `scratch/` directory.

The cases exercise an indirect source miss merged before real compilation and
emission, consumed RET/API nonobservations, pre-operation cuts, exact missing
source/resource outcomes, late/foreign records, finite malformed wire input,
SOURCE8's actual slot/nullable-base export, typed flat metadata, actual durable
archive bytes/O_EXCL refusal and preservation of pending facts. The GNU case
actually invoked configured cpp/as/ld/objcopy on the original backend output and
checked linked/extracted bytes at the explicit reserved base; it did not execute
those machine bytes or manufacture publication/ACK evidence.

## Retained receipts

- `focused-command.json`: exact argv, environment overrides, source archive
  identity, pre-run boot/kernel/taint/modules and activity.
- `focused-result.json`: return code, elapsed time, post-run identity/activity,
  all 99 file rechecks and raw-log hash.
- `focused-unittest.log`: unedited combined test log, SHA256
  `2b207a2867c94ca9d61867bd7b46057e8c32cd08570e00a0dbd6b30573155752`.
- `pipeline-config.json`, `preparation.json`, `python-version.txt` and
  `return-code.txt`: actual finite inputs and preparation/result scalars.
- `source-state.json` and `source-manifest.json`: exact committed archive
  identity, captured worktree status and file hashes. `transfer_bytes` is the
  summed source-file content size; the tar itself is 1,198,080 bytes.

The same raw receipts and retained per-case artifacts remain in the VM at
`/mnt/kdlock-builds/kdlock-main-work/run-c6becf81-01a1bc4f/`. The source archive
is retained there as `kdlock-main-c6becf81.tar`; it is not duplicated here.
