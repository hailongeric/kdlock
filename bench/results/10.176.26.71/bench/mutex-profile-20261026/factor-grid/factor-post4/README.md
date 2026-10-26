# Factor-grid build failure

The initial post4 grid stopped while compiling its first Native one-cacheline workload. **No warmup or timing ran; all 18 planned points remain unmeasured.**

The existing workload Makefile required `RB_LINES=16` for mutex cacheline workloads and rejected `RB_LINES=1`. This is a preparation failure, with no throughput value. The failed source is `8b31c980192bd69daf5abedf989a8dacb445ee5f`; any expanded-width retry has a separate source and stage identity.

[Failure and archive hashes](failure.json). The complete failed stage remains in the raw `factor-post4-archive.stdout` archive, including the compiler log, source snapshot and 18 unrun records.
