# Final candidate MM archive fetch

This candidate-only copy retains the existing five-pin read-only transport and
host archive verification. It binds archive producer `fd52c123`, candidate
configuration `fafaac53`, harness `de5e4f06`, and the completed diagnostic
provenance record `2196af51` checked by helper `a30f16cc`. The original baseline
fetch, descriptor and 42 scored points remain unchanged. The intermediate sites
revision, original failed sites/API attempts, normal API retirement, original
focused checks and baseline replay retain their actual identities.

Run only after the candidate archive is complete and its five hashes are known:

```
python3 /tmp/kdlock-writer-queue-mm-fetch-diagnostic-r2-20261031.py \
  --arm candidate --boot-id ACTUAL_CANDIDATE_BOOT \
  --destination /dev/shm/kdlock-writer-queue-mm-candidate-diagnostic-r2-20261031 \
  --archive-owner-sha256 ACTUAL_OWNER_SHA \
  --archive-sha256 ACTUAL_INDEX_SHA \
  --inventory-sha256 ACTUAL_INVENTORY_SHA \
  --aliases-sha256 ACTUAL_ALIAS_SHA \
  --preservation-map-sha256 ACTUAL_PRESERVATION_SHA \
  --diagnostic-provenance-sha256 2196af5157c900d9faf9ea61b7d51d3f6852d9c3cba6351654d593d88a5ad364
```

Use the actual elevated 380G10 tmpfs namespace. This helper makes one read-only
receipt/tar transport; it does not archive, recapture an endpoint, run a workload,
reboot or retry. It verifies every compressed archive member on 380G10 and emits
the new candidate `analysis-arm.json`. Only after successful verification does it
remove its own redundant transport tar/cache. Failures and partial files remain.
No archived source is executed. Timeout handling terminates only its local SSH
transport and makes no guest-drain claim. Source review is not execution.
