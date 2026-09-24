# 性能优化任务

本页只维护当前状态、未完成任务和测量约束；操作见 [AGENTS](AGENTS.md)，
正确性与延期范围见 [TODO](TODO.md)，命令和成绩集中在
[三方运行器](../bench/tclock_compare/README.md)。已撤回候选的过程保留在结果报告与Git历史，
不再列为当前实现或重复的下一步任务。

## 1. 当前状态与证据边界

当前实现包含 `39b0e7c` 的continuation错位布局、`1eaaf99` 的简单batch元数据
单次初始化，以及 `ccefa62` 保存的CPU热值C `if` 获取和MCS发布计数机制；
当前工作树按用户要求简化比例准入：采样和比较同为512次MCS节奏，复用原始计数，
只保留16字节的上次获取/MCS快照，允许近似统计和IRQ边界偏移。移除两低确认、原生冷却、
独立频率热值、已接受采样计数及跨比例拒绝保留热度，小型pinned封装内联。
spin单锁达到512次检查12.5亿TSC窗口，mutex保持第1025次/25亿，CPU窗口保持400亿。
动态热表布局、busy guard、CPU热值分流、通用clobber解锁和owner/ticket/frame协议保持。
默认100%比例门槛，0绕过比例；本轮按用户要求移除observe，当前只有adaptive；完整规则见[执行流](JIT_EXECUTION.md#21-热度与角色)。
诊断槽128字节区域隔离、额外4KiB共享存储仍是独立提交439cd82。

单锁字、原生MCS、根fast/pending免ticket、caller-clobber、共享寄存器包、批内C循环、
正常完成专用路径、node通知分行及source lease均已实现。每CPU仍分配20 KiB；
continuation在低12 KiB内错位，高8 KiB等待栈不变；完整布局见
[frames](design/frames.md#911-reuse-before-copy-contract)。这些不再作为待实现任务。

| 现有证据 | 结论与边界 |
| --- | --- |
| [当前比例准入调查](../bench/tclock_compare/results/20260924-contention-ratio.md) | 全部基线、失败候选、诊断与审计索引；简化候选42场正确排空但保护失败 |
| [诊断槽隔离](../bench/tclock_compare/results/20260924-diagnostic-pairs.md) | 439cd82的独立24场pilot及采样证据，不代表1/2/8/16/20线程保护已完成 |
| [MCS8/CPU400万组合](../bench/tclock_compare/results/20260923-mcs8-cpu4m.md) | 历史168/168场、三轮；该批8/20线程adaptive高于上一批默认历史值，3/4线程仍慢，单线程未一致改善 |
| [默认热度分流完整三轮](../bench/tclock_compare/results/20260923-spin-default-heat-full3.md) | 更早MCS1/CPU400亿版本的168场，覆盖1/2/3/4/8/16/20线程、c1/c16和observe/adaptive；不能替代当前比例准入的验收 |
| [元数据与存储布局调查](../bench/tclock_compare/results/20260923-spin-single-hot-balance.md) | 20线程恢复到历史水平；单线程短测较新基线下降约5%–6%，独立长对照未复现一致降幅；代码地址也变化，未隔离缓存根因 |
| [历史恢复](../bench/tclock_compare/results/20260922-performance-recovery.md) | 属于当时采样器；其中PMU来自恢复前慢版，不能冒充历史快版或当前PMU |

实验检查点b83f551及两个后继等待候选未通过性能保护，等待改动已撤回并保留证据。
简化候选已通过基础2组、采样fixture及10项错误变体、运行器26项和W=1构建（11条既有objtool警告）；
`simple512-fixed`的42场KD adaptive正确排空，但16/20线程中位数约低8%–9%，性能保护失败。
当前简化策略按用户要求保留为EXPERIMENTAL检查点。随后`selected-final-fixed`完整168场及
nested/early两场已完成，3/4线程改善但c16/8等保护未满足；该批使用旧单CPU预热。
最新[固定2.5GHz扩展矩阵](../bench/tclock_compare/results/20260924-fixed-expanded.md)使用全worker
各48000次预热，c1/c16及1–8/16/20线程单轮80场全部有效并排空。c1的1/3/5/6线程仍低于Linux，
7线程起该轮高于Linux，16/20线程约为TCLock的98.5%/98.7%；单轮不能证明无回退。
当前任务聚焦c1：少于4线程接近Linux，多于4线程超过Linux，高线程接近TCLock。
用户指定连续2秒中最高300ms的全worker活跃窗口，三方同时保留整段吞吐；先建立相同新口径对照，
再分别检查pending-only等待上限和冷获取调用成本，不把测量变化算作优化。
[新口径基线](../bench/tclock_compare/results/20260924-warmed-peak.md)已完成c1全部10个线程点的三轮90场，
全部有效；低线程差距仍存在，16/20线程的新长测约为TCLock的86%。
冷获取首次CAS及已有计数内联的独立30场已完成：单线程32.729→41.599Mops/s，
约为新Linux基线93.4%；16/20线程差异不到0.4%，接近窗口计数误差界。普通JIT、
observe nested/early和配对冷路径通过；adaptive nested因约50%的比例未执行JIT，保留NO_JIT失败记录。
pending-only等待512候选在2线程大幅改善，但4线程约下降11%–12%，已撤回为1；不合并到本次内联改动。
诊断身份复用独立30场通过，8线程峰值约+1.69%，16/20线程基本保持；4线程仍波动且本批中位数较低。
一次短批即冷却候选使热群崩溃，已撤回；证据并入同一峰值报告。原生queue-head六后继候选3至6线程提高，但7线程两轮明显回退，已撤回并归档。
后续复用现有采样时钟评估更平稳的竞争估计，不逐请求读时钟或增加远端链访问。
仅adaptive清理已完成基础/采样3组、runner32项及SELFTEST两种构建；比例0的nested/early
实际返回395570/99927次正文并排空。当前没有移除模式的单独性能归因。
禁用计时跳过两次helper的30场通过，合并adaptive-only后16/20线程约5.30Mops/s；
不能把两项之间的全部收益归因于计时调用。下一项评估已有512采样区间的冷准入下界，
随后独立测试spin waiter诊断使用per-CPU事件总数，owner/ACK和真正排空计数保持。
性能测量不能解释为全量功能通过。并发冷准备RCU stall、pinned mutex mode-4
soft lockup及其他真实限制保留在 [TODO](TODO.md#current-checkpoint)。

### 与 TCLock 的剩余差异

| 阶段 | KD保留的工作 | 不能删除的边界 |
| --- | --- | --- |
| 获取与排队 | CPU/锁频率、MCS/获取比例、上下文与翻译身份检查；稳定ticket及continuation | 准入、ABI/source有效性、KD自身排队协议 |
| 正文 | wrapper元数据、frame、虚拟SP/BP和地址重写、生成代码分派 | TCLock切换原生waiter栈，两者不是等量机器指令 |
| 完成与续跑 | 终态、复杂出口、owner ACK、pop/借用退休和最终恢复 | FULL、native后缀及远端请求不能当成最小COMPLETE |
| 观测 | 正文证据、精确waiter数和可选统计 | 不得近似排空/owner协议量或删除JIT witness |

## 2. P0：建立当前版本的可信基线

正式测量只比较Linux原生、TCLock与当前KD。默认每配置3轮，取有效最大吞吐及
同场ns/op，同时报告min/median/max/spread、KD/Linux、KD/TCLock及所有原始样本。
旧版成绩只作历史参照；当前配置或组件的诊断对照不能混为新增旧KD正式测量臂。

- [x] 完成此前默认壳MCS1/CPU400亿的完整三轮线程矩阵，以及元数据/布局优化的定向功能和独立长对照。
- [x] 此前MCS8/CPU400万组合完成[正式三方矩阵](../bench/tclock_compare/results/20260923-mcs8-cpu4m.md)：
  c1/c16、1/2/3/4/8/16/20线程各三轮，168/168通过并排空。8/20线程该批未见历史对照退化，
  3/4线程和单线程目标当时未完成；这是匹配旧源码的证据。
- [ ] 完成当前比例准入版本的匹配三轮矩阵，确认3/4线程改善及1/2/8/16/20线程性能保持，
  保留有效样本、原生/JIT覆盖和排空证据；诊断小矩阵不代替该验收。
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
不按线程数分流，也不测量完整委托收益。旧确认/冷却/保留状态机已按用户要求移除。
简化版本收益与高线程性能保持仍需匹配测量，通用net-cost模型仍未实现。

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

- [x] 此前试验spin单锁计数32→128/1024，固定当时的CPU和单锁时间窗口；
  两候选均未同时改善低线程并守住8/20线程，该轮结束时恢复32。
  [三轮诊断](../bench/tclock_compare/results/20260923-adaptive-threshold-sweep.md)
  表明减少单锁采时仍未消除3/4线程短代理批次；收益准入继续按P1.1评估。
- [x] 扩展到单锁窗口、CPU窗口和MCS间隔及成比例组合的
  [三轮诊断](../bench/tclock_compare/results/20260923-adaptive-windows.md)。减少MCS采时改善部分8线程成绩，
  过紧窗口损害20线程，低线程未一致改善；该轮结束时恢复原默认。
  用户随后指定的MCS8/CPU400万组合已形成独立历史矩阵；本轮起点及早期比例诊断使用
  MCS32/CPU400亿/lock1024阈值，当前采样与比较同为512次，不能沿用旧组合或早期候选的性能结论。
  窗口/间隔相互影响，不能仅按采时次数推定收益。
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
