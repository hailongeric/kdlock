# 下一阶段性能优化任务

本轮执行：[单锁字、本地哈希与稳定角色](design/locking.md)。基线已提交为
`7e2460c`；已清理停用 spin 分发/缓存并实现单锁字、本地哈希及角色；mutex 接入及生命周期检查保留。
当前协议以链接的 locking 章节为准，旧 hook 性能入口已删除。

本清单保留性能实验顺序及剩余任务，2026-09-20 的单锁字/本地哈希进度以
上述协议链接和本轮结果报告为准。历史证据不自动成为当前版本的验收。总体正确性事项和明确延期项目仍在
[TODO](TODO.md)，这里统一维护性能实验的顺序、修改范围和验收条件。
源码位置查 [CODE_MAP](CODE_MAP.md)，具体执行步骤及 TCLock 对照查
[EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。

## 1. 现状与证据边界

当前普通 spin/mutex 已使用 caller-clobber：入口和正常完成只传 RIP/RSP/RBP，
中途退出才物化 FULL 包。PT/Stack 共用寄存器区、批内 C 循环、预备预取提示、
请求热字段集中和 spin node 通知分行均已实现；旧 gate 已删除。这些不再列为
待做的“消除重复保存”任务。legacy/FULL、独立 owner 记录及最终 ACK 仍有用途。

当前已实现单锁字及分类型 CPU 本地哈希，协议与准入的唯一说明在
[locking](design/locking.md)。原 gate/S、Linux L 二次获取、站点缓存和全局晋升集合
均已删除。10240 次批量时钟、400 亿 TSC CPU 窗口和 25 亿 TSC 单锁窗口保留，
16 桶/6 候选使用 score-error 准入。统计识别频率，尚不判断代理的净收益。
本轮阶段结果见 [单锁字报告](../bench/tclock_compare/results/20260920-singleword.md)。

| 已有证据 | 可以说明什么 | 不能据此说明什么 |
| --- | --- | --- |
| [本地发现组件对照](../bench/hotlock_record/results/20260919-local-discovery.md) | 冷地址及正向命中的 record 组件成本下降；每 CPU 独立发现也增加总准备工作 | 当前完整 lock/body/unlock 的收益、稳态 JIT ≥99% |
| [1/4/8/16/20 线程三方数据](../bench/tclock_compare/results/20260919-thread-scaling.md) | 当时版本的扩展趋势；4 线程短批次和高线程长批次的差别 | 后续布局及本地发现版本的当前成绩 |
| [缓存行隔离配对](../bench/spin_cacheline/results/20260919-cacheline-isolation.md) | 当时 kdlock 的 20 线程改善及 4 线程回退 | node 与 gate 各自的贡献，或独立多锁的 gate 干扰 |
| 历史 IP 采样及源码依赖链 | 指出需要测量的候选热点 | 精确的缓存转移数、单独 wrapper 成本或因果归因 |

### 与 TCLock 的剩余差异

| 阶段 | kdlock 保留的额外工作 | 优化约束 |
| --- | --- | --- |
| 获取入口 | 本地频率、source/上下文筛选、翻译条目身份 | 不能跳过冷却、新旧 ABI 或 source 状态 |
| 排队 | 单 KD 字、稳定 ticket 与请求引用 | KD 对象只能使用 KD 协议；Linux peer 使用独立 Linux 对象 |
| 每个正文 | wrapper 元数据、frame、虚拟 SP/BP/地址重写、生成代码分派 | TCLock 直接切 waiter 原生栈；两者并非等量机器指令 |
| 完成与续跑 | 终态核对、复杂出口、远端/native owner ACK、最后引用释放 | 普通 COMPLETE 已有专门路径，不能把复杂出口也当精简完成 |
| 观测 | 正文证据、精确 waiter 数和可选统计 | 统计可近似，影响排空/owner 的协议量不能随意近似 |

## 2. P0：建立当前版本的可信基线

- [ ] **P0.1 诊断已知并发冷准备故障。** 保留 c16/t4/clobber 准备阶段的
  [RCU stall 记录](../bench/tclock_compare/results/20260918-native-stack.md#失败记录与边界)，
  先以受控、可恢复的定向用例定位是否发生在发现、发布或队列依赖阶段。
  当前本地发现版本是否仍复现需要实测；没有复现不等于已证明旧根因修复。
  单 CPU 48000 次准备是已有稳态测量策略，不是修复。
- [ ] **P0.2 分开测冷启动与稳态。** 当前 benchmark 单 CPU 准备能发布 entry，
  不能使其他 CPU 自动满足本地频率。先明确每条测量臂的准备过程；若增加每 CPU
  真实空临界区准备，应放在计时外，单列成本，核对目标正文没有被提前执行。
  不通过写 hot 表、伪造计数或放宽正文证据取得高 JIT 比例。
- [ ] **P0.3 重跑同环境三方基线。** 在同一 kdclobber2、缓解配置、帧指针、
  编译选项、caller ABI、CPU 放置和负载下，对比 Linux / TCLock / kdlock，
  覆盖 1/4/8/16/20 线程 × 1/16 cacheline，每配置交替五次；普通 clobber 为主。
  legacy/native caller 的 spill 成本另设小型配对，不混入三方比值。
  使用[三方运行器](../bench/tclock_compare/README.md)，先核对计划及准备适配，
  不把本文矩阵当作本轮已经执行。

交付：冻结源码/二进制/内核身份、逐会话数据、完整操作 Mops/s 和 ns/op、实际
JIT 比例、批长、离散程度、准备时间及失败记录。按相同统计口径比较中位数和
每次配对值；NO_JIT 仍记录成本，但不算代理通过。实际 JIT、完整数据、owner
ACK 和排空任何一项失败，该会话不得进入性能通过集合。

## 3. P1：避免不划算的代理，并降低原生入口成本

已完成不代理请求的共用 MCS 队列及普通 fast-owner 解锁：冷锁/拒绝不再默认
循环 CAS，无需 JIT request/frame；实际节点耗尽仍保留先读后 CAS。
这解决原生排队机制，收益驱动的代理选择仍未实现。小范围前后比较见
[不代理 MCS](../bench/tclock_compare/results/20260920-native-mcs.md)。


### P1.1 基于收益的新请求准入

假设：轻竞争时逐请求准备不能被短批次摊销，是高频却低收益的重要候选原因。
旧 4 线程记录已经 hot 且 ready，批长约两个正文；继续降低热锁阈值不直接解决它。

- [ ] 先以默认关闭、低频的观测统计批次结束原因、正文数和原生竞争结果。
  区分“没有后继”“批量上限”“entry 拒绝”“复杂出口”，不逐次打印。
- [ ] 在新 root 边界试验 native / bounded probe / delegate 三态，加入滞回和
  冷却期；优先使用每 CPU 状态，避免再建立全局频繁写计数。频率只决定值得
  观察，不直接决定收益；先测代理/原生完整成本，再确定决策规则。
- [ ] 切换仅影响未来请求。旧 ticket、批次、native owner 和 ACK 按原协议排空；
  保留有效翻译条目。性能降级不能复用永久 `jit_disabled` 或 source retire。

位置：[kd_lock.c](../kernel_module/kd_lock.c)、[kd_hotlock.c](../kernel_module/kd_hotlock.c)、
[combiner.inc](../kernel_module/spin/combiner.inc)。验收：低竞争逼近匹配原生臂成本，
高竞争保持收益和实际覆盖；报告转换时间及探测成本。目标是稳定负载下接近
0% 或 ≥99% JIT，但不以等待凑批、漏计原生正文或降低覆盖制造数字。转换阶段
允许混合比例；如果高 JIT 仍更慢，应选择原生而非追求比例。

### P1.2 分离 caller spill、hook 与 record 的成本

- [ ] 先做单线程 native 调用边界配对，核对反汇编中的活跃值 spill/reload、
  SP/BP 和续点；使用当前显式 API 设计配对，旧 hook dispatch-floor 已删除。
- [ ] 在相同 frozen build 对照 cold、local-positive、碰撞地址流和每批检查点。
  测本地重入门、preempt pin、哈希和满表六候选淘汰，区分均摊成本和周期峰值。
  保留重入丢样及锁地址校验，不以失去正确身份缓存为优化。
- [x] 删除已停用站点缓存；该参数对照已不适用于当前直接 API。

位置：[kd_hotlock.c](../kernel_module/kd_hotlock.c)、[kd_lock.c](../kernel_module/kd_lock.c)、
[hotlock 组件基准](../bench/hotlock_record/README.md)。验收以完整操作为主，
组件 ns/call 只解释差异；组件下降不能替代端到端吞吐或 JIT 覆盖。

## 4. P2：减少逐请求同步和生成代码成本

### P2.1 真共享及多锁缓存行为

- [ ] 独立测量 `waiter_count` 的增减 RMW、ticket 引用和 source lease。
  先列全消费者，区分诊断近似量与排空/生命周期精确量，再评估是否能按批持有、
  转移所有权或减少重复读取。已有批次 source lease 不重复列为新方案。
- [ ] 用单锁和独立多锁两类负载分别检验 node/锁字的隔离效果；记录 footprint
  和碰撞，不把每 CPU 缓存放大到导致更高 miss。需要可靠硬件事件时先验证 guest
  PMU 能力，缺失时不声称测到了 cache-to-cache 转移。

位置：[diagnostics.inc](../kernel_module/spin/diagnostics.inc)、
[kd_spin_entry.c](../kernel_module/kd_spin_entry.c)、
[kd_source.c](../kernel_module/kd_source.c)。验收必须保留 native peer 排斥、精确
排空、node 复用与 request 最后引用约束；删除原子本身不是成绩。

### P2.2 wrapper、JIT 分派与地址重写

- [ ] 按冻结原生/JIT 汇编比较每次正文的指令数、scratch spill、虚拟栈/地址
  改写及入口分派；把编译器 caller spill 与 wrapper 保存区分开。
- [ ] 对正常 COMPLETE 路径的重复元数据读取做小步 A/B；仅在身份、准入结果
  及有效期可证明一致时复用。中途 FULL、hostcall 和远端处理保留独立出口。
- [ ] 单列观察层成本：默认 `jit_timing=0`，采样会话与吞吐会话分开。
  quiet 仍有实际正文计数；不能删 witness 后把同一结果宣称为已验证 JIT。

位置：[wrapper.S](../include/wrapper.S)、[wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc)、
[frame_lifecycle.inc](../kernel_module/execution/frame_lifecycle.inc)、[special_inst.py](../disassem/special_inst.py)、
[normal.py](../disassem/normal.py)。现有 inclusive timer 可重叠，不能直接相加作为
纯 CPU 成本。若改变生成指令，选择真实生成代码及受影响边界测试，而非只测模型。

### P2.3 预取策略

- [ ] 使用已有 `spin_prefetch=0/1/2` 比较不预取、consumer 查找和 producer 提示，
  固定布局、批长、caller ABI 与 JIT 覆盖，关注 4/20 线程的差别。
- [ ] 仅在收益明确后试距离/范围；分别核对 producer 新增写入、无效预取及
  可能的缓存污染。预取地址是提示，不能替代权威 frame 或生命周期引用。

位置：[prefetch.inc](../kernel_module/spin/prefetch.inc)。验收看完整吞吐/延迟和
请求 footprint；不因某一热点采样比例降低就判定成功。

## 5. P3：嵌套、mutex 与更广负载

- [ ] 先诊断[历史：七角色双 CPU mutex 失败](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#mutex-pinned-mode4-failure)的
  可运行性依赖；禁止抢占轮询是当前契约，不能悄悄改回旧睡眠等待来取得通过。
- [ ] 在明确 CPU 放置后，分别测同/异队列嵌套、乱序释放、hostcall 和 native 后缀。
  先验证一次副作用、原 owner ACK 和排空，再分析 packet 分离与服务成本。
- [ ] 基础收益成立后再扩展多锁、正文长度、NUMA、输入集和公平性。独立 TCLock
  当前已验收的是普通单锁 spin 路径，不能用它推导 mutex 或任意嵌套的性能。

访问时 guard、通用 flags/特殊指令语义及不可变 JIT 版本仍按用户决定延期；
这份性能清单没有将它们重新加入本轮实施范围，也不消除其限制。

## 6. 实施顺序与停止条件

建议下一轮先完成 P0 的准备口径和当前基线，再做 P1.2 成本拆分及 P1.1 的
有界准入实验；随后按实际热点选择 P2 的一个任务，最后扩展 P3。
每个实验只改变一个可解释因素，记录假设、开关、冻结输入、配对数据和结论。
先运行基础及直接相关验证，需要 live 时只选受影响协议，不默认跑全量。

出现数据错误、旧 owner 未 ACK、未排空或已执行前缀重放，立即停止性能判定并
保留故障证据。覆盖变化或 CPU 准备不同使配对失效；收益在重复运行中不稳定，
保留原默认并报告未证实，不继续堆叠补丁掩盖回退。

本轮[联合测量](../bench/tclock_compare/results/20260920-local-hash.md)已完成单字、记录器及策略分阶段比较；adaptive 在本负载回退，收益选择和滞回仍未实现。
