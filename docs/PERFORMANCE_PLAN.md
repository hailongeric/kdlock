# 性能优化任务

本页只维护当前状态、未完成任务和测量约束；操作见 [AGENTS](AGENTS.md)，
正确性与延期范围见 [TODO](TODO.md)，命令和成绩集中在
[三方运行器](../bench/tclock_compare/README.md)。已撤回候选的过程保留在结果报告与Git历史，
不再列为当前实现或重复的下一步任务。

## 1. 当前状态与证据边界

2026-09-26进行中的c1 NUMA优化：线程扩展到1–8/12/16/20/24/28/32，
worker顺序放置CPU0–31，20线程以内位于node0，24/28/32跨node0/1；collector改为CPU38。
保持固定2.5GHz、全worker预热和2秒内300ms峰值，三方各三轮。
已选择256次代理上限及独立的每batch NUMA扫描预算限制工作量，远端延期链在批次结束后优先交接；
该上限不是调度延迟/无饥饿证明。先保存当前1024/NUMA-off基线，再定向验证候选和比较。
TCLock保留上游1024上限，NUMA-on/off必须随构建身份明确标注，不混合取优。
最终结果尚未完成，不能将本段写作已达Linux/TCLock目标。

当前开发基于ade7d82的有界NUMA实现，选择256上限、局部后继快速选择及冗余状态精简；
完整本轮比较见[NUMA调查](../bench/tclock_compare/results/20260926-numa.md)，下表c1/c8是797e847历史实现证据。
spin使用显式单锁字API、共享continuation/frame、原生pending/MCS路径和统一clobber解锁。
冷获取首次CAS内联，简单batch单次初始化元数据，关闭计时时跳过重复helper。
只保留adaptive：per-CPU获取/MCS差值每512次发布比较，原生队头在同一近似边界检查
捕获队尾以内的五个后继；不等待凑批，不新增逐请求时钟。完整参数与限制见
[执行流](JIT_EXECUTION.md#21-热度与角色)。spin waiter诊断使用per-CPU事件总数，
live聚合近似，独立排空后余额精确；owner/ACK及真正生命周期计数保持不变。

| 当前证据 | 结论与边界 |
| --- | --- |
| [c1三方90场与功能验证](../bench/tclock_compare/results/20260924-warmed-peak.md#captured-tail五后继三方90场完成) | 1–8/16/20线程各三轮，全部业务正确并排空；选定代码的nested/early各200万操作、实际JIT及排空通过 |
| [c1/c8三方126场](../bench/tclock_compare/results/20260925-c1-c8-warmed-peak.md) | 同一锁实现，七个线程点各三轮；c1单线程为Linux的93.2%，16/20线程约为TCLock的89%；c8在8/16/20线程超过TCLock约10%–13% |

峰值、整段吞吐及全部三轮分布以对应报告为准；部分中间版本比较仍有下降，
不能把最好值当成每轮保证，或把不同阶段拼接为普遍无回退证明。
目标仍是c1少于4线程接近Linux、多于4线程超过Linux、高线程接近TCLock。
上述结果不验证mutex性能或全部协议组合；并发冷准备RCU stall、pinned mutex mode-4
soft lockup等已知限制仍见[TODO](TODO.md#current-checkpoint)。

旧阈值、等待、布局候选及其失败证据统一见[历史索引](../bench/tclock_compare/results/HISTORY.md)；
最新优化中的pending512、短批冷却、native6及冷周期下界撤回原因保留在
[峰值调查](../bench/tclock_compare/results/20260924-warmed-peak.md)，不重复列为当前待办。

### 与 TCLock 的剩余差异

| 阶段 | KD保留的工作 | 不能删除的边界 |
| --- | --- | --- |
| 获取与排队 | CPU/锁频率、MCS/获取比例、上下文与翻译身份检查；稳定ticket及continuation | 准入、ABI/source有效性、KD自身排队协议 |
| 正文 | wrapper元数据、frame、虚拟SP/BP和地址重写、生成代码分派 | TCLock切换原生waiter栈，两者不是等量机器指令 |
| 完成与续跑 | 终态、复杂出口、owner ACK、pop/借用退休和最终恢复 | FULL、native后缀及远端请求不能当成最小COMPLETE |
| 观测 | 正文证据、近似live waiter聚合、排空后精确余额和可选统计 | 不得近似排空/owner协议量或删除JIT witness |

## 2. P0：建立当前版本的可信基线

正式测量只比较Linux原生、TCLock与当前KD。固定2.5GHz、全部worker各48000次预热，
连续2秒内取最高300ms全worker窗口并保留整段吞吐。默认每配置3轮，取有效最高峰值及
同场ns/op，同时报告min/median/max/spread、KD/Linux、KD/TCLock及所有原始样本。
旧版成绩只作历史参照；当前配置或组件的诊断对照不能混为新增旧KD正式测量臂。

- [ ] 诊断已知并发冷准备故障。当前显式登记翻译后全worker各48000次预热是测量方法，不是修复；
  没有在当前版本复现也不能宣布旧根因消失。故障位置见 [TODO](TODO.md#current-checkpoint)。
- [ ] 分开衡量冷启动、本地热度准备及稳态。当前全worker参与预热，不强制修改CPU热值；
  新增真实准备必须在计时外单列成本，不能写hot表、伪造计数或提前执行目标正文。
- [ ] 继续区分短测波动、测量长度及组件成本。完整操作、实际JIT和观察开销分别报告；
  PMU长批次不混入短测取优，三轮范围不是置信区间或统计等价证明。

冻结源码/ELF/内核身份、CPU放置、命令、逐会话结果及失败记录。发布NORMAL不等于
执行；运行器要求实际JIT的配置缺正文、业务错误、owner ACK或排空失败均不能算性能通过。
允许原生完成的少线程配置须保留NO_JIT标记，不作为JIT正例。
TCLock未观测代理计数，不能推算其批长。原始快慢样本不因异常而删除。

## 3. P1：避免不划算的代理并降低原生入口成本

### P1.1 基于收益的新请求准入

当前以同一512次MCS边界上的获取/发布差值作近似竞争判断，默认100%门槛；
原生队头在物理获取前增加有界captured-tail资格，已代理队头不做该检查。
不按线程数分流，也不测量完整委托收益。旧确认/冷却/保留状态机已按用户要求移除。
匹配c1矩阵已有收益证据，通用net-cost模型仍未实现；多锁、不同正文及阶段变化不能由本批推断。

- [ ] 先以默认关闭、低频观测区分无后继、批量上限、entry拒绝和复杂出口，不逐次打印。
- [ ] 比较完整代理/原生成本，检验当前比例判断在阶段变化、正文长度和不同锁流下
  的效果，再决定是否扩展为成本模型。保留每CPU状态，不增加全局高频写入，
  不靠等待凑批或漏计原生正文获得高JIT比例。

当前切换只影响未来获取；旧ticket、批次、native owner及ACK照常排空，保留有效
翻译条目。性能降级不能复用永久 `jit_disabled` 或source retire。

位置：[kd_hotlock.c](../kernel_module/kd_hotlock.c)、[kd_lock.c](../kernel_module/kd_lock.c)、
[combiner.inc](../kernel_module/spin/combiner.inc)。高JIT比例仍更慢时应选择原生；
准入转换成本及稳定性能需要分别验证。

### P1.2 调用边界与采样成本

- [ ] 在同一冻结构建中分离caller spill/reload、SP/IP/BP传递、已有pin复用及热表成本。
  普通API自己的抢占保护不可删除，已撤回的clock强制内联不作为优化成果。
- [ ] 比较cold、local-positive、碰撞地址流和窗口重置，区分均摊成本与峰值。
  所有成本隔离候选保持[当前采样与比例策略](JIT_EXECUTION.md#21-热度与角色)，
  除非任务明确调整策略。
- [ ] 单线程短/长批次分别报告，不能将长度变化产生的绝对吞吐跳升归为布局收益。

以完整操作吞吐为验收；组件ns/call或指令数下降只能解释候选，不能替代实际JIT覆盖。

## 4. P2：减少逐请求同步和生成代码成本

### P2.1 共享数据与布局

- [x] continuation在已有低12 KiB区域内错位；原始基址释放、全部槽位和局部初始化回滚已验证。
- [ ] 若继续定位缓存原因，独立控制代码地址与数据放置；先核对guest PMU能力，
  没有硬件事件时只报告地址几何模型，不宣称测到cache-to-cache或L1 miss因果。
- [x] 核对spin waiter_count消费者，保留发布/退出钩子，以per-CPU事件总数替换逐请求共享写；
  基础及batch/storage四组、独立30场通过，性能分布与即时下溢信号限制已记录。
- [ ] 继续核对ticket引用及source lease消费者，再评估按批持有、所有权转移和重复读取。
  owner/ACK及真正排空计数保持精确；spin诊断修改不推广到mutex计数。
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
