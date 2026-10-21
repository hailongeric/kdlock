# Separate mmap and page-fault validation

Status: implementation prepared; VM correctness and timing pending. This stage
follows the user's instruction to retain concurrent, local readers and split
mmap from page-fault workloads. No admission or protocol checks are removed.
The sole source writer and VM executor is the main agent; helpers are inactive.

The unbuilt exclusive-lookup draft is preserved at
`codex/archive-mmap-exclusive-lookup-20261021`, commit
`206cfc158169d66baaa95fa3c22e4d7e9e7f210c`. Its artificial writer sequence was
rejected before any build or VM execution. No result from that draft is a pass.

The maintained source keeps the original shared reader protocol. Only the task
pointer capture moves before the backing critical section, and final release
also refuses context/data errors. Two separately named workloads have distinct
oracles: mmap-only must perform zero callbacks and zero backing acquisitions;
CPU faults must produce one callback and reader pair per successful fault cycle.
Retry/revalidation/fallback checks and real metadata-writer concurrency remain.
TCLock is included only for supported resident backing operations. Native mmap
ownership stays Native; no TCLock or KD mmap-lock replacement is claimed.

The previous [local correctness stage](../mmap-fault-optin-20261021/README.md)
is fixed historical evidence. All seven mutex regressions remain open at the
[prior investigation](../../bench/pipecap-owner-20261021/final-status.json).
New source versions, observations and future timings must remain separate from
those baselines. Acceptance is false until remaining gaps are resolved or
explicitly listed as unresolved.
