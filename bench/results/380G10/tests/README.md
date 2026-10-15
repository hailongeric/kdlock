# Source-host checks and historical tests

Current source edits and read-only documentation/archive checks run on `380G10`.
Builds and executable tests run in the VM on `10.176.26.71`, whose receipts belong
to [that machine index](../../10.176.26.71/README.md).

Original-host executable test archives remain in `../raw/legacy/`, with their
frozen commands, inputs and drain records. [Validation](../../../../docs/VALIDATION.md)
indexes those historical receipts and their source-specific limits.

The [2026-10-15 documentation refresh](documentation-refresh-20261015.json)
records static guide/link checks, source-backed options, full-grid result-table
consistency and the local branch inventory. It runs no compiler, kernel test or
benchmark and preserves the earlier measurement receipts.

The [2026-10-12 documentation cleanup](documentation-cleanup-20261012.json)
records the guide audit, obsolete-file removal and archive-backed duplicate-copy
pruning. It contains static checks only, with canonical archive identities and
preservation proofs.
