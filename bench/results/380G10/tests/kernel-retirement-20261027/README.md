# Historical worktree cleanup, October 27, 2026

The user retired the Linux 6.1 kernel experiments before adaptation to Ubuntu
26.04 / Linux 7.0. On source host `380G10`, this cleanup removed **24 clean
historical worktrees** after preserving each exact HEAD under an explicit
`archive/kernel-retirement-20261027/<worktree-name>` branch. All 24 references
were checked after removal. The main checkout and index were not targeted.

| Observation | Result |
| --- | ---: |
| Selected worktrees | 24 |
| Planned allocated bytes (`du`) | 3,213,139,968 |
| Available filesystem bytes before | 27,672,641,536 |
| Available filesystem bytes after | 30,893,453,312 |
| Observed available-byte increase | 3,220,811,776 |
| Retained worktrees | 23 |
| Privileged process scan errors / matching references | 0 / 0 |

The observed space increase is 3.000 GiB; concurrent
host activity can affect that difference. It is separate from the planned
allocated-byte inventory. No kernel image, benchmark archive, result, dirty
worktree, or ignored evidence directory was deleted by this operation.

The other 23 worktrees remain registered: 21 contain uncommitted historical
experiment work and two contain ignored raw results. Their HEADs, full Git
status, binary changes relative to HEAD, ignored/untracked path lists and
file metadata matched before and after. This is the stated comparison scope,
not a claim of hashing every retained file.

A privileged read-only scan inspected 678 host processes'
working directories, open-file paths and mapped files before removal, with no
matching references or access errors. Each candidate's HEAD and clean status,
including ignored files, were rechecked immediately before its archive ref
was created. Removal used ordinary `git worktree remove`, without `--force`.
A process scan is a point-in-time observation.

- [Exact selection and retention plan](clean-worktrees-plan.json)
- [Privileged process-reference check](privileged-process-scan.json)
- [Removal, references, free space and retention verification](clean-worktrees-results.json)

This was source-host housekeeping and offline verification. It ran no builds,
unit tests, benchmarks, guest kernel changes or VM operations.
