# 下一阶段性能优化任务

配对冷CPU快路径和公共调用精简已分步提交。按用户最终要求，cookie仅引用已有per-CPU
`rate_hot`，一个CPU一份、所有锁共享；解锁根据冷态锁字状态5，cookie不保存路径/深度。
[最终同期与PMU验证](../bench/tclock_compare/results/20260922-spin-cpu-hot-cookie.md)：36场性能、
8场功能、12场PMU通过并排空；c1/c16单线程改善，c1四线程observe下降7.04%，
20线程下降14.87%–18.64%。这些竞争退化仍待解决，因此新接口/选项继续显式启用。
单线程PMU显示指令与周期明显减少，但尚未对竞争退化作因果拆分。
不追加重复轮次掩盖退化；前两阶段局部cookie成绩只作历史。


当前继承 continuation、ticket 和无竞争入口优化：顶层 pending 复用 fast owner，
合并 claim/release guard，slowpath 返回不重复 claim；request/ref 准备延后到慢路径。
单锁字、本地哈希、原生 MCS 和 continuation 退休交接均保留。MCS 后置准入及
时间域迁移实验已撤回，当前恢复入口判断和批量时钟；关闭代理的公共入口跳过记录。
锁协议见 [locking](design/locking.md)，现场存储见 [frames](design/frames.md)，
对象大小、创建位置及 TCLock/KD 数据流见 [执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md)。
当前协议以链接的 locking 章节为准，旧 hook 性能入口已删除。

此前 [四线程 ticket 前后对照](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-four-thread-ticket.md)
记录该阶段定向优化，c1/c16 四线程提升 9.4%/14.0%，仍低于 TCLock。
[MCS 准入实验](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-admission.md)曾改善单线程，
但竞争性能回退。[后续调查](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md)
同期复现回退，两个候选未恢复到旧版 95%，因此按用户授权恢复旧版路径。
四线程相对 TCLock 的差距与具体指令级根因仍未解决。
本清单保留性能实验顺序及剩余任务，2026-09-20 的完整三方基线以
[continuation 三方报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-continuation.md)为准。历史证据不自动成为当前版本的验收。总体正确性事项和明确延期项目仍在
[TODO](TODO.md)，这里统一维护性能实验的顺序、修改范围和验收条件。
源码位置查 [CODE_MAP](CODE_MAP.md)，具体执行步骤及 TCLock 对照查
[EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。

## 1. 现状与证据边界

当前普通 spin/mutex 已使用 caller-clobber：入口和正常完成只传 RIP/RSP/RBP，
中途退出才物化 FULL 包。PT/Stack 共用寄存器区、批内 C 循环、预备预取提示、
请求热字段集中和 spin node 通知分行均已实现；旧 gate 已删除。这些不再列为
待做的“消除重复保存”任务。continuation 栈、根包共享及 native ticket 退休也已实现，
不再扫描 request 空闲引用或维护 users/packet_owner。legacy/FULL、独立 owner、
source lease、物理 ACK 和 executor pop 后的借用释放仍有用途。

当前已实现单锁字及分类型 CPU 本地哈希，协议与准入的唯一说明在
[locking](design/locking.md)。原 gate/S、Linux L 二次获取、站点缓存和全局晋升集合
均已删除。当前热表直接按完整锁地址哈希计数，每 CPU/type 256 桶、256 记录。
spin CPU 每 4 次实际 MCS 入队检查一次，mutex CPU 保持每 1024 次入口检查，
两者共用 40 亿 TSC 窗口；fast/pending 不增加 spin CPU 计数。热 CPU 才查表，spin/mutex 单锁 count 大于 32
（33 次）检查 25 亿 TSC 窗口。删除候选分数和淘汰，满表不覆盖。
query 不采时。当前预分配空间每 CPU 13376 字节，锁路径不分配。
统计识别频率，尚不判断代理净收益；本轮不以操作减少推断性能已提高。

2026-09-22 对热表简化造成的高竞争退化做了隔离测试，当时恢复最佳已测采样器；
不撤销普通 spin IRQ 语义和 wrapper 栈修复。数据与限制见
[回归处理](../bench/tclock_compare/results/20260922-performance-recovery.md)。
后续按用户指定改为spin CPU每32次实际MCS入队检查，入口及单锁规则保留。
[本轮单轮三方检查](../bench/tclock_compare/results/20260922-spin-mcs32.md)显示20线程
c1/c16相对最近基线下降20.8%/18.4%；本次未进一步调整协议或自动回退。
随后按用户确认合并CPU MCS阈值1、单锁阈值32及删除统计busy/barrier，非task样本丢弃。
[合并单轮结果](../bench/tclock_compare/results/20260922-spin-mcs1-lock32.md)的20线程c1/c16
为5.011/4.802 Mops/s，较MCS32版本提高27.3%/23.7%，本轮恢复到下降前水平；
两组改动的贡献未拆分，单轮结果不证明稳定收益。
当前MCS4/40亿CPU窗口的[完整单轮bench](../bench/tclock_compare/results/20260922-spin-mcs4-full-benchmark.md)
30/30场通过；20线程c1/c16为5.009/4.768 Mops/s，与上一轮接近，c1单线程下降10.16%。
保留原始样本，本轮未追加重复测量或性能归因。
单锁字阶段结果保留在 [历史报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-singleword.md)；
此前 `644f231` 三方矩阵 150/150 通过，40/40 竞争 KD 有实际 JIT，仍存在低竞争差距。
该 continuation 矩阵没有同期旧版 KD 对照，不将历史差异单独归因于存储改造；
2026-09-21 ticket 优化另有同期修改前后对照。

前序 [直接哈希对照](../bench/tclock_compare/results/20260921-hotlock-direct.md) 120/120 场通过，
adaptive 四线程/二十线程近似持平；删除候选没有表现为整体提速。
此前 [两级候选采样对照](../bench/tclock_compare/results/20260921-hotlock-twolevel.md) 中，adaptive
二十线程受益于更早变热，但单线程回退、四线程无明确收益；observe 高竞争近似持平。
更低阈值没有解决低竞争代理净收益问题。

| 已有证据 | 可以说明什么 | 不能据此说明什么 |
| --- | --- | --- |
| [本地发现组件对照](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/hotlock_record/results/20260919-local-discovery.md) | 冷地址及正向命中的 record 组件成本下降；每 CPU 独立发现也增加总准备工作 | 当前完整 lock/body/unlock 的收益、稳态 JIT ≥99% |
| [1/4/8/16/20 线程三方数据](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260919-thread-scaling.md) | 当时版本的扩展趋势；4 线程短批次和高线程长批次的差别 | 后续布局及本地发现版本的当前成绩 |
| [缓存行隔离配对](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/spin_cacheline/results/20260919-cacheline-isolation.md) | 当时 kdlock 的 20 线程改善及 4 线程回退 | node 与 gate 各自的贡献，或独立多锁的 gate 干扰 |
| 历史 IP 采样及源码依赖链 | 指出需要测量的候选热点 | 精确的缓存转移数、单独 wrapper 成本或因果归因 |

### 与 TCLock 的剩余差异

| 阶段 | kdlock 保留的额外工作 | 优化约束 |
| --- | --- | --- |
| 获取入口 | 代理开启时入口频率记录/上下文筛选；queue 分支检查翻译身份 | 不能跳过冷却、新旧 ABI 或 source 状态 |
| 排队 | 单 KD 字、稳定 ticket 与 continuation 槽 | KD 对象只能使用 KD 协议；Linux peer 使用独立 Linux 对象 |
| 每个正文 | wrapper 元数据、frame、虚拟 SP/BP/地址重写、生成代码分派 | TCLock 直接切 waiter 原生栈；两者并非等量机器指令 |
| 完成与续跑 | 终态核对、复杂出口、owner ACK、执行者 pop/借用退休及最终恢复后回收 | 普通 COMPLETE 已有专门路径，不能把复杂出口也当精简完成 |
| 观测 | 正文证据、精确 waiter 数和可选统计 | 统计可近似，影响排空/owner 的协议量不能随意近似 |

## 2. P0：建立当前版本的可信基线

2026-09-21 用户确定：后续性能对象固定为 Linux 原生、TCLock 和当前 kdlock，
不再运行旧版 kdlock 对照。旧版 O/N 和回退实验仅保留历史结论；下文尚未执行的
诊断配对限于当前实现的配置或组件，不增加旧版本测量臂。正式结果使用三方
相同负载、CPU 放置；2026-09-22 用户最新要求每配置一轮，使用各后端这一次
有效会话的吞吐，报告 KD/Linux、KD/TCLock。代码修改后可直接运行性能测试，
保留运行器内置的业务、JIT 和排空检查；独立功能测试按需选择。
既有旧版成绩不能充当当前 Linux/TCLock 的同期数据，历史两轮成绩保留原口径。

- [x] **P0.0 处理 MCS 准入调整的竞争回退。** 已冻结 A/B/C、完成独立周期采样，
  比较读锁字避失败 CAS 与 observe 去重复查询两个候选；两者均未恢复，按用户授权
  回退到包含 ticket 优化的 A。性能及功能证据见 [调查报告](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260921-mcs-recovery.md)。
  未关闭 JIT、删除统计或退休检查；未证明某一指令或缓存转移是唯一根因。
  若重启 MCS 后置准入实验，需用 Linux/TCLock 与修改后的当前 KD 重新测量，不能直接恢复已失败版本。

- [ ] **P0.1 诊断已知并发冷准备故障。** 保留 c16/t4/clobber 准备阶段的
  [RCU stall 记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md#失败记录与边界)，
  先以受控、可恢复的定向用例定位是否发生在发现、发布或队列依赖阶段。
  当前本地发现版本是否仍复现需要实测；没有复现不等于已证明旧根因修复。
  单 CPU 48000 次准备是已有稳态测量策略，不是修复。
- [ ] **P0.2 分开测冷启动与稳态。** 当前 benchmark 单 CPU 准备能发布 entry，
  不能使其他 CPU 自动满足本地频率。先明确每条测量臂的准备过程；若增加每 CPU
  真实空临界区准备，应放在计时外，单列成本，核对目标正文没有被提前执行。
  不通过写 hot 表、伪造计数或放宽正文证据取得高 JIT 比例。
- [x] **P0.3 当前 observe 三方基线。** 2026-09-22 回退后的 60 场完成，见
  [最新三方结果](../bench/tclock_compare/results/20260922-performance-recovery.md)。
  同一 kdclobber2、固定 guest/host CPU 映射、编译设置与负载下比较 Linux / TCLock / KD，
  覆盖 1/4/8/16/20 线程 × 1/16 cacheline，每配置两轮、各取有效最大值。
  5880 万次操作全部通过并排空，16/16 竞争 KD 有实际 JIT；单/四线程仍低于 TCLock。
  adaptive 仅做实际 JIT 功能检查，没有当前完整 adaptive 性能矩阵。
- [x] **P0.4 处理热表简化的高竞争退化。** 隔离实验支持局部恢复最佳已测采样器，
  无 busy、共享表和直接映射三项改动已撤回，普通 spin IRQ 与 wrapper 修复保留。
  具体微架构原因仍未证实，不能将回退收益归因于某一条 busy 指令。

交付：冻结源码/二进制/内核身份、逐会话数据、完整操作 Mops/s 和 ns/op、实际
JIT 比例、准备时间及失败记录；单轮不估计轮间波动，批长仅在确有观测时报告。
当前 TCLock 无执行计数，不能推算代理量或批长。按相同统计口径比较各后端单次有效吞吐，保留
原始样本与会话身份；NO_JIT 仍记录成本，但不算代理通过。实际 JIT、完整数据、owner
ACK 和排空任何一项失败，该会话不得进入性能通过集合。

## 3. P1：避免不划算的代理，并降低原生入口成本

已完成不代理请求的共用 MCS 队列及普通 fast-owner 解锁：冷锁/拒绝不再默认
循环 CAS，无需 JIT request/frame；实际节点耗尽仍保留先读后 CAS。
这解决原生排队机制，收益驱动的代理选择仍未实现。小范围前后比较见
[不代理 MCS](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-native-mcs.md)。


2026-09-21 已完成顶层 pending 免 ticket、合并 claim/release guard 及去除队首
返回后的重复 claim；普通队首自执行 ticket guard 从 7 次降到 4 次。
实测四线程每批仍约 2 个正文，JIT 占比下降而吞吐上升；收益准入策略仍未实现。

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

当前三方单线程 PMU 与 KD off 配置诊断已完成，见
[profiling](../bench/tclock_compare/results/20260921-single-thread-profile.md)：c1 指令/op
约为 Linux 50、TCLock 56、KD 344，KD off 160。查询、热表和 fast 路径局部准备
是后续精简重点；三方均只配对一次抢占 pin，不能删除 KD API 自己的保护。
本轮已将 request/ref 局部准备移入独立慢路径、合并执行 context 查询，并对热表
固定操作类型做编译期展开。[验证报告](../bench/tclock_compare/results/20260921-fast-path-optimization.md)
包含五组功能、150 场三方和 12 场 PMU：c1 相较此前诊断约少 15.9% 指令、17.4%
周期，但本轮单/四线程吞吐仍低于 TCLock。仍未将 caller spill、单个 helper 或热表成本做独立
因果拆分，以下细分任务保持未完成。

- [ ] 先做单线程 native 调用边界配对，核对反汇编中的活跃值 spill/reload、
  SP/BP 和续点；使用当前显式 API 设计配对，旧 hook dispatch-floor 已删除。
- [ ] 在相同 frozen build 对照 cold、local-positive、碰撞地址流和每批检查点。
  测已有 pin 的复用、精确地址碰撞链和 CPU 窗口重置，区分均摊成本和周期峰值。
  无 busy、共享表和直接映射实验已因竞争退化回退；功能通过不代表性能改善。
  后续若重新简化，必须对照当前已测版本验证完整操作吞吐和实际 JIT。
- [x] 删除已停用站点缓存；该参数对照已不适用于当前直接 API。

位置：[kd_hotlock.c](../kernel_module/kd_hotlock.c)、[kd_lock.c](../kernel_module/kd_lock.c)、
[当前三方入口](../bench/tclock_compare/README.md)。旧/新采样器组件工具已删除；验收以完整操作为主，
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
排空、node 复用、frame 退休与 continuation 最后读取约束；删除原子本身不是成绩。

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

当前 observe 基线已完成；下一轮先厘清 P0 尚未完成的冷启动/自适应准备口径，
再做 P1.2 成本拆分及 P1.1 的
有界准入实验；随后按实际热点选择 P2 的一个任务，最后扩展 P3。
每个实验只改变一个可解释因素，记录假设、开关、冻结输入、配对数据和结论。
先运行基础及直接相关验证，需要 live 时只选受影响协议，不默认跑全量。

出现数据错误、旧 owner 未 ACK、未排空或已执行前缀重放，立即停止性能判定并
保留故障证据。覆盖变化或 CPU 准备不同使配对失效；收益在重复运行中不稳定，
保留原默认并报告未证实，不继续堆叠补丁掩盖回退。

历史[联合测量](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260920-local-hash.md)已完成单字、记录器及策略分阶段比较；adaptive 在本负载回退，收益选择和滞回仍未实现。
