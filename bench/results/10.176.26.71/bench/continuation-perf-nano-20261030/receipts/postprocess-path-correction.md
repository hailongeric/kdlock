# Postprocessing watcher revision 2: actual local receipt prefix

Root found that revision 1 used `/tmp/continuation-perf-nano-f7a84065-20261030`
for local receipt names, while the archive watcher publishes them with the
`/tmp/kdlock-continuation-perf-nano-f7a84065-20261030` prefix. Revision 1 therefore
waited for a nonexistent owner; root reports that no fetch or audit started.

This note precedes creation of a new revision-2 script. Change only `PREFIX` to
`Path('/tmp')/('kdlock-'+NAME)` and its own `EVIDENCE` directory to
`/tmp/kdlock-nano-f7a84065-postprocess-r2-20261030`. All completion/drain gates,
five-hash bindings, prepared-tool hashes, timeout/child retention behavior and
raw/comparison output paths remain unchanged. Revision 1 and its receipt are
preserved; only root may stop that watcher after exact PID verification.

Prepared launch command, for root to run separately after review:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 /tmp/kdlock-nano-f7a84065-postprocess-watch-r2-20261030.py
```

Preparation is source-host only. No watcher launch, controller import, fetch,
audit, guest read, test or build is performed here.
