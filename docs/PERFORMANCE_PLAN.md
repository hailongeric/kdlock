# 性能优化任务

本页只维护当前状态、未完成任务和测量约束；操作见 [AGENTS](AGENTS.md)，
正确性与延期范围见 [TODO](TODO.md)，命令和成绩集中在
[三方运行器](../bench/tclock_compare/README.md)。已撤回候选的过程保留在结果报告与Git历史，
不再列为当前实现或重复的下一步任务。

## 1. 当前状态与证据边界

当前采用有界512正文及独立512扫描预算、六后继准入、minimal IP预取、直接per-CPU热值。
此前在此基础上压缩continuation前缀以合并IP/SP缓存行、用带代际的原子状态替代ticket guard、
折叠JIT的RIP常量地址，并定向调整低竞争解锁布局；见[全链路报告](../bench/tclock_compare/results/20260927-flow.md)。
采样策略、预取距离、owner/ACK及批次边界保持不变。此前维护删除单锁字迁移后遗留的
恒等包装和未使用宏，精简失败返回赋值，并显式内联ticket叶子校验；
[维护验证](../bench/tclock_compare/results/20260926-cleanup.md)包括基础/相关5组、两种构建、81场定向比较和36线程nested/early；
最高KD峰值较前次共有点变化-0.11%至+0.94%，不作为新性能收益或全线程无回退证明。

当前比例统计使用MCS1024触发的右移/清零窗口（默认`spin_entry_ratio_limit=2`），单锁热度仍独立采样512次。
已完成五组共144场定向比较、相关验证及最终15线程点三方135场，见
[窗口调优](../bench/tclock_compare/results/20260927-ratio-window.md)。
最终KD在8/12/16/20/24/28/32/36线程峰值均高于TCLock；8/16/20线程相对
[前次完整矩阵](../bench/tclock_compare/results/20260927-followup.md)峰值变化均在0.4%以内。
1线程仍比Linux低约5%，7线程仍低于TCLock；3线程虽高于同期Linux，但峰值较前次低约5.5%，
三轮范围不重叠，不能宣布全线程无回退或都归为波动。
Linux本轮28线程一轮峰值12.834、整段11.054 Mops/s，另外两轮峰值约3.6；32/36未复现高峰。
全部快慢样本保留，计数/窗口一致并不确定高吞吐原因。
原子ticket选型与旧guard参照见[全链路矩阵](../bench/tclock_compare/results/20260927-flow.md)。
用热度阈值替代六后继检查的五候选111场定向实验均未同时保持小线程和多线程性能，
已恢复原策略；见[实验结论](../bench/tclock_compare/results/20260927-heat-thresholds.md)。
提高单锁采样数只延迟晋升；短批CPU冷却会扰动代理群，CPU采样耗时下限也不能稳定区分低线程慢代理。
这些结果不证明所有替代策略都不可行，当前没有保留候选阈值、反馈状态或新增采样。
512选型、撤回候选及早期功能证据统一见[跨node报告](../bench/tclock_compare/results/20260926-cross-node.md)。

当前 c1 比较覆盖 1–8/12/16/20/24/28/32/36 线程，worker 顺序放置 CPU 0–35：
20 线程以内位于 node 0，24/28/32/36 跨 node 0/1；collector 使用 CPU 38。
保持固定 2.5 GHz、全部 worker 各预热 48000 次、正式 2 秒内最高 300 ms 窗口，
三方各三轮并保留整段吞吐。KD 使用 NUMA-on、512 次代理上限和独立的每 batch 512 次NUMA
扫描预算，延期远端链在批次结束后优先交接；上限约束工作量，不是调度延迟或无饥饿证明。
TCLock 启用其原有 NUMA 路径，保留上游 1024 配置（普通WWJUMP可执行1025正文）；不同构建、策略或上限的样本不混合取优。

spin 使用显式单锁字 API、共享 continuation/frame、原生 pending/MCS 路径和统一 clobber 解锁。
冷获取首次 CAS 内联，简单 batch 单次初始化元数据。只保留 adaptive：per-CPU 获取/MCS
计数在MCS达到1024时直接右移比较并清零，原生队头在同一近似边界检查捕获队尾以内的六个后继；
不等待凑批，不新增逐请求时钟。完整参数与限制见
[执行流](JIT_EXECUTION.md#21-热度与角色)。spin waiter 诊断使用 per-CPU 事件总数，
live 聚合近似，独立排空后余额精确；owner/ACK 及真正生命周期计数保持不变。

全部历史测量及失败候选从[benchmark结果索引](../bench/tclock_compare/README.md#本次结果)进入，
本页不重复版本成绩表。不能混合不同阶段取优，最好值不是每轮保证，三轮范围不是统计等价证明。
目标仍是c1少线程尽量不低于Linux，多线程尽量达到或超过TCLock。
并发冷准备RCU stall、pinned mutex mode-4及延期的协议范围见[TODO](TODO.md#current-checkpoint)。

### 与 TCLock 的剩余差异

| 阶段 | KD保留的工作 | 不能删除的边界 |
| --- | --- | --- |
| 获取与排队 | CPU/锁频率、MCS/获取比例、上下文与翻译身份检查；稳定ticket及continuation | 准入、ABI/source有效性、KD自身排队协议 |
| 正文 | wrapper元数据、frame、虚拟SP/BP和地址重写、生成代码分派 | TCLock切换原生waiter栈，两者不是等量机器指令 |
| 完成与续跑 | 终态、复杂出口、owner ACK、pop/借用退休和最终恢复 | FULL、native后缀及远端请求不能当成最小COMPLETE |
| 观测 | 正文证据、近似live waiter聚合、排空后精确余额和可选统计 | 不得近似排空/owner协议量或删除JIT witness |

### 2026-09-27：全链路访存与指令审查

NUMA-on继续作为provider和比较运行器默认值。优化优先级按实际写入、所有权迁移、
依赖加载及生成指令判断，不把所有全局读取都当成远端DRAM访问。

| 阶段 | 当前成本与本轮处理 | 仍可优化的方向 |
| --- | --- | --- |
| 入口/热度 | CPU本地获取/MCS计数，1024次MCS边界采时，单锁独立512次；冷CAS内联，无每次全局热计数 | 多锁碰撞或阶段变化需要独立负载；不新增每次时钟 |
| 原生pending/MCS | 真实锁字CAS/tail交换和后继release；这是排他/排队成本 | 不能通过删除锁原子或抢占配对降低成绩 |
| ticket | 删除私有guard，代际/状态/kind/借用数共用一个64位CAS字；分配release发布，等待acquire读 | 后续可测独占OWNED/RELEASED转换的store化；当前保留完整CAS，避免混合优化 |
| 请求发布 | continuation内result保留32位，内部kind压为字节并重排；frame从32移到24，MINIMAL IP/SP共行 | 记录仍704字节；这是五行变四行的几何，不是已测cache miss次数 |
| NUMA选择 | 有界512正文/独立512扫描；连续延期链只改必要接点，远端前缀最后优先交接 | 先测批终止原因；继续放大上限可能损害少数节点进度 |
| 预取 | producer预先给地址，在前一正文之前预取后继frame/寄存器/栈；MINIMAL IP/SP共行只发一次hint | FULL/借用包的尾部partial line可单独评估；远距离预取旧回退仍有效 |
| batch准入/lease | registry身份只读复用，发布状态逐请求读取，精确source lease按batch摊销 | 不复制共享包，不把生命周期计数改成近似统计 |
| JIT正文 | 翻译时折叠RIP常量地址；callee跳板去掉重复SP存储，由公共出口统一发布 | 未使用GS/task槽的静态省略；terminal CALL融合需独立验证 |
| wrapper完成 | 正常COMPLETE已经只回交IP/SP/BP；FULL处理复杂/中途出口 | 去掉虚拟CALL栈写需保持真实续点及FULL契约，不是直接删保存指令 |
| 退休/通知 | 先pop/退休，再release唤醒；队列头和轮询行分离 | 原owner ACK、最后一次packet读取和节点复用顺序保持不变 |
| 嵌套/原生后缀 | 通用dispatcher删除冗余MFENCE，完成/native/ACK/status各自发布；native路由表仍有共享锁 | 可复用本地native-root避开无关全局查询，先读注入开关再CAS；普通c1 batch不经过通用dispatcher |

普通c1生成代码没有KD新增的MFENCE/LFENCE/SFENCE。x86的`barrier()`、普通
`smp_rmb/wmb()`及这里的acquire/release通常只是编译顺序或MOV；删除它们不等于省掉硬件栅栏。
真正的locked操作包括锁字仲裁、ticket状态CAS以及batch lease。`run_combiner`的显式
`smp_mb()`位于拒绝交接分支，不是每个代理正文的成本。本轮保留所有发布/ACK顺序，
不新增访问时安全检查，不把统计近似原则套用到存储存活协议。

后续复查确认队列的`rsp == 0xdeadbeef`已无生产写入，非代理节点统一使用socket标记；
删除该额外读取/比较，保留真实rsp字段及TCLock自身协议。batch两次per-CPU统计共享短期
本地base指针，避免重复读取全局指针；仍使用GS相对更新，不增加`this_cpu_ptr()`地址计算。
这些静态减少不等同于测到更少远端cache miss，验证与成绩见[后续报告](../bench/tclock_compare/results/20260927-followup.md)。

反汇编确认consumer prefetch、batch准备、寄存器访问和小型队列判断已经内联，
不再机械添加属性。producer `kd_spin_prepare_prefetch()`仍有独立调用和保存现场，
可单独测试强制内联；必须同时检查调用者spill/代码大小，不改显式栈切换边界。
FULL按`regs+0/64/128`预取可能漏掉未对齐包的尾行；inline包主要是SS，通用借用位置还可能含SP。
这是缓存覆盖方向而非正确性错误，是否补hint取决于相关负载，不能盲目加宽所有请求。

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

当前在MCS达到1024时以`(spin_entries >> 10) < 2`判断比例，并清零两计数；
原生队头在物理获取前增加有界captured-tail资格，已代理队头不做该检查。
不按线程数分流，也不测量完整委托收益。旧确认/冷却/保留状态机已按用户要求移除。
当前c1矩阵已覆盖右移/清零策略，旧百分比矩阵只作历史参照；通用net-cost模型仍未实现。
多锁、不同正文及阶段变化不能由历史矩阵推断。

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
- [ ] 单独评估clobber unlock入口/快路径对齐：本轮代码精简让不变的release MOV
  移到text偏移模64为63处。先核对实际位置再测，不把静态跨行直接认定为已测瓶颈。

以完整操作吞吐为验收；组件ns/call或指令数下降只能解释候选，不能替代实际JIT覆盖。

## 4. P2：减少逐请求同步和生成代码成本

### P2.1 共享数据与布局

- [x] continuation在已有低12 KiB区域内错位；原始基址释放、全部槽位和局部初始化回滚已验证。
- [x] 压缩内部kind而保留32位result；MINIMAL IP/SP合并到同一行，记录步长与分配容量不变。
- [x] 删除ticket私有raw spinlock与临时抢占pin，remote借用只操作一个带代际的原子字；
  最后put发布frame退休，原waiter只读等待，保留原有request pin和真实ACK契约。
- [ ] 若继续定位缓存原因，独立控制代码地址与数据放置；先核对guest PMU能力，
  没有硬件事件时只报告地址几何模型，不宣称测到cache-to-cache或L1 miss因果。
- [x] 核对spin waiter_count消费者，保留发布/退出钩子，以per-CPU事件总数替换逐请求共享写；
  基础及batch/storage四组、独立30场通过，性能分布与即时下溢信号限制已记录。
- [ ] 继续核对ticket引用及source lease消费者，再评估按批持有、所有权转移和重复读取。
  owner/ACK及真正排空计数保持精确；spin诊断修改不推广到mutex计数。
- [ ] 用单锁与独立多锁分别检验布局、footprint和碰撞，不把每CPU缓存盲目放大。
- [ ] 按native/mixed负载测source-ready与native-list锁、source gate与冷写锁的同缓存行影响；
  plain c1没有native列表更新，不能将这些潜在false sharing当作其已测瓶颈。

位置：[diagnostics.inc](../kernel_module/spin/diagnostics.inc)、
[kd_spin_entry.c](../kernel_module/kd_spin_entry.c)、[kd_source.c](../kernel_module/kd_source.c)。
保留native peer排斥、node复用、frame退休及continuation最后读取约束。

### P2.2 wrapper、JIT分派与地址重写

- [x] 简单spin batch按ABI一次写最终元数据；通用helper仍处理mutex/复杂路径。
- [x] 按实际生成代码折叠普通RIP常量地址，c1块减少3条指令/22字节；不增加运行时guard。
- [x] 删除callee出口重复SP存储；[定向复测](../bench/tclock_compare/results/20260927-followup.md)18场及36线程nested原生续跑通过，吞吐未见明确提升。
- [ ] 继续核对scratch spill和虚拟CALL栈操作；仅在身份、
  准入与有效期可证明一致时复用状态。FULL、hostcall与远端处理保留独立出口。
- [x] 相邻batch_entries/ww_jumps复用短期本地诊断指针，保留两次GS相对per-CPU更新；匹配ELF与成绩见后续报告。
- [ ] 测量观察层成本，默认 `jit_timing=0`，采样与正式吞吐分开；inclusive timer
  可能重叠，不能相加为纯CPU成本。生成指令变化要验证真实生成代码及对应边界。

位置：[wrapper.S](../include/wrapper.S)、[wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc)、
[frame_lifecycle.inc](../kernel_module/execution/frame_lifecycle.inc)、
[special_inst.py](../disassem/special_inst.py)、[normal.py](../disassem/normal.py)。

### P2.3 预取

- [x] 同一可执行代码比较0与2；关闭预取明显下降，保留producer提示2。
- [x] 测试首请求+两请求完整预取，以及更远队列头分级预取；前者高竞争下降，
  后者跨NUMA略升但16/20下降约2%，均撤回并归档。当前仍在正文前预取下一请求。
- [x] 默认producer MINIMAL只预取BP/IP，利用已断言的IP/SP共行；FULL和consumer模式保持原范围。
- [ ] 后续如调整距离/范围，按实际cache-miss/生成代码测量定位；本轮未采集硬件miss。
  提示不能代替权威frame或生命周期引用。

位置：[prefetch.inc](../kernel_module/spin/prefetch.inc)。验收看完整吞吐和footprint。

## 5. P3：嵌套、mutex与更广负载

- [ ] 先诊断已知七角色双CPU mutex的可运行性依赖。published waiter禁止抢占并
  PAUSE轮询是当前契约，不能悄悄恢复旧睡眠等待来取得通过。
- [ ] 明确CPU放置后，再比较同/异队列嵌套、乱序释放、hostcall与native后缀；
  先保持一次副作用、原owner ACK和排空，再分析服务成本。
- [ ] 继续定位28线程20+8节点分布的短批与整段差距；先区分批上限、无后继及entry拒绝，
  不新增每请求时钟；修改上限或NUMA选择时同时检查少数节点进度。
- [ ] 诊断24线程20+4放置的服务偏斜：本轮KD三轮node1整段份额仅1.10%–1.25%；
  512正文/扫描上限及正进度不等于公平或最大等待时间保证，吞吐之外需保留worker分布。
- [ ] 按实际需求扩展多锁、正文长度、NUMA和公平性；单锁spin的TCLock结果不能
  推广为mutex或任意嵌套性能。

访问时guard、通用flags/特殊指令语义和不可变JIT版本仍明确延期，未重新纳入实施范围。

## 6. 实验选择与停止条件

下一项按复现问题或测得热点选择，先明确假设、当前对照、冻结输入和判据，不自动
执行整个清单。代码修改后可直接测性能；独立单元和live按受影响范围选择，默认不跑全量。
有效改动按独立可回退提交保存，不叠加未经验证的大改动。

数据错误、旧owner未ACK、未排空或已执行前缀重放时停止性能判定并保存证据。
CPU准备、覆盖或输入变化使配对失效；重复收益不稳定时保留原默认，不堆叠补丁掩盖回退。
