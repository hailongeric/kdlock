# Frozen orchestration evidence

These snapshots record the source-host transport/controllers, guest control
scripts and renderer used for the one-round MM campaign. They are historical
execution inputs, not relocation-safe launch commands. Do not run them as a new
campaign: their output paths, identities and boot requests belong to this run.
Maintained workload implementations are in `bench/mmap_fault/` and
`bench/mmap_lock/` at commit `e74223c8c0d0a1f72f2c7d87560b37c3125a23f5`.
The new raw orchestration scripts were hash-frozen separately from that commit.
The shared-mm report's control-library revision refers to the maintained code,
not to a claim that these new orchestration snapshots existed in that commit.

`transport-reused.py` is the unchanged bounded transport/boot implementation with
SHA-256 `f37653e624a959387de57dd28cfee08fa1b6deb8d6879cb299f5bfde5b2408df`.
A command deadline stops orchestration without signaling an uncertain workload,
unloading its module or assuming drain. Only successful exact accounting and
lifetime checks permit ordinary unload and the next boot.

The private preparation contains 18 split correctness cases and eight unscored
client validation controls. The targeted four-test run and nine negative receipt
checks are retained beside its controller. Shared-mm reuses the unchanged
prepared payload/client and hash-bound actual-API correctness receipts, then
performs fresh readiness on each boot. No prior timed rate fills a new point.

The read-only audits were run before the final documentation edits, against
the captured source revision. Their worktree identity checks deliberately refuse
a later changed worktree. Raw archive bytes and their recorded hashes remain
independently inspectable.
