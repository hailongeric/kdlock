# 历史验收索引

本页只索引历史冻结版本，不再保留已失效的运行命令和重复实现说明。
当前行为见 [DESIGN](DESIGN.md)、[寄存器 ABI](JIT_REGISTER_ABI.md)；
运行方法和最近验证见 [tests](../tests/README.md)，性能结果见
[bench](../bench/README.md)。历史通过项不能拼接为当前版本的全量通过。

2026-09-20 当前实现为显式 KD 单锁字、分类型 CPU 本地哈希，无全局晋升集合。
最新结果见 [联合报告](../bench/tclock_compare/results/20260920-local-hash.md)。
旧透明 hook live 套件及其工作负载已删除，历史参数只能与匹配 checkout 一同使用。
下列固定版本记录保留原始成功、失败和证据身份，不构成当前测试库存。

仍未解决的 pinned mode-4 soft lockup、并发 promotion RCU stall、动态地址
筛查缺口、flags 和原地覆盖风险见 [TODO](TODO.md#current-checkpoint)。
本次压缩文档没有修复这些问题，也没有重跑历史矩阵。

所有下列链接固定到整理前提交，包含原结果、失败、源码身份、证据路径及
当时的命令。也可以离线读取：

```sh
git show 17f146e52f9f52485b8211addb7dab7195e70452:docs/VALIDATION.md
```

原始归档位于仓库外；新 checkout 不包含 `/tmp` 或 guest 证据。
归档哈希只对原记录负责，不表示本次重新认证全部历史归档。

## 冻结记录

| 原记录 | 完整证据说明 |
| --- | --- |
| <a id="demo-workload-module-layout"></a>Demo workload module layout | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#demo-workload-module-layout) |
| <a id="spin-cacheline-microbenchmark"></a>Spin Cacheline Microbenchmark | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#spin-cacheline-microbenchmark) |
| <a id="spin-static-dispatch-profiling"></a>Spin static dispatch profiling | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#spin-static-dispatch-profiling) |
| <a id="native-fast-path-optimization"></a>Native fast path optimization | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-fast-path-optimization) |
| <a id="continuous-lock-contention-scan"></a>Continuous lock contention scan | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#continuous-lock-contention-scan) |
| <a id="single-thread-investigation"></a>Single-thread investigation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#single-thread-investigation) |
| <a id="full-rescan-after-workload-consolidation"></a>Full rescan after workload consolidation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#full-rescan-after-workload-consolidation) |
| <a id="batch-calls-and-timing-documentation"></a>Batch calls and timing documentation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#batch-calls-and-timing-documentation) |
| <a id="atomic-worker-coordination"></a>Atomic worker coordination | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#atomic-worker-coordination) |
| <a id="benchmark-only-build-separation"></a>Benchmark-only build separation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#benchmark-only-build-separation) |
| <a id="initial-full-scan"></a>Initial full scan | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#initial-full-scan) |
| <a id="repository-checkpoint"></a>Repository Checkpoint | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#repository-checkpoint) |
| <a id="native-handoff-timing"></a>Native Handoff Timing | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-handoff-timing) |
| <a id="isolated-python-runtime"></a>Isolated Python Runtime | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#isolated-python-runtime) |
| <a id="mutex-oversubscription-assessment"></a>Mutex Oversubscription Assessment | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-oversubscription-assessment) |
| <a id="private-queue-timing"></a>Private Queue Timing | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#private-queue-timing) |
| <a id="native-owner-wait-timing"></a>Native Owner Wait Timing | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-owner-wait-timing) |
| <a id="jit-boundary-timing"></a>JIT Boundary Timing | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#jit-boundary-timing) |
| <a id="context-symbol-matching"></a>Context-Symbol Matching | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#context-symbol-matching) |
| <a id="translation-resource-accounting"></a>Translation Resource Accounting | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#translation-resource-accounting) |
| <a id="mutex-routine-log-severity"></a>Mutex Routine Log Severity | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-routine-log-severity) |
| <a id="paired-native-jit-experiments"></a>Paired Native-JIT Experiments | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#paired-native-jit-experiments) |
| <a id="tclock-comparator-feasibility"></a>TCLock Comparator Feasibility | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#tclock-comparator-feasibility) |
| <a id="instrumented-benchmark-measurements"></a>Instrumented Benchmark Measurements | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#instrumented-benchmark-measurements) |
| <a id="hotlock-promotion-ordering"></a>Hotlock Promotion Ordering | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#hotlock-promotion-ordering) |
| <a id="typed-scalar-service"></a>Typed Scalar Service | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#typed-scalar-service) |
| <a id="main-plan-acceptance-audit"></a>Main-Plan Acceptance Audit | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#main-plan-acceptance-audit) |
| <a id="shared-b-waiter-exit"></a>Shared B Waiter Exit | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#shared-b-waiter-exit) |
| <a id="progressed-spin-gate-refusal"></a>Progressed Spin Gate Refusal | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#progressed-spin-gate-refusal) |
| <a id="shared-native-mutex-b"></a>Shared Native Mutex B | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#shared-native-mutex-b) |
| <a id="shared-b-mixed-completion"></a>Shared B Mixed Completion | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#shared-b-mixed-completion) |
| <a id="shared-b-combiner"></a>Shared B Combiner | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#shared-b-combiner) |
| <a id="call-quota-continuation"></a>CALL Quota Continuation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#call-quota-continuation) |
| <a id="native-frame-retirement"></a>Native Frame Retirement | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-frame-retirement) |
| <a id="mutex-nested-scheduling"></a>Mutex Nested Scheduling | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-nested-scheduling) |
| <a id="remote-packet-unit"></a>Remote Packet Unit | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#remote-packet-unit) |
| <a id="spin-waiter-publication"></a>Spin Waiter Publication | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#spin-waiter-publication) |
| <a id="original-waiter-exit"></a>Original Waiter Exit | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#original-waiter-exit) |
| <a id="test-inventory-review"></a>Test Inventory Review | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#test-inventory-review) |
| <a id="redundant-node-model-removal"></a>Redundant Node Model Removal | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#redundant-node-model-removal) |
| <a id="redundant-mutex-model-removal"></a>Redundant Mutex Model Removal | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#redundant-mutex-model-removal) |
| <a id="frame-model-consolidation"></a>Frame Model Consolidation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#frame-model-consolidation) |
| <a id="call-model-consolidation"></a>Call Model Consolidation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#call-model-consolidation) |
| <a id="tail-model-consolidation"></a>Tail Model Consolidation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#tail-model-consolidation) |
| <a id="reading-handoff"></a>Reading Handoff | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#reading-handoff) |
| <a id="static-per-cpu-ranges"></a>Static Per-CPU Ranges | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#static-per-cpu-ranges) |
| <a id="dynamic-pointer-screening-gap"></a>Dynamic Pointer Screening Gap | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#dynamic-pointer-screening-gap) |
| <a id="offline-evidence-verifier"></a>Offline Evidence Verifier | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#offline-evidence-verifier) |
| <a id="emitted-block-context-admission"></a>Emitted-Block Context Admission | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#emitted-block-context-admission) |
| <a id="renamed-native-frame-routing"></a>Renamed Native-Frame Routing | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#renamed-native-frame-routing) |
| <a id="native-b-peer-cancellation-and-retry"></a>Native B Peer Cancellation And Retry | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-b-peer-cancellation-and-retry) |
| <a id="queued-spin-acquisition"></a>Queued Spin Acquisition | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#queued-spin-acquisition) |
| <a id="checked-spin-acquisition"></a>Checked Spin Acquisition | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#checked-spin-acquisition) |
| <a id="spin-gate-pressure"></a>Spin Gate Pressure | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#spin-gate-pressure) |
| <a id="environment-evidence"></a>Environment Evidence | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#environment-evidence) |
| <a id="early-outer-continuation"></a>Early-Outer Continuation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#early-outer-continuation) |
| <a id="same-cpu-mutex-continuation"></a>Same-CPU Mutex Continuation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#same-cpu-mutex-continuation) |
| <a id="remote-relay-after-waiter-exit"></a>Remote Relay After Waiter Exit | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#remote-relay-after-waiter-exit) |
| <a id="repository-native-controls"></a>Repository Native Controls | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#repository-native-controls) |
| <a id="mutex-shadow-with-live-frames"></a>Mutex Shadow With Live Frames | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-shadow-with-live-frames) |
| <a id="natural-held-lock-capacity"></a>Natural Held-Lock Capacity | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#natural-held-lock-capacity) |
| <a id="scoped-evidence-capture"></a>Scoped Evidence Capture | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#scoped-evidence-capture) |
| <a id="native-b-peers-with-live-frames"></a>Native B Peers With Live Frames | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-b-peers-with-live-frames) |
| <a id="real-spin-ticket-pressure"></a>Real Spin Ticket Pressure | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#real-spin-ticket-pressure) |
| <a id="code-pool-with-live-frames"></a>Code Pool With Live Frames | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#code-pool-with-live-frames) |
| <a id="checked-two-level-mutex"></a>Checked Two-Level Mutex | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#checked-two-level-mutex) |
| <a id="runtime-capability-negotiation"></a>Runtime Capability Negotiation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#runtime-capability-negotiation) |
| <a id="real-mutex-stack-mutation"></a>Real Mutex Stack Mutation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#real-mutex-stack-mutation) |
| <a id="mutex-control-stack-check"></a>Mutex Control Stack Check | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-control-stack-check) |
| <a id="covered-diagnostic-selection"></a>Covered Diagnostic Selection | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#covered-diagnostic-selection) |
| <a id="shared-return-partitions"></a>Shared Return Partitions | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#shared-return-partitions) |
| <a id="two-source-modules"></a>Two Source Modules | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#two-source-modules) |
| <a id="writer-drain-and-source-reuse"></a>Writer Drain And Source Reuse | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#writer-drain-and-source-reuse) |
| <a id="source-pins-and-retirement"></a>Source Pins And Retirement | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#source-pins-and-retirement) |
| <a id="device-session-binding"></a>Device Session Binding | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#device-session-binding) |
| <a id="combined-task-and-node-pressure"></a>Combined Task And Node Pressure | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#combined-task-and-node-pressure) |
| <a id="bounded-return-graph"></a>Bounded Return Graph | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#bounded-return-graph) |
| <a id="source-and-hook-lifetime-review"></a>Source And Hook Lifetime Review | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#source-and-hook-lifetime-review) |
| <a id="real-mutex-node-pressure"></a>Real Mutex Node Pressure | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#real-mutex-node-pressure) |
| <a id="same-cpu-mutex-refusal"></a>Same-CPU Mutex Refusal | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#same-cpu-mutex-refusal) |
| <a id="scoped-regression-organization"></a>Scoped Regression Organization | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#scoped-regression-organization) |
| <a id="parallel-native-frames"></a>Parallel Native Frames | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#parallel-native-frames) |
| <a id="failed-preparations"></a>Failed Preparations | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#failed-preparations) |
| <a id="original-waiter-release-races"></a>Original Waiter Release Races | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#original-waiter-release-races) |
| <a id="failed-bias-expectations"></a>Failed Bias Expectations | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#failed-bias-expectations) |
| <a id="cancellable-native-waiter"></a>Cancellable Native Waiter | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#cancellable-native-waiter) |
| <a id="original-waiter-signals"></a>Original Waiter Signals | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#original-waiter-signals) |
| <a id="spin-virtual-cancellation"></a>Spin Virtual Cancellation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#spin-virtual-cancellation) |
| <a id="mutex-task-lifecycle"></a>Mutex Task Lifecycle | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-task-lifecycle) |
| <a id="mutex-resource-coverage"></a>Mutex Resource Coverage | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-resource-coverage) |
| <a id="resource-registry-coverage"></a>Resource Registry Coverage | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#resource-registry-coverage) |
| <a id="scoped-learned-callees"></a>Scoped Learned Callees | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#scoped-learned-callees) |
| <a id="acceptance-contract"></a>Acceptance Contract | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#acceptance-contract) |
| <a id="recorded-matrix-manifest"></a>Recorded Matrix Manifest | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#recorded-matrix-manifest) |
| <a id="recorded-commands"></a>Recorded Commands | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#recorded-commands) |
| <a id="historical-evidence-index"></a>Historical Evidence Index | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#historical-evidence-index) |
| <a id="matrix-progression"></a>Matrix Progression | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#matrix-progression) |
| <a id="investigation-directory-index"></a>Investigation Directory Index | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#investigation-directory-index) |
| <a id="native-registration-phase-guard"></a>Native Registration Phase Guard | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-registration-phase-guard) |
| <a id="captured-kernel-baseline"></a>Captured Kernel Baseline | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#captured-kernel-baseline) |
