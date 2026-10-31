# Archive the candidate with its separate diagnostic provenance

The completed baseline archive remains unchanged. This candidate-only revision preserves the entire candidate arm, selects nine successful logical owners explicitly, and groups all other attempts separately. The original sites/API owners stay failed; a later success uses a different directory. The producer's maintained grouping, endpoint replay, idle checks, and one-round measurement settings are unchanged.

Reviewed source:

- `/tmp/kdlock-writer-queue-mm-archive-diagnostic-r2-20261031.py`: `fd52c123f07d1c9de1996dd2fc8540b8cb8794e2cfe9b22937b6af1a444bd7b0`.
- `/tmp/kdlock-writer-queue-diagnostic-provenance-r2-20261031.py`: `a30f16ccb4036ff5acc186c029359456bcbcbedce8c89a7820cf931bf8cc4bfb`.
- Completed source-host provenance record `/tmp/kdlock-writer-queue-diagnostic-provenance-r2-20261031.json`: `2196af5157c900d9faf9ea61b7d51d3f6852d9c3cba6351654d593d88a5ad364`.

The record was built once by reading exact JSON and Git blobs. It verifies all 5,847 baseline, 5,848 intermediate and 5,850 final tracked paths and the strict diagnostic's two six-file manifests. Its ten tracked diagnostic changes and three strict diagnostic changes are enumerated. This is source correspondence, not another correctness run.

After timing and its immediate endpoint complete, restore the four exact inputs in `/tmp/kdlock-writer-queue-mm-diagnostic-r2-20261031.uploads.json` using the existing reviewed missing-or-identical uploader. Existing guest receipt/configuration references in the provenance record must remain at their original paths. Do not reconstruct or relabel a receipt.

Use the previous schema-1 archive bindings with final config `fafaac5315038e45f150feb4d24a45913a848dfaed8e8c51236952d5087c8584`, actual candidate boot and bundle, and actual nine owners. Add:

```json
"diagnostic_provenance": {
  "path": "/tmp/kdlock-writer-queue-diagnostic-provenance-r2-20261031.json",
  "sha256": "2196af5157c900d9faf9ea61b7d51d3f6852d9c3cba6351654d593d88a5ad364"
}
```

Invoke exactly one action through the existing guest-step transport, with its usual `completed` success key and bounded archive timeout:

```sh
PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 \
  /tmp/kdlock-writer-queue-mm-archive-diagnostic-r2-20261031.py \
  --bindings ACTUAL_BINDINGS_PATH --bindings-sha256 ACTUAL_BINDINGS_SHA256
```

The archive output paths are the original candidate-archives/candidate-archive-control locations, which must still be absent. This revision has not executed. It preserves the provenance record and every referenced input, including the original compatibility raw inputs and failed API retirement-bound files. It does not modify production source, select a new workload, rerun baseline points, or grant performance acceptance.

The matching new fetch revision takes the five actual completed control hashes plus this provenance hash. Its resulting candidate descriptor and the original baseline descriptor feed `/tmp/kdlock-writer-queue-mm-offline-diagnostic-r2-20261031/`; use a new comparison output directory. Do not run paired analysis until both actual archives are available.
