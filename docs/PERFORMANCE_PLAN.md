# 性能优化任务

本页只维护当前状态、未完成任务和测量约束；操作见 [AGENTS](AGENTS.md)，
正确性与延期范围见 [TODO](TODO.md)，命令和成绩集中在
[三方运行器](../bench/tclock_compare/README.md)。已撤回候选的过程保留在结果报告与Git历史，
不再列为当前实现或重复的下一步任务。

## 1. 当前状态与证据边界

当前实现包含 `39b0e7c` 的continuation错位布局、`1eaaf99` 的简单batch元数据
单次初始化，以及 `ccefa62` 保存的默认CPU热值C `if` 获取和MCS发布采样。
解锁使用通用clobber入口。冷路径保留完整
CAS/pending/MCS；获取的宽clobber只属于热分支，解锁始终传递lock/SP/IP/BP。
寄存器保存由编译器决定，不手写push/pop，也不保证所有保存都在热分支内。

spin CPU每次实际MCS发布检查400亿TSC窗口，无队列深度门槛；fast/pending不计数。
mutex CPU每1024次入口检查，单锁第33次检查25亿窗口。精确地址哈希无候选、淘汰或
busy字段，满表保留已有身份；owner/ticket/frame不依赖热表。规则以
[执行流](JIT_EXECUTION.md#21-热度与角色)为准。

单锁字、原生MCS、根fast/pending免ticket、caller-clobber、共享寄存器包、批内C循环、
正常完成专用路径、node通知分行及source lease均已实现。每CPU仍分配20 KiB；
continuation在低12 KiB内错位，高8 KiB等待栈不变；完整布局见
[frames](design/frames.md#911-reuse-before-copy-contract)。这些不再作为待实现任务。

| 当前证据 | 结论与边界 |
| --- | --- |
| [默认热度分流完整三轮](../bench/tclock_compare/results/20260923-spin-default-heat-full3.md) | 168场覆盖1/2/3/4/8/16/20线程、c1/c16和observe/adaptive；低线程仍有明显波动及相对TCLock差距 |
| [元数据与存储布局调查](../bench/tclock_compare/results/20260923-spin-single-hot-balance.md) | 20线程恢复到历史水平；单线程短测较新基线下降约5%–6%，独立长对照未复现一致降幅；代码地址也变化，未隔离缓存根因 |
| [历史恢复](../bench/tclock_compare/results/20260922-performance-recovery.md) | 属于当时采样器；其中PMU来自恢复前慢版，不能冒充历史快版或当前PMU |

当前测量不能解释为全量功能通过。并发冷准备RCU stall、pinned mutex mode-4
soft lockup及其他真实限制保留在 [TODO](TODO.md#current-checkpoint)。

### 与 TCLock 的剩余差异

| 阶段 | KD保留的工作 | 不能删除的边界 |
| --- | --- | --- |
| 获取与排队 | CPU/锁频率、上下文与翻译身份检查；稳定ticket及continuation | 冷却、ABI/source有效性、KD自身排队协议 |
| 正文 | wrapper元数据、frame、虚拟SP/BP和地址重写、生成代码分派 | TCLock切换原生waiter栈，两者不是等量机器指令 |
| 完成与续跑 | 终态、复杂出口、owner ACK、pop/借用退休和最终恢复 | FULL、native后缀及远端请求不能当成最小COMPLETE |
| 观测 | 正文证据、精确waiter数和可选统计 | 不得近似排空/owner协议量或删除JIT witness |

## 2. P0：建立当前版本的可信基线

正式测量只比较Linux原生、TCLock与当前KD。默认每配置3轮，取有效最大吞吐及
同场ns/op，同时报告min/median/max/spread、KD/Linux、KD/TCLock及所有原始样本。
旧版成绩只作历史参照；当前配置或组件的诊断对照不能混为新增旧KD正式测量臂。

- [x] 完成当前默认壳的完整三轮线程矩阵，以及元数据/布局优化的定向功能和独立长对照。
- [ ] 诊断已知并发冷准备故障。单CPU48000次预热是稳态测量方法，不是修复；
  没有在当前版本复现也不能宣布旧根因消失。故障位置见 [TODO](TODO.md#current-checkpoint)。
- [ ] 分开衡量冷启动、本地热度准备及稳态。其他CPU不会因单CPU准备自动变热；
  新增真实准备必须在计时外单列成本，不能写hot表、伪造计数或提前执行目标正文。
- [ ] 继续区分短测波动、测量长度及组件成本。完整操作、实际JIT和观察开销分别报告；
  PMU长批次不混入短测取优，三轮范围不是置信区间或统计等价证明。

冻结源码/ELF/内核身份、CPU放置、命令、逐会话结果及失败记录。发布NORMAL不等于
执行；运行器要求实际JIT的配置缺正文、业务错误、owner ACK或排空失败均不能算性能通过。
允许原生完成的少线程配置须保留NO_JIT标记，不作为JIT正例。
TCLock未观测代理计数，不能推算其批长。原始快慢样本不因异常而删除。

## 3. P1：避免不划算的代理并降低原生入口成本

### P1.1 基于收益的新请求准入

频率发现已经实现，收益驱动的native/probe/delegate选择尚未实现。2/3线程真实MCS
可升温，不能靠线程数或CPU热值保证值得代理。低竞争短批次成本仍是待测问题。

- [ ] 先以默认关闭、低频观测区分无后继、批量上限、entry拒绝和复杂出口，不逐次打印。
- [ ] 比较完整代理/原生成本后，再试新root边界的有界探测、滞回及冷却，优先使用
  每CPU状态，不增加全局高频写入，不靠等待凑批或漏计原生正文获得高JIT比例。
- [ ] 切换只影响未来请求；旧ticket、批次、native owner及ACK照常排空，保留有效
  翻译条目。性能降级不能复用永久 `jit_disabled` 或source retire。

位置：[kd_hotlock.c](../kernel_module/kd_hotlock.c)、[kd_lock.c](../kernel_module/kd_lock.c)、
[combiner.inc](../kernel_module/spin/combiner.inc)。高JIT比例仍更慢时应选择原生；
准入转换成本、冷却及稳定性能需要分别验证。

### P1.2 调用边界与采样成本

- [x] 按本次授权试验spin单锁计数32→128/1024，固定CPU和单锁时间窗口；
  两候选均未同时改善低线程并守住8/20线程，已恢复32。
  [三轮诊断](../bench/tclock_compare/results/20260923-adaptive-threshold-sweep.md)
  表明减少单锁采时仍未消除3/4线程短代理批次；收益准入继续按P1.1评估。
- [x] 扩展到单锁窗口、CPU窗口和MCS间隔及成比例组合的
  [三轮诊断](../bench/tclock_compare/results/20260923-adaptive-windows.md)。减少MCS采时改善部分8线程成绩，
  过紧窗口损害20线程，低线程未一致改善；保留原默认。窗口/间隔相互影响，不能仅按采时次数推定收益。
- [ ] 在同一冻结构建中分离caller spill/reload、SP/IP/BP传递、已有pin复用及热表成本。
  普通API自己的抢占保护不可删除，已撤回的clock强制内联不作为优化成果。
- [ ] 比较cold、local-positive、碰撞地址流和窗口重置，区分均摊成本与峰值。
  所有候选保持MCS1/400亿窗口/lock32语义，除非任务明确调整策略。
- [ ] 单线程短/长批次分别报告，不能将长度变化产生的绝对吞吐跳升归为布局收益。

以完整操作吞吐为验收；组件ns/call或指令数下降只能解释候选，不能替代实际JIT覆盖。

## 4. P2：减少逐请求同步和生成代码成本

### P2.1 共享数据与布局

- [x] continuation在已有低12 KiB区域内错位；原始基址释放、全部槽位和局部初始化回滚已验证。
- [ ] 若继续定位缓存原因，独立控制代码地址与数据放置；先核对guest PMU能力，
  没有硬件事件时只报告地址几何模型，不宣称测到cache-to-cache或L1 miss因果。
- [ ] 逐项核对waiter_count、ticket引用及source lease消费者，再评估按批持有、
  所有权转移和重复读取。诊断近似量与精确排空/生命周期量分开。
- [ ] 用单锁与独立多锁分别检验布局、footprint和碰撞，不把每CPU缓存盲目放大。

位置：[diagnostics.inc](../kernel_module/spin/diagnostics.inc)、
[kd_spin_entry.c](../kernel_module/kd_spin_entry.c)、[kd_source.c](../kernel_module/kd_source.c)。
保留native peer排斥、node复用、frame退休及continuation最后读取约束。

### P2.2 wrapper、JIT分派与地址重写

- [x] 简单spin batch按ABI一次写最终元数据；通用helper仍处理mutex/复杂路径。
- [ ] 按实际原生/JIT汇编比较指令、scratch spill、虚拟栈及地址重写；仅在身份、
  准入与有效期可证明一致时复用状态。FULL、hostcall与远端处理保留独立出口。
- [ ] 测量观察层成本，默认 `jit_timing=0`，采样与正式吞吐分开；inclusive timer
  可能重叠，不能相加为纯CPU成本。生成指令变化要验证真实生成代码及对应边界。

位置：[wrapper.S](../include/wrapper.S)、[wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc)、
[frame_lifecycle.inc](../kernel_module/execution/frame_lifecycle.inc)、
[special_inst.py](../disassem/special_inst.py)、[normal.py](../disassem/normal.py)。

### P2.3 预取

- [ ] 使用已有 `spin_prefetch=0/1/2` 比较无预取、consumer查找和producer提示，
  固定布局、caller ABI及JIT覆盖，分别看低/高竞争。
- [ ] 收益明确后才扩展距离/范围，同时核对无效预取、污染及新增producer工作。
  提示不能代替权威frame或生命周期引用。

位置：[prefetch.inc](../kernel_module/spin/prefetch.inc)。验收看完整吞吐和footprint。

## 5. P3：嵌套、mutex与更广负载

- [ ] 先诊断已知七角色双CPU mutex的可运行性依赖。published waiter禁止抢占并
  PAUSE轮询是当前契约，不能悄悄恢复旧睡眠等待来取得通过。
- [ ] 明确CPU放置后，再比较同/异队列嵌套、乱序释放、hostcall与native后缀；
  先保持一次副作用、原owner ACK和排空，再分析服务成本。
- [ ] 按实际需求扩展多锁、正文长度、NUMA和公平性；单锁spin的TCLock结果不能
  推广为mutex或任意嵌套性能。

访问时guard、通用flags/特殊指令语义和不可变JIT版本仍明确延期，未重新纳入实施范围。

## 6. 实验选择与停止条件

下一项按复现问题或测得热点选择，先明确假设、当前对照、冻结输入和判据，不自动
执行整个清单。代码修改后可直接测性能；独立单元和live按受影响范围选择，默认不跑全量。
有效改动按独立可回退提交保存，不叠加未经验证的大改动。

数据错误、旧owner未ACK、未排空或已执行前缀重放时停止性能判定并保存证据。
CPU准备、覆盖或输入变化使配对失效；重复收益不稳定时保留原默认，不堆叠补丁掩盖回退。
