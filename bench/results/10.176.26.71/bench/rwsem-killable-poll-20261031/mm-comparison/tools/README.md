# Explicit source domains for the prospective MM archive replay

The first read-only replay remains failed at
`/dev/shm/kdlock-killable-functional-mm-comparison-20261031/validation.json`, SHA
`4f9c469ee972e102ee3ec1cf41a4cd9bf6682ab280debf5161627a99a81bfe78`.
Its generic `/source/` heuristic interpreted `strict-hold/source/README.md` as
the common harness root `README.md`. These are distinct source domains:

- The actual diagnostic README is
  `803cadd227b01b5c8eb2a87895cc5da135306f1ba0eb7f0e975c891d5f462653`,
  from diagnostic commit `3b34414a259d6061a4b566ac33579f9547df080e`.
- The unchanged f4ae common README is
  `470094c10ad03cb9dcff20419712f28d86b42d1a729c98db2c7d6f80e991646c`.

This new reader first validates the exact six diagnostic-manifest source leaves
against the pinned manifest, reviewed diagnostic Git commit and archived bytes.
Only those six exact members use the diagnostic source domain. Every other
common source snapshot retains the original generic exact comparison. The
existing full strict diagnostic source/classifier/policy checks also remain.
There is no blanket exclusion for a directory or extension, no modified source
receipt, no relaxed common harness hash and no score-parser change.

Old tools, failed output and actual input bytes stay unchanged. The input SHA is
`249f173be35bcd1335b4f12ca64f237aefa1e0f900811272239fed788dbef359`.
After independent source review, use a new output path for one read-only replay:

```sh
python3 /tmp/kdlock-killable-functional-offline-r2-20261031/mmap_compare.py \
  --inputs /dev/shm/kdlock-killable-functional-mm-comparison-inputs-20261031.json \
  --inputs-sha256 249f173be35bcd1335b4f12ca64f237aefa1e0f900811272239fed788dbef359 \
  --trusted-checkout /home/eric/vm/vm-shared/kdlock \
  --cache-root /dev/shm \
  --output /dev/shm/kdlock-killable-functional-mm-comparison-r2-20261031
```

No VM, workload, build, test, network or archived source execution is involved.
All losses, both process models and the explicit prospective policy are retained.
Nano's failed gate and performance qualification/acceptance remain false.
