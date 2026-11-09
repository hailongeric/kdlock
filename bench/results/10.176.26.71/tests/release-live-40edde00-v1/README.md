# Munmap g6: executed, but no retained-root completion

One focused live diagnostic used the exact tested `40edde00525b` source archive
and its previously built 128-image kdscope5 provider. Provider and workload
actually started. All eight short eight-process applications exited zero,
drained and passed per-root counter conservation. No test driver or build was
repeated. This was unscored learning, not performance qualification.

**Munmap did not complete its retained JIT scope.** Each published replacement
was exercised, reaching g6 NORMAL. The two applications bound to g6 recorded
425,584 and 426,048 JIT entries respectively; every entry finished native
handback and both recorded zero retained-root returns. Application completion
and native custody/cleanup are separate from retained-root JIT completion.

| Application | Startup munmap generation | JIT entries | Retained-root returns | Finished handbacks |
| --- | --- | ---: | ---: | ---: |
| 0 | No registered image | 0 | 0 | 0 |
| 1 | 1 | 623,552 | 0 | 623,552 |
| 2 | 2 | 552,151 | 0 | 552,151 |
| 3 | 3 | 478,610 | 0 | 478,610 |
| 4 | 4 | 445,963 | 0 | 445,963 |
| 5 | 5 | 425,865 | 0 | 425,865 |
| 6 | 6 | 425,584 | 0 | 425,584 |
| 7 | 6 | 426,048 | 0 | 426,048 |

## Concrete handback limits

No final CALL/IJ record remains pending for munmap. Its last admitted CALL,
`mas_spanning_rebalance` at `0xffffffff826bfd20`, was learned from g5 and
incorporated into g6. Further ordinary miss learning alone cannot remove the
remaining permanent native exits.

G6 contains nine known release terminals and 15 source frontiers. Concrete
static candidates include:

- `mas_nomem` CALL `_raw_spin_unlock` at `0xffffffff826c6b6a`, with actual
  return word `0xffffffff826c6b6f` (assembly lines 121731–121743). With remaining
  owners, the candidate runtime completes this release once and hands back the
  exact saved continuation.
- `__memmove`'s `STD` at `0xffffffff826f0777` (assembly lines 123404–123418),
  followed in native source by `REP MOVSQ` and `CLD`. The original JIT emits a
  pre-instruction `SOURCE_FRONTIER` there.

These are possibilities in the image, not observed per-invocation exit reasons.
`service_trace` was off and the counters retain no exit IP/reason or owner state.
This run therefore cannot distinguish intentional nonfinal-release fallback
from a source-frontier exit, nor prove that a release-bounded unit reached its
runtime unlock boundary. The exact g6 assembly SHA256 is
`c98154797e822db9583a3b6fb1cf344bffd47fd0abaa6c08f09e325611104a28`.

The smallest release-continuation mechanism would retain compiler cuts,
authorize exact post-release unit-entry IPs under the same logical root, and
resume the original JIT from its saved packet while owners remain. Missing
units would still hand back. This does not resolve the separate `STD` frontier;
actual handback attribution is needed before choosing the next implementation.
Neither mechanism was added and no follow-up run was started to answer this.

## Separate mmap refusal and safe stop

Mmap remained g0 NATIVE_ONLY: `CONTEXT_NATIVE_ONLY` at
`vma_interval_tree_insert`, `0xffffffff817d4690`, reports
`reachable text exceeds 32 CFG expansions` (daemon log line 2921).
The unchanged bound was preserved. The diagnostic's combined-root stability
condition therefore failed after its eight-invocation allowance, despite stable
munmap g6. Its error remains `bounded short learning did not settle during an application`.

Exact retirement separately succeeded with state 2, modules/frames/writers zero,
and final idle. Normal recovery verified `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`d794c6f4-85cc-484b-a290-471c44d68497`. No actor or acquire-boundary rewrite
was included. The current Git checkout was untouched: immutable tested source
was reused after unexecuted checkout aborts, with no stated policy denial or
change to the supported SSH/identity/approval route.

[receipt.json](receipt.json) retains exact per-application startup generations,
counts, stop state and recovery. Full verified evidence is
`/tmp/kdlock-release-live-collected/evidence.tar` (393 indexed entries), SHA256
`e1a933d892078ff6450ff39e68efa538a54220ab7264f8591fabcccd5640857e`.
All regular files and literal link metadata were verified without following
links. The guest evidence is under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/kdlock-release-live-run-40edde00525b-zx89t3s5/processes/kd`.
