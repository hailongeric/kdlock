# Frame initialization functional checks

Four fixed-work KD sessions passed exact frozen-oracle replay, each including warmup and the requested fixed work. No throughput is reported.

| Body | Workers | Execution evidence | Exact drain |
|:---|---:|:---|:---|
| mutex | 1 | NO_JIT | Passed |
| mutex | 8 | RETURNED_JIT | Passed |
| mutex-locality | 1 | NO_JIT | Passed |
| mutex-locality | 8 | RETURNED_JIT | Passed |

The one-worker points completed locally with `NO_JIT`; the eight-worker points have exact returned-body evidence. All source snapshots matched commit `96fc5e89d608a843025d17c1893577a99e54357b`.

[Functional audit and receipt hashes](audit.json). The full archive and frozen replay receipts remain in the raw campaign directory.
