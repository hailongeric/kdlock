# 性能优化任务

本页只维护当前状态、未完成任务和测量约束；操作见 [AGENTS](AGENTS.md)，
正确性与延期范围见 [TODO](TODO.md)，命令和成绩集中在
[三方运行器](../bench/tclock_compare/README.md)。已撤回候选的过程保留在结果报告与Git历史，
不再列为当前实现或重复的下一步任务。

## 1. 当前状态与证据边界

2026-10-03 继续[全线程集合与mutex执行成本优化](../bench/tclock_compare/results/20261003-mutex-followup.md)：
shared runtime独立筛选保留，1/2/16/36三方36场通过；16/36 KD峰值为同期TCLock的127.18%/106.51%，
1/2仍仅46.78%/62.86%。六组相关unit、三场spin实际JIT及真实mutex owner/ACK通过；
公共helper与FULL路径保留。随后精确per-CPU active/reserved余额独立18场及五组unit、owner/ACK通过，
16/36中位数比shared-runtime筛选提高2.81%/0.79%；36收益小于波动，保留精确排空而不宣称显著增益。有界mutex NUMA分组的27场业务/JIT/排空通过，但36线程中位数两次下降5.44%/7.76%，已保留分支并撤回。
OUTER原生CAS/配对路由独立36场通过，1/2/16/36峰值达到同期TCLock的90.82%/92.25%/194.04%/186.51%；
真实hash JIT与owner/ACK通过。此优化主要缩短原生路径，36线程JIT仅1.14%–1.40%，node1整段份额约44%。
随后cacheline完整15点135场全部通过；4–36线程全部12点峰值高于TCLock，36为8.324/4.640 Mops/s。
1/2/3仍落后，3线程只达78.57%，未实现全点追平；原90%阈值通过14/15点。所有KD中位数较上次完整矩阵提高，
24线程node1整段份额16.705%–17.390%，与4/24工作者比例接近。hash完整复验及小线程路径诊断另列。

2026-10-03 开始[mutex 新一轮优化](../bench/tclock_compare/results/20261003-mutex-optimization.md)：
默认UBSAN-off新基线及原生CAS先于计数pin的候选，共72场定向三方测试通过。
1/2/16/36线程KD中位数提高约10.19%/7.96%/5.73%/2.47%；36线程最高峰仍仅为同期TCLock的75.47%。
独立采样显示36线程约70.21%的worker cycles权重位于内核queued spinlock等待，
当前mutex只有约6%–8%操作委托。随后仅取消已发布shadow查找的全局锁、保留带锁插入，
16/36筛选及1/2/36复测45场通过：36中位数4.205/4.361，峰值为同期TCLock的91.55%/108.93%。
确定性交错测试覆盖重复键/碰撞插入；一个额外callchain诊断因stack-unwinder警告失败，
保留失败并经检查正常排空，之后普通复测通过。task空bucket快速否定虽改善1/2线程，36线程连续两组中位数下降
超过3%，已保留实验分支并撤回；当前保留原RCU查询。停用fault-injection的atomic读前检查亦连续两组下降超过3%，
已保留分支并撤回。native-pin与shadow读优化的完整cacheline135场全部通过，1/2/16/36中位数相对本轮基线提高
11.86%/13.17%/9.92%/28.39%；36峰值91.52%，但相同源码复测只有85.19%，仍未稳定达到目标。
独立task bucket锁候选通过真实owner/ACK检查和36场筛选/复测，却令JIT占比升至65%–97%而吞吐大幅下降，已保留并撤回。
其平面profile显示内核queued-spin等待降至不足0.04%，KD自身waiter等待占主导；单纯去除registry锁不足以优化完整委托路径。
恢复后的两项优化完成mutex/hash135场：130通过，7/12/32线程共5场NO_JIT失败均已排空并保留，不合入有效分数。
完整三轮且达到90%的点为6/8/16/20/24/28/36；36峰值119.91%，但整段中位数低于TCLock6.94%。
24线程hash少数node峰值份额最低0.424%，36最快样本单worker峰值仅256次，不能宣称公平或稳定追平。
最终29阶段归档核对527场benchmark/diagnostic及4组unit、4组JIT=0 owner/ACK，完整性检查零问题；失败状态未改写。

2026-09-28 完成[私有寄存器包与 continuation 重排](../bench/tclock_compare/results/20260928-packed-continuation.md)：
核心身份/状态与 RIP/RSP/RBP 共用第一条64字节行，虚拟GPR backing共用第二行，
默认MINIMAL frame/包提示由四条不同记录行减少到三条；168字节包和704字节记录不增长。
Linux pt_regs不变，生成物升级KDWB002/KDWC002并在NORMAL发布前拒绝旧布局。
新的UBSAN-off基线/定向/复测共141场性能通过，另有7场实际JIT功能、TCLock执行采样及真实owner ACK。
这不是吞吐提升：hash16/36复测中位数下降1.01%/2.03%，峰值仅为同期TCLock的83.55%/76.41%。
两线程首次c1下降4.69%，复测下降1.13%，未复现超过3%的保护点回退。保留此次结构合并及其代价；
90%竞争hash目标仍未完成，24线程少数node份额仅0.86%–1.99%。没有重跑完整15点矩阵。

2026-09-28 用户指定三方运行器的KD私有provider默认关闭UBSAN；spin/mutex共用
`--kd-provider-ubsan off`默认值，显式`kernel`仍可继承内核配置。普通provider构建及内核
保持原设置。此前成绩保留实际插桩政策，不因默认值变化重标历史样本或混合取优。
本次默认值修改已通过guest两个基础程序、44项运行器检查及不传UBSAN选项的36线程hash功能复验：
360万次操作中3595136次返回正文JIT，实际provider无UBSAN handler引用，业务/排空通过。
这是默认构建与功能验证；此前显式off的性能成绩仍为历史证据。归档见运行器说明。

2026-09-28 按用户要求完成[36线程 spin 专项复测与归因](../bench/tclock_compare/results/20260928-spin36-analysis.md)：
45 场性能与 30 场独立诊断全部通过。hash KD/TCLock 峰值为 1.985/2.648 Mops/s（74.96%），
单 cacheline 为 8.665/5.952（145.59%）；低吞吐依赖正文，不能泛化为所有 spin 工作负载。
hash 实际 JIT 约 99.9%。新采样定位生成正文和 request/frame 检查的额外工作；固定 16 人
跨 node 放置使两方中位数分别下降 47.24%/43.08%，单 node 仍有差距。KD provider UBSAN-off
只提高约 3.81% 中位数，未关闭差距。独立事件显示更多 instructions/L1 misses，却没有更高的
通用 cache-miss 总数；不以普通 cycles 样本宣称测得远端 load latency 或单条指令的确定耗时。
该次复测只新增证据与分析；上述UBSAN默认值调整发生在复测之后。

2026-09-28 按[NUMA/mutex 分阶段计划](../bench/tclock_compare/results/20260928-numa-mutex.md)
完成显式放置、独立单事件 PMU、终态 CALL/COMPLETE 融合、静态 GS/task 导入省略及预算提前检查。
完整 spin/hash 135 场通过；KD 只在 1、3–6 线程达到同期 TCLock 峰值的 90%，高线程仍有差距。
24 线程少数 node 仅约 2% 进度；有限 batch/scan 不代表公平保证。
独立三方 mutex cacheline 基线已完成全部 135 场，真实 KD JIT、TCLock 委托和 parking 均有证据。
native-first、本地栈/观测和专用 batch helper 已独立筛选保留。shadow/task cache、mutex NUMA
独立候选及其高 JIT 组合均有保护点重复回退，分支保留并排除；精确 per-CPU 余额实验虽改善
组合，但未单独合入。已接受版本继续使用 RCU task registry、原 shadow table 与 mutex FIFO；
spin NUMA grouping 不变。最终 cacheline 135 场与原 registry 的实际 owner/RCU ACK 检查通过；
仅 6/7/8/12/16/20 线程达到同期 TCLock 峰值的 90%，跨节点仍有差距。
mutex/hash 的 ratio256 全点 135 场已收集：129 场通过，6 场 NO_JIT 保留为失败；
7/8/12/16 线程没有完整三轮 JIT 验收，只有 6/20/24/28/32/36 同时满足三轮与 90% 目标。
ratio512 候选因重复 cacheline 回退已拒绝。24 线程 mutex/hash 的 KD 少数 node 整段份额仅
1.86%–2.32%。最终共享代码 spin/hash 1/16/36 三方 27 场回归通过，中位数变化均不足 1%；
16/36 峰值仍仅为 TCLock 的 80.72%/74.95%，不能宣称本轮已达到全部性能目标。
本阶段保留 pinned KD waiters；实验 task cache 最多保留 1024 个 task 记录至卸载。
不做 oversubscription 重设计、内核修改或 wrapper 输入 ABI 扩展，不重试已撤回的寄存器
驻留/广泛预取候选。

按用户2026-09-27的阶段安排，spin本轮以[135场收尾复测](../bench/tclock_compare/results/20260927-spin-checkpoint.md)
作为转入mutex前的c1基线，未再修改锁实现。KD在8–36线程全部已测点峰值高于TCLock，
相对前次相同实现变化在约±0.31%内；1/2线程仍低于Linux，2/7线程低于TCLock。
Linux28/32/36线程高值再次出现且计数/窗口审计通过，24线程KD的少数node进度占比仍约1%。
该矩阵保留为hash优化前的c1历史参照；用户随后要求继续优化hash正文，多线程目标仍未完成。

随后按用户要求新增hash连续计时并完成[三方135场hash比较](../bench/tclock_compare/results/20260927-hash-peak.md)。
固定2.5GHz、NUMA-on及相同预热/窗口设置下，KD在3–5线程领先两方，6–36线程各已测点低于TCLock；
8–36线程实际JIT占比99.5%–99.8%，不能将差距归为没有代理。锁实现与c1 checkpoint相同，
不同正文的成绩不能作为同负载实现回退。随后完成[hash优化分阶段测量](../bench/tclock_compare/results/20260927-hash-optimization.md)：
省去循环内witness写入、只读虚拟寄存器写回及常态预算RIP物化，扩大后继栈预取，并内联普通batch helper。
JIT精简单独没有一致吞吐收益；预取收益较小。显式UBSAN-off/批上限1024配置的完整135场中，
KD在8/16/36线程为3.416/3.390/1.869 Mops/s，约为同期TCLock的71%/72%/71%。
这包括构建插桩与批长变化，不能全部计作代码优化；当时生产默认仍为kernel插桩/512，2线程下降亦保留。
默认kernel/512的hash定向复测在16线程提升约3.16%，36线程约0.11%；不能把显式配置的收益归为默认实现收益。
一cacheline六个回归点峰值较历史下降约0.49%–5.66%，尚未实现不回退目标。
36线程nested/early默认比例2完成业务但测量阶段没有JIT；显式比例4的功能复测有实际JIT并排空。
完整分布、候选撤回、首次失败和证据以该报告为准，没有mutex live测试。

随后完成[跨层内联与解锁尾调用优化](../bench/tclock_compare/results/20260927-hash-runtime.md)：
将spin、dispatcher与frame层组合编译，移除combiner内五个逐请求外部helper调用和目录memcmp，
并让native clobber unlock通过内核module static-call尾调用调度。默认kernel/512完整135场通过；
相对上一版相同默认配置，16/36线程峰值提高12.47%/6.26%，中位数提高12.47%/5.98%。
1/2线程达到同期Linux峰值的94.8%/98.6%；hash多线程仍低于TCLock，目标尚未完成。
显式off/1024与c1回归另列，不能混入默认成绩。c1的16/20/36线程提高约30%–34%，
但8线程下降18.85%，平均batch仅9–13正文。随后加入[有界refill](../bench/tclock_compare/results/20260927-spin-refill.md)：
已启动批次的后继链接暂空时最多PAUSE/重读8次；已有NUMA远端暂存队列时直接交接，
保留native边界及原512上限。c1的8线程恢复到5.935–6.063 Mops/s、平均460–476正文/batch；
16/36线程较该内联检查点约下降1%，仍比hash优化前高约33%/29%。
最终默认hash的24线程中位数恢复到2.918，但未复现此前3.182的最高值；8–36线程为同期TCLock的65%–79%。
最终定向90场、nested/early及构建验收范围另见refill报告。
source/owner/ACK及准入顺序保持；
吞吐与静态指令证据不等于cache miss归因；后续flat-IP cycles采样也不是精确load-latency测量。

随后完成[36线程hash采样与批次调优](../bench/tclock_compare/results/20260927-hash36-profile.md)：
实际JIT已超过99%，单node仍存在KD/TCLock差距，不能全部归为NUMA或未代理。
增加批上限到1024，默认36线程三轮为1.964/1.969/1.974 Mops/s，较refill检查点峰值提高6.98%，
仍比同期TCLock最高值低约25%。虚拟寄存器跨块常驻候选无吞吐收益，已撤回。
24线程吞吐提高9.28%，但node1份额从约3.1%降到约2.0%；主矩阵2线程下降，
独立复核中位数恢复到历史水平；两次分开报告，不宣称全线程无回退或公平性保证。配置消融、定向回归与所有失败范围见该报告。

当前默认采用有界1024正文及独立1024扫描预算、六后继准入、producer预取及直接per-CPU热值。
此前在512上限下压缩continuation前缀以合并IP/SP缓存行、用带代际的原子状态替代ticket guard、
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

历史完整 c1 比较覆盖 1–8/12/16/20/24/28/32/36 线程；新1024默认仅定向复验8/16/36。
worker 顺序放置 CPU 0–35：
20 线程以内位于 node 0，24/28/32/36 跨 node 0/1；collector 使用 CPU 38。
保持固定 2.5 GHz、全部 worker 各预热 48000 次、正式 2 秒内最高 300 ms 窗口，
三方各三轮并保留整段吞吐。当前 KD 使用 NUMA-on、1024 次代理上限和独立的每 batch 1024 次NUMA
扫描预算，延期远端链在批次结束后优先交接；上限约束工作量，不是调度延迟或无饥饿证明。
TCLock 启用其原有 NUMA 路径，保留上游 1024 配置（普通WWJUMP可执行1025正文）；不同构建、策略或上限的样本不混合取优。

spin 使用显式单锁字 API、共享 continuation/frame、原生 pending/MCS 路径和统一 clobber 解锁。
冷获取首次 CAS 内联，简单 batch 单次初始化元数据。只保留 adaptive：per-CPU 获取/MCS
计数在MCS达到1024时直接右移比较并清零，原生队头在同一近似边界检查捕获队尾以内的六个后继；
准入不等待凑批，不新增逐请求时钟；已启动批次在后继链接暂空时最多PAUSE/重读8次。
空链接且已有NUMA远端暂存队列时直接交接；native边界及正文上限继续立即结束批次。完整参数与限制见
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
| 请求发布 | frame位于continuation偏移0；40字节核心头与IP/SP/BP填满首行，完整包为KD私有layout2；仅两个producer标签共用一字节 | 包/记录仍168/704字节，result仍32位；owner/ACK不压缩，几何不能当作cache miss次数 |
| NUMA选择 | 有界1024正文/独立1024扫描；连续延期链只改必要接点，远端前缀最后优先交接 | 先测批终止原因；继续放大上限可能损害少数节点进度 |
| 预取 | producer预先给地址；MINIMAL预取核心头/三字段续点、虚拟GPR backing及provenance共三行，另有SP-8及最多四个向上地址 | FULL/借用包范围及复杂ledger提示保留；更少提示没有带来本轮hash吞吐提升，远距离旧回退仍有效 |
| batch准入/lease | registry身份只读复用，发布状态逐请求读取，精确source lease按batch摊销；组合编译内联readiness、prepare/complete、bind/retire，目录改为精确整数比较 | 不复制共享包，不把生命周期计数改成近似统计 |
| JIT正文 | RIP常量折叠；callee复用公共SP发布；入口witness只写一次、预算DEC/JZ、块内只读GPR不写回 | 已验证静态省略与终态 CALL/COMPLETE 融合；未知需求保留导入，失败完整物化 CALL 一次 |
| wrapper完成 | 正常COMPLETE已经只回交IP/SP/BP；FULL处理复杂/中途出口 | 已知终态先检查等价 SP/IP/BP/锁/端点；其他路径保留 FULL 与真实续点 |
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
spin 的 TCLock 未观测代理计数，不能推算其批长；mutex 已记录委托及 parking。
原始快慢样本不因异常而删除；显式继续收集已排空 NO_JIT 不改变失败状态或评分资格。

## 3. P1：避免不划算的代理并降低原生入口成本

### P1.1 基于收益的新请求准入

当前在MCS达到1024时以`(spin_entries >> 10) < 2`判断比例，并清零两计数；
原生队头在物理获取前增加有界captured-tail资格，已代理队头不做该检查。
不按线程数分流，也不测量完整委托收益。旧确认/冷却/保留状态机已按用户要求移除。
本轮nested/early在默认比例2下只在预热出现JIT、测量阶段退为原生；内层无竞争获取会稀释per-CPU比例。
显式比例4的定向功能验证通过，但不是默认策略问题的修复，也不用于普通hash性能取优。
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
- [x] 简单 mutex batch 按批持有一个 source lease，保留逐请求 readiness、物理 owner ledger
  与最终 ACK；复杂 FULL 继续通用恢复。纯观测移至 per-CPU，已接受版本的生命周期余额仍精确且共享。
- [ ] 继续核对复杂出口的 ticket/source lease 消费者及重复读取；独立 per-CPU 精确余额实验只在
  未合入候选保留，不能以近似统计替代 owner/ACK 或真正排空。
- [ ] 用单锁与独立多锁分别检验布局、footprint和碰撞，不把每CPU缓存盲目放大。
- [ ] 按native/mixed负载测source-ready与native-list锁、source gate与冷写锁的同缓存行影响；
  plain c1没有native列表更新，不能将这些潜在false sharing当作其已测瓶颈。

位置：[diagnostics.inc](../kernel_module/spin/diagnostics.inc)、
[kd_spin_entry.c](../kernel_module/kd_spin_entry.c)、[kd_source.c](../kernel_module/kd_source.c)。
保留native peer排斥、node复用、frame退休及continuation最后读取约束。

### P2.2 wrapper、JIT分派与地址重写

- [x] 简单 spin batch 按 ABI 一次写最终元数据；普通 ABI2 MINIMAL mutex batch 使用专用
  prepare/complete/retire，其他 mutex 和复杂 FULL 保留通用 helper。
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
- [x] layout2使MINIMAL三字段与核心头共行，虚拟GPR backing与provenance各占一行；默认共三条frame/包提示，FULL范围与栈边界保留。
- [ ] 后续如调整距离/范围，按实际 cache-miss/生成代码测量定位；本轮已采集独立通用
  cache/L1 事件，但未测得具体 load 或远端延迟，不能用总数证明某次预取的因果收益。
  提示不能代替权威frame或生命周期引用。

位置：[prefetch.inc](../kernel_module/spin/prefetch.inc)。验收看完整吞吐和footprint。

## 5. P3：嵌套、mutex与更广负载

- [x] 完成 mutex 六类优化的实现与筛选：接受 native-first、node 本地栈/观测、专用 batch helper；
  无锁 shadow、1024 稳定 task records 和有界 NUMA grouping 因保护点重复回退保留于实验分支。
  cacheline 最终 135 场通过后完成 mutex/hash 135 场取样，后者 6 场 NO_JIT 未通过验收。
- [ ] 定位 mutex/hash 的竞争 JIT 覆盖缺口及仍未达到 90% 的配置；不重复合入已拒绝的 ratio512
  或高 JIT 组合，不以原生回退成绩替代要求实际 JIT 的正例。
- 已知七角色双CPU mutex的 oversubscription 可运行性问题不在本阶段范围内。
  published waiter 禁止抢占并 PAUSE 轮询仍是当前契约。
- [ ] 明确CPU放置后，再比较同/异队列嵌套、乱序释放、hostcall与native后缀；
  先保持一次副作用、原owner ACK和排空，再分析服务成本。
- [ ] 继续定位28线程20+8节点分布的短批与整段差距；先区分批上限、无后继及entry拒绝，
  不新增每请求时钟；修改上限或NUMA选择时同时检查少数节点进度。
- [ ] 诊断 24 线程 20+4 放置的服务偏斜：本轮 spin/hash 的 KD node1 整段份额约 2%，
  mutex/hash 为 1.86%–2.32%；
  1024正文/扫描上限及正进度不等于公平或最大等待时间保证，吞吐之外需保留worker分布。
- [ ] 按实际需求扩展多锁、正文长度、NUMA和公平性；单锁spin的TCLock结果不能
  推广为mutex或任意嵌套性能。

访问时guard、通用flags/特殊指令语义和不可变JIT版本仍明确延期，未重新纳入实施范围。

## 6. 实验选择与停止条件

下一项按复现问题或测得热点选择，先明确假设、当前对照、冻结输入和判据，不自动
执行整个清单。代码修改后可直接测性能；独立单元和live按受影响范围选择，默认不跑全量。
有效改动按独立可回退提交保存，不叠加未经验证的大改动。

数据错误、旧owner未ACK、未排空或已执行前缀重放时停止性能判定并保存证据。
CPU准备、覆盖或输入变化使配对失效；重复收益不稳定时保留原默认，不堆叠补丁掩盖回退。
