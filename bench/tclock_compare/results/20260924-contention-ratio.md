# 2026-09-24：低竞争比例准入调查（EXPERIMENTAL检查点，性能验收未完成）

目标是改善3/4线程短代理批次，同时保持1/2/8/16/20线程性能。**目标尚未完成。** 简化政策已保存为EXPERIMENTAL检查点`36512ed`；随后独立的节点数组128字节对齐在16/20线程相对simple512恢复约8%–9%，但c16/8中位仍低于原基线9.42%，c16/1低2.68%。两阶段各42场正确排空，均不能记为完整性能保护通过。旧检查点`b83f551`、所有失败候选及原始快慢样本继续保留；目录名`final`不代表通过。

节点数组对齐已独立提交为`f320d9f`。后续冷原生快速成功不计数候选未取得一致收益，已决定拒绝，运行输入在下一项独立实验前恢复到f320d9f。候选省略首次CAS成功，失败仍在pending/MCS前记录，使用独立标识`mcs_entry_ratio512_cold_failed`；该标识只保留在归档源码和结果中，不混入恢复后的`mcs_entry_ratio512_simple`成绩。

## 本地busy保护与已pin入口专化（当前实验检查点）

恢复f320d9f后，`local-access-fixed`只将CPU本地热表的busy保护改为普通读写/编译器屏障，并让已pin的spin记录入口跳过通用抢占判断。比例、入口计数范围、512次节奏、16字节快照和1024正文批次上限保持，策略仍为`mcs_entry_ratio512_simple`。冷CAS成功不计数候选已经撤回，其成绩单列如下。

42/42场、32400000操作正确并排空；30场实际JIT、26331389次正文。**仍未通过全部性能保护**：对before-fixed，c16/8中位/最大低8.21%/10.34%，c1/20低1.40%/1.49%，c16/20低1.88%/1.70%。c16/20三轮为4.706/4.670/4.382Mops/s，全部保留。相对紧邻node-pair128，c16/8中位提高1.34%但最大低0.96%，不能据此宣称问题解决。当前只完成KD adaptive42场，未运行该版本完整三方168场、nested/early或全量功能。

以下比较不包含被拒绝的冷计数候选；最大值和ns/op来自同一会话。[对before的全部三轮/min/median/max/spread](../../.tmp/ratio-20260924/local-access-comparison.txt)、[对node的完整比较](../../.tmp/ratio-20260924/local-access-vs-node-comparison.txt)、[records](../../.tmp/ratio-20260924/local-access-fixed/records.json)及[summary](../../.tmp/ratio-20260924/local-access-fixed/summary.json)保留全部精度。

| c/t | 中位 / 最大 Mops/s | spread % | 最佳ns/op | 对before中位 / 最大 % | 对node中位 / 最大 % |
| --- | --- | ---: | ---: | --- | --- |
| 1/1 | 31.370 / 31.565 | 2.48 | 31.68 | -0.14 / +0.00 | -0.67 / -0.06 |
| 1/2 | 2.155 / 2.159 | 6.53 | 463.14 | +4.92 / -10.40 | +5.23 / -2.79 |
| 1/3 | 2.127 / 2.200 | 3.83 | 454.49 | +34.50 / +37.65 | +0.55 / +0.93 |
| 1/4 | 2.438 / 2.502 | 6.54 | 399.66 | +24.63 / +25.89 | +1.75 / +4.03 |
| 1/8 | 3.984 / 4.226 | 6.94 | 236.65 | +7.68 / +13.43 | +0.30 / +5.26 |
| 1/16 | 4.916 / 4.950 | 0.73 | 202.04 | -0.41 / -2.99 | +0.05 / +0.12 |
| 1/20 | 4.975 / 4.984 | 0.37 | 200.65 | -1.40 / -1.49 | -0.31 / -0.59 |
| 16/1 | 26.013 / 26.519 | 2.20 | 37.71 | -2.54 / -1.17 | +0.14 / +1.90 |
| 16/2 | 1.548 / 1.642 | 6.35 | 609.07 | -6.98 / -3.56 | -4.19 / -0.33 |
| 16/3 | 1.759 / 1.835 | 9.38 | 544.87 | +36.67 / +41.18 | +6.86 / +11.45 |
| 16/4 | 1.814 / 1.841 | 9.56 | 543.31 | +11.62 / +12.87 | +3.01 / -1.02 |
| 16/8 | 3.892 / 3.910 | 3.88 | 255.74 | -8.21 / -10.34 | +1.34 / -0.96 |
| 16/16 | 4.604 / 4.641 | 1.06 | 215.47 | -0.67 / -0.59 | -0.41 / -0.92 |
| 16/20 | 4.670 / 4.706 | 6.93 | 212.51 | -1.88 / -1.70 | -1.40 / -1.27 |

[定向检查](../../.tmp/ratio-20260924/checks-local-access.log)通过基础2组、采样fixture/10项错误变体和抢占路径fixture，共4组；运行器26/26通过，两次W=1构建保留22条既有objtool警告。[机器码检查](../../.tmp/ratio-20260924/local-access-codegen.md)/[JSON](../../.tmp/ratio-20260924/local-access-codegen.json)核对六个访问/采样函数没有CMPXCHG或LOCK前缀；已pin记录入口410字节，无抢占计数读取/增减或调度分支，通用入口仍保留条件pin。它证明发射代码形态，不是性能或实时IRQ证明。

冻结provider ELF SHA-256：`0ac556136aa91b689698b232f1dbc18fb45b79e3d47d3e738bcba089c7546f18`。[闭合目录审计](../../.tmp/ratio-20260924/archive-audit-local-access.json)核对259项源码、5项二进制和126项JIT镜像，业务/摘要/排空记录一致。当前作为独立实验检查点保存，不能记为本轮目标已完成；256批次上限仅为未应用、未运行提案，不属于本批。

## 冷原生快速成功不计数（已拒绝）

`cold-failed-fixed`已完成42/42场、32400000操作，业务及排空均通过；30场实际JIT、26372390次正文，1/2线程12场仍为NO_JIT。**性能保护未通过**：对原before-fixed，c16/8中位/最大低10.83%/11.41%，c16/2中位低10.53%；3/4线程改善不能替代保护条件。对紧邻node-pair128阶段，c16/1中位提高1.32%，但c16/2低7.85%、c16/8低1.56%，没有一致恢复。

两组对照分别是原用户工作树基线before-fixed和对齐检查点f320d9f的node-pair128-fixed；每组c1/c16×七线程数×三轮，当前仅KD adaptive。以下最大吞吐与ns/op来自同一会话，全部14组列出；[对原基线的全部三轮/min/median/max/spread](../../.tmp/ratio-20260924/cold-failed-comparison.txt)、[对紧邻阶段的完整比较](../../.tmp/ratio-20260924/cold-failed-vs-node-comparison.txt)以及[records](../../.tmp/ratio-20260924/cold-failed-fixed/records.json)/[summary](../../.tmp/ratio-20260924/cold-failed-fixed/summary.json)保留精度与所有快慢样本，不跨阶段取优。

| c/t | 中位 / 最大 Mops/s | spread % | 最佳ns/op | 对before中位 / 最大 % | 对node中位 / 最大 % |
| --- | --- | ---: | ---: | --- | --- |
| 1/1 | 31.478 / 31.995 | 2.36 | 31.26 | +0.20 / +1.36 | -0.33 / +1.30 |
| 1/2 | 2.093 / 2.113 | 6.61 | 473.34 | +1.91 / -12.33 | +2.21 / -4.89 |
| 1/3 | 2.166 / 2.406 | 11.99 | 415.64 | +36.95 / +50.52 | +2.39 / +10.36 |
| 1/4 | 2.293 / 2.393 | 8.17 | 417.91 | +17.21 / +20.39 | -4.31 / -0.51 |
| 1/8 | 3.983 / 4.020 | 2.24 | 248.76 | +7.66 / +7.91 | +0.28 / +0.14 |
| 1/16 | 4.989 / 5.015 | 2.50 | 199.41 | +1.06 / -1.71 | +1.53 / +1.44 |
| 1/20 | 5.000 / 5.042 | 2.21 | 198.34 | -0.91 / -0.34 | +0.19 / +0.57 |
| 16/1 | 26.321 / 26.633 | 1.91 | 37.55 | -1.39 / -0.75 | +1.32 / +2.34 |
| 16/2 | 1.489 / 1.617 | 8.66 | 618.50 | -10.53 / -5.03 | -7.85 / -1.85 |
| 16/3 | 1.633 / 1.647 | 1.46 | 607.04 | +26.88 / +26.72 | -0.79 / +0.04 |
| 16/4 | 1.717 / 1.722 | 3.49 | 580.79 | +5.66 / +5.59 | -2.49 / -7.41 |
| 16/8 | 3.781 / 3.864 | 2.53 | 258.82 | -10.83 / -11.41 | -1.56 / -2.14 |
| 16/16 | 4.647 / 4.768 | 3.27 | 209.72 | +0.27 / +2.14 | +0.54 / +1.79 |
| 16/20 | 4.678 / 4.699 | 1.14 | 212.83 | -1.71 / -1.85 | -1.23 / -1.42 |

[定向检查](../../.tmp/ratio-20260924/checks-cold-failed.log)通过基础2组、采样fixture及10项错误变体、冷路由套件和1/2/3/8线程混合原生用例；生产W=1构建保留11条既有objtool警告。[运行器检查](../../.tmp/ratio-20260924/checks-cold-failed-runner.log)27/27通过，包含旧策略拒绝及八种历史标识分组。未运行该版本完整三方168场、nested/early或全量功能。

[闭合目录审计](../../.tmp/ratio-20260924/archive-audit-cold-failed.json)核对259项冻结源码、5项二进制、126项JIT镜像及摘要/业务/排空记录均一致；这不等于性能接受。18项已审阅输入及补丁保留于`cold-failed-reviewed-source/`，provider ELF SHA-256为`b8a52d1ee83f493a84abee3ed54556b090d8ce715e0049410e36ae1850d4d7c2`。该小规模失败候选不另作生产检查点，保留冻结证据后恢复f320d9f；下一项独立采样器实验不属于此批结果。

## 36512ed简化检查点（性能保护失败）

用户要求减少策略与统计成本：允许近似计数，不为IRQ保持精确采样，采样和比例比较使用同一节奏，复用已有MCS计数并内联薄封装。该检查点因此统一到512次MCS边界，只保留16字节的上次获取/MCS快照；先按差值比较比例，再采一次CPU时钟。首次建立比例起点，随后直接判断默认100%门槛；observe/0绕过比例。busy跳过比较时快照不推进，事件自然进入下次差值。

已移除两低确认、8窗口冷却、独立频率状态、已接受采样流及跨比例拒绝的热度保留；spin单锁改为达到512次（`>=512`）检查12.5亿TSC窗口，mutex保持1025次/25亿，CPU窗口仍为400亿。热表身份与owner/ACK/排空约束未放宽。运行器策略标识为`mcs_entry_ratio512_simple`，与所有历史标识分开汇总。准确执行语义见[热度与角色](../../../docs/JIT_EXECUTION.md#21-热度与角色)。

[checks-simple512.log](../../.tmp/ratio-20260924/checks-simple512.log)记录基础2组、采样fixture/10项错误变体、运行器26项及W=1构建通过，保留11条既有objtool警告。该pilot为c1/c16、1/2/3/4/8/16/20线程、每配置三轮/每worker100000次，只含KD adaptive42场；不是三方168场。此次guest文档仍为前检查点，运行源码/测试已逐文件核对；后续最终矩阵才冻结同步后的当前文档。不能将旧候选的结果当作简化实现的验收。

## 36512ed简化检查点的42场结果

42/42场、32400000操作数据正确且排空；30场实际JIT、累计26327355次正文，1/2线程12场为NO_JIT。16/20线程中位吞吐约低于原基线8%–9%，c16/8低10.42%；此处保留简单政策而不是宣称性能通过。吞吐单位Mops/s，三轮按r0/r1/r2排列，ns/op取最大吞吐同一会话。离线[完整比较](../../.tmp/ratio-20260924/simple512-comparison.txt)由analyze.py生成；[机器可读结果](../../.tmp/ratio-20260924/simple512-comparison.json)、[summary](../../.tmp/ratio-20260924/simple512-fixed/summary.json)、[records](../../.tmp/ratio-20260924/simple512-fixed/records.json)保留全部精度和身份。

| c / 线程 | r0 / r1 / r2 | min / median / max | spread % | 最佳ns/op | 对基线最大值变化 % |
| --- | --- | --- | ---: | ---: | ---: |
| 1 / 1 | 31.211 / 30.712 / 31.348 | 30.712 / 31.211 / 31.348 | 2.04 | 31.90 | -0.69 |
| 1 / 2 | 1.991 / 2.168 / 2.109 | 1.991 / 2.109 / 2.168 | 8.39 | 461.25 | -10.03 |
| 1 / 3 | 2.088 / 2.093 / 2.165 | 2.088 / 2.093 / 2.165 | 3.66 | 461.93 | +35.43 |
| 1 / 4 | 2.315 / 2.346 / 2.453 | 2.315 / 2.346 / 2.453 | 5.90 | 407.63 | +23.43 |
| 1 / 8 | 3.908 / 3.900 / 3.955 | 3.900 / 3.908 / 3.955 | 1.39 | 252.85 | +6.16 |
| 1 / 16 | 4.551 / 4.545 / 4.537 | 4.537 / 4.545 / 4.551 | 0.32 | 219.71 | -10.79 |
| 1 / 20 | 4.641 / 4.624 / 4.611 | 4.611 / 4.624 / 4.641 | 0.65 | 215.48 | -8.27 |
| 16 / 1 | 25.875 / 25.920 / 25.926 | 25.875 / 25.920 / 25.926 | 0.20 | 38.57 | -3.38 |
| 16 / 2 | 1.650 / 1.662 / 1.514 | 1.514 / 1.650 / 1.662 | 8.97 | 601.61 | -2.36 |
| 16 / 3 | 1.656 / 1.697 / 1.667 | 1.656 / 1.667 / 1.697 | 2.43 | 589.35 | +30.52 |
| 16 / 4 | 1.776 / 1.853 / 1.752 | 1.752 / 1.776 / 1.853 | 5.69 | 539.53 | +13.66 |
| 16 / 8 | 3.964 / 3.799 / 3.755 | 3.755 / 3.799 / 3.964 | 5.51 | 252.27 | -9.11 |
| 16 / 16 | 4.284 / 4.277 / 4.273 | 4.273 / 4.277 / 4.284 | 0.24 | 233.44 | -8.24 |
| 16 / 20 | 4.335 / 4.368 / 4.349 | 4.335 / 4.349 / 4.368 | 0.75 | 228.96 | -8.76 |

后续`node-pair128-fixed`显式对齐四节点数组到128字节，保持简单政策及节点类型/通知偏移不变；ELF节点/CPU状态相对偏移恢复到0x1580/0x1780，静态.text的80971字节相同，每CPU静态节增加64字节填充。42场全部正确排空，30场实际JIT、26333961次正文。完整14组全部样本、与simple512及原基线的比较、检查/审计和ELF哈希见[独立节点数组报告](20260924-node-array-alignment.md)。当前实际per-CPU基址未捕获，静态节一致也不表示装载后代码相同；不把相对布局推断写成硬件因果。

## b83f551检查点（历史性能失败）

spin使用GS INC累计物理获取尝试、GS XADD累计实际MCS发布，每128次发布调用受busy guard保护的采样器。独立48字节静态per-CPU比例状态保留原动态热表布局；字节相位方案已拒绝并精确恢复前版本。默认100%门槛，以4个成功采样批次构成512次策略发布窗口；包括初始乐观状态在内，连续两个低窗口关闭准入，后续8窗口保持原生。比例单独关闭保留近期单锁状态，重开时复用采样时间清除过期或倒退状态；真正的CPU频率冷热变化仍清零。

该检查点将spin单锁改为第513次记录检查严格小于12.5亿TSC ticks的窗口，缩短批次并同比缩短时间界限，大致保持频率门槛；mutex保持第1025次/25亿，CPU窗口仍为400亿。未缩短时间窗口的513次提案从未运行。observe绕过比例/冷却门槛，配对调用壳仍受CPU频率门槛约束。缓存hot不是逐入口过期保证。完整语义与计数限制以[执行流](../../../docs/JIT_EXECUTION.md#21-热度与角色)为准。

该旧候选的[初次检查](../../.tmp/ratio-20260924/checks-spin512.log)中基础两组通过，错误变体因未使用的局部`window`变量而编译失败；这是测试变体问题，原日志保留。修订为`((void)window,true)`后，[修订检查](../../.tmp/ratio-20260924/checks-spin512-revised.log)检出72项错误变体，并完成W=1的`KDLOCK_SELFTEST=1`及`=0`构建，保留22条既有objtool警告（每种11条）。这些检查不替代性能验收。诊断槽128字节隔离已独立提交`439cd82`，见[局部修复报告](20260924-diagnostic-pairs.md)，它不等于完整比例策略通过。

## 基线与测量边界

本轮基线是用户已有脏工作树加最小spin gate符号恢复，**不是纯净`a80684a`**。它使用MCS32/CPU400亿、单锁第1025次/25亿及busy guard；原始[用户补丁](../../.tmp/ratio-20260924/user.patch)和逐阶段冻结源码、ELF保留。历史MCS8/CPU400万报告不能作为本轮匹配基线。工作限于kdlock及运行器，未重建guest内核；recovery ext4副本使用`6.1.159-kdclobber2`、nokaslr、voluntary抢占，provider装载`mutex_jit=1`，此处负载为spin。

完整矩阵为1/16 cacheline × 1/2/3/4/8/16/20线程 × Linux/TCLock/KD observe/KD adaptive × 3轮，共168场；每worker100000次。匹配KD adaptive基线为42场。每会话重新加载、登记和翻译，停止daemon后单CPU预热48000次；准备与预热不计时。后端顺序正序/逆序/正序。pilot只覆盖其计划中的线程，不替代完整保护矩阵。

固定放置阶段使用`taskset -c 0-19`，worker按配置绑定CPU0至CPU(`threads-1`)，保存`runner_affinity`及拓扑；guest vCPU对应宿主CPU已另行核对。早期宿主`intel_pstate`允许1–3GHz，c16单线程出现较大变化；数据、源码及参数复核没有确定原因，不能直接归因为频率或计数指令。`before-fixed`起临时将宿主worker CPU0..19的min/max设为2500000kHz，保留[原值](../../.tmp/ratio-20260924/host-cpufreq-original.json)及[设置读回](../../.tmp/ratio-20260924/host-cpufreq-fixed.json)。这是限频配置，不是全程实测频率恒定的证明；**结束后的恢复及读回仍待完成**。

正式比值使用每配置有效最大吞吐及同一会话ns/op，同时保留全部三轮、min/median/max和`spread=(max-min)/median×100%`；三轮范围不是置信区间。模式、调用壳、策略、门槛与冻结输入分开，不跨候选取优。业务、IRQ/preempt、实际JIT及排空分别核对；允许原生的低线程样本不冒充JIT正例。PMU/profile长批次只用于诊断，不并入100000次矩阵。

## 已完成阶段与失败历史

下表链接各阶段原始records或专门诊断证据；同目录summary保留该阶段全部配置和三轮统计。完整guest证据位于`/root/kdlock-evidence/ratio-20260924/<phase>/`，host镜像位于`bench/.tmp/ratio-20260924/`。所有失败、快慢样本和未执行提案保留，不改写冻结记录。

| 阶段与证据 | 场数 | 结论与处置 |
| --- | ---: | --- |
| [before](../../.tmp/ratio-20260924/before/records.json)、[before-node0](../../.tmp/ratio-20260924/before-node0/records.json)、[before-fixed](../../.tmp/ratio-20260924/before-fixed/records.json) | 各42 | 原始、固定准备CPU集合、再固定宿主限频的独立基线；不混合取优 |
| [pct75](../../.tmp/ratio-20260924/pct75/records.json)、[pct95](../../.tmp/ratio-20260924/pct95/records.json)、[pct97](../../.tmp/ratio-20260924/pct97/records.json) | 各24 | 早期32次比例窗口门槛诊断，未解决4线程短批次 |
| [native-control](../../.tmp/ratio-20260924/native-control-console.log) | 0 | taskset仅CPU0，拓扑检查在模块加载前拒绝，无有效测量 |
| [native-control-node0](../../.tmp/ratio-20260924/native-control-node0/records.json) | 12 | 关闭委托的独立原生控制，不作为实际JIT正例 |
| [window512-pct99-node0](../../.tmp/ratio-20260924/window512-pct99-node0/records.json)、[window512-pct100-node0](../../.tmp/ratio-20260924/window512-pct100-node0/records.json) | 各24 | 独立512窗口候选，保留全部三轮，不能代替后续矩阵 |
| [final](../../.tmp/ratio-20260924/final/records.json)、[confirm2-fixed](../../.tmp/ratio-20260924/confirm2-fixed/records.json) | 各168 | 完整三方矩阵正确排空，但高线程性能保护失败；前者也未采用后续限频控制 |
| [count-on-pct0-fixed](../../.tmp/ratio-20260924/count-on-pct0-fixed/records.json)、[count-nop-pct0-fixed](../../.tmp/ratio-20260924/count-nop-pct0-fixed/records.json) | 各12 | 关闭比例，以及同布局等长NOP替换获取计数，均未恢复高竞争吞吐 |
| [before-fixed-after](../../.tmp/ratio-20260924/before-fixed-after/records.json) | 12 | 恢复原基线后吞吐恢复，独立重测不替代42场基线 |
| [table-tail-fixed](../../.tmp/ratio-20260924/table-tail-fixed/records.json)、[batch128-fixed](../../.tmp/ratio-20260924/batch128-fixed/records.json) | 各24 | 调整表尾、减少采样调用均未消除高竞争回退 |
| [separate-ratio-fixed](../../.tmp/ratio-20260924/separate-ratio-fixed/records.json)、[spin-alignment-fixed](../../.tmp/ratio-20260924/spin-alignment-fixed/records.json) | 12 / 6 | 比例状态分离及代码对齐控制未恢复吞吐 |
| pmu-before-fixed、pmu-separate-ratio-fixed：[六场计数](../../.tmp/ratio-20260924/pmu-comparison-evidence.json) | 各3 | 每场2000万操作；候选周期/op约增加20%，指令/op约增加2.5%，事件均报告100% running |
| profile-before-fixed、profile-separate-ratio-fixed：[六场采样](../../.tmp/ratio-20260924/profile-comparison.json) | 各3 | 定位诊断槽身份/禁用字段读取热点；基线前两场受采样扰动，全部保留 |
| [diag-pair128-fixed](../../.tmp/ratio-20260924/diag-pair128-fixed/records.json) | 24 | 128字节区域隔离改善匹配慢候选，独立保留为439cd82；对原基线高线程保护仍不完整 |
| profile-diag-pair128-fixed：[修复后采样](../../.tmp/ratio-20260924/profile-pair128-comparison.json) | 3 | 热点明显下降，未与pilot吞吐混合；不证明具体硬件机制 |
| [diag-pair128-pct99-fixed](../../.tmp/ratio-20260924/diag-pair128-pct99-fixed/records.json)、[slot-cache-fixed](../../.tmp/ratio-20260924/slot-cache-fixed/records.json) | 各24 | 99%门槛未守住高线程且削弱4线程收益；slot缓存无改善并撤回 |
| [retention-fixed](../../.tmp/ratio-20260924/retention-fixed/records.json) | 24 | 保留近期单锁状态后仍未满足高线程保护 |
| [startup2-fixed](../../.tmp/ratio-20260924/startup2-fixed/records.json)、[startup2-pct0-fixed](../../.tmp/ratio-20260924/startup2-pct0-fixed/records.json) | 24 / 12 | 初始两低确认及同代码比例0控制均未通过保护；比例0仍有实际JIT |
| [phase-fixed](../../.tmp/ratio-20260924/phase-fixed/records.json) | 24 | 字节相位候选无一致改善，已拒绝并精确恢复四文件；不是当前513次候选结果 |
| [spin512-fixed](../../.tmp/ratio-20260924/spin512-fixed/records.json) | 42 | b83f551的spin第513次/12.5亿候选正确排空，30场实际JIT，累计26363560次正文；高线程保护仍失败 |
| [replenish8-fixed](../../.tmp/ratio-20260924/replenish8-fixed/records.json) | 24 | simple-JIT补充后继最多8次pause；4线程明显回退，未保留 |
| [productive16-fixed](../../.tmp/ratio-20260924/productive16-fixed/records.json) | 24 | 仅已有16次成功进展再等待的候选；c16/8中位4.095、最大4.103仍低于原基线4.241/4.361Mops/s，保护未满足 |
| [simple512-fixed](../../.tmp/ratio-20260924/simple512-fixed/records.json) | 42 | 当前简化检查点正确排空，30场实际JIT/26327355次正文；高线程保护失败，全目录一致性审计通过 |
| [node-pair128-fixed](../../.tmp/ratio-20260924/node-pair128-fixed/records.json) | 42 | 独立节点数组128字节对齐，16/20线程恢复约8%–9%；仍未满足原基线全部保护 |
| [cold-failed-fixed](../../.tmp/ratio-20260924/cold-failed-fixed/records.json) | 42 | 冷原生首次CAS成功不计数；正确排空，30场实际JIT，无一致收益，已拒绝并恢复f320d9f |
| [local-access-fixed](../../.tmp/ratio-20260924/local-access-fixed/records.json) | 42 | 本地busy读写和已pin入口专化；正确排空，30场实际JIT，c16/8及部分保护仍失败 |

`startup2-fixed`相对`before-fixed`最大吞吐仍有c16/8低4.60%、c1/20低0.56%、c16/20低1.44%；同代码比例0时c16/8仍低9.58%。`phase-fixed`的c1/3、c1/4低于startup，c16/8中位约3.913对4.116Mops/s，20线程变化小且方向不一。详细三轮分别见[startup summary](../../.tmp/ratio-20260924/startup2-fixed/summary.json)、[比例0 summary](../../.tmp/ratio-20260924/startup2-pct0-fixed/summary.json)、[phase summary](../../.tmp/ratio-20260924/phase-fixed/summary.json)；这些都不属于当前缩短spin批次的测量。

诊断槽定位依据保存的ELF、装载地址和199Hz内核平面IP采样：匹配慢候选的只读身份/少写禁用字段与远端waiter计数处于同一128字节区域，分隔后`kd_spin_diag_find`加权采样周期/op从210–231降至12–20，接近原基线12–15。共享数组增加4KiB；采样period估计与skid不能视为单指令延迟或硬件机制证明。原基线前两场采样受扰动，未删除；完整限制见[修复前分析](../../.tmp/ratio-20260924/profile-comparison-observed.md)、[修复后分析](../../.tmp/ratio-20260924/profile-pair128-observed.md)。

## b83f551检查点42场pilot（历史结果）

以下仅为`spin512-fixed`的KD adaptive，与`before-fixed`同模式比较。吞吐单位Mops/s，三轮按r0/r1/r2原顺序保留；ns/op取最大吞吐的同一会话。c16/8的中位/最大分别低8.32%/10.47%，保护失败。全部精度及身份见[当前summary](../../.tmp/ratio-20260924/spin512-fixed/summary.json)、[当前records](../../.tmp/ratio-20260924/spin512-fixed/records.json)及[匹配基线](../../.tmp/ratio-20260924/before-fixed/summary.json)。

| c / 线程 | r0 / r1 / r2 | min / median / max | spread % | 最佳ns/op | 对基线最大值变化 % |
| --- | --- | --- | ---: | ---: | ---: |
| 1 / 1 | 30.950 / 30.848 / 31.499 | 30.848 / 30.950 / 31.499 | 2.10 | 31.75 | -0.21 |
| 1 / 2 | 2.294 / 2.511 / 2.133 | 2.133 / 2.294 / 2.511 | 16.47 | 398.21 | +4.21 |
| 1 / 3 | 2.295 / 2.334 / 2.391 | 2.295 / 2.334 / 2.391 | 4.13 | 418.19 | +49.60 |
| 1 / 4 | 2.587 / 2.274 / 2.689 | 2.274 / 2.587 / 2.689 | 16.05 | 371.89 | +35.29 |
| 1 / 8 | 4.151 / 3.943 / 4.147 | 3.943 / 4.147 / 4.151 | 5.02 | 240.93 | +11.41 |
| 1 / 16 | 4.990 / 4.927 / 4.920 | 4.920 / 4.927 / 4.990 | 1.42 | 200.41 | -2.20 |
| 1 / 20 | 5.042 / 5.024 / 4.998 | 4.998 / 5.024 / 5.042 | 0.87 | 198.33 | -0.34 |
| 16 / 1 | 26.313 / 26.569 / 26.348 | 26.313 / 26.348 / 26.569 | 0.97 | 37.64 | -0.98 |
| 16 / 2 | 1.528 / 1.699 / 1.526 | 1.526 / 1.528 / 1.699 | 11.35 | 588.42 | -0.17 |
| 16 / 3 | 1.755 / 1.801 / 1.757 | 1.755 / 1.757 / 1.801 | 2.62 | 555.19 | +38.55 |
| 16 / 4 | 1.991 / 1.732 / 1.799 | 1.732 / 1.799 / 1.991 | 14.38 | 502.37 | +22.07 |
| 16 / 8 | 3.888 / 3.859 / 3.905 | 3.859 / 3.888 / 3.905 | 1.18 | 256.11 | -10.47 |
| 16 / 16 | 4.677 / 4.700 / 4.663 | 4.663 / 4.677 / 4.700 | 0.80 | 212.75 | +0.69 |
| 16 / 20 | 4.710 / 4.743 / 4.761 | 4.710 / 4.743 / 4.761 | 1.08 | 210.03 | -0.54 |

## 检查、未执行提案与归档

旧候选验证均留在匹配日志：retention为69项采样变体；startup初次漏检`reject-counter-wrap`而失败，两组基础单元通过，修订后67项检出；byte-phase的plain和显式变量对齐版本各70项检出并完成W=1构建，各保留11条既有objtool警告。日志见[retention](../../.tmp/ratio-20260924/checks-retention.log)、[startup首次](../../.tmp/ratio-20260924/checks-startup.log)、[startup修订](../../.tmp/ratio-20260924/checks-startup-revised.log)、[phase首次](../../.tmp/ratio-20260924/checks-phase.log)、[phase对齐](../../.tmp/ratio-20260924/checks-phase-aligned.log)。fixture及离线一致性不证明真实内核并发，也不能替代当前候选验证。

未执行材料包括late-allocation提案、`capture_allocations.py`、未对齐`phase-v1`以及未同比缩短时间的`spin512-unscaled-source`；未通过该wrapper读取`/proc/kcore`。phase的GS重定位疑虑是误报：旧计数器同样使用PC32，无需修正asm操作数，见[机器码核对](../../.tmp/ratio-20260924/phase-codegen-observed.md)。相关源码、测试、构建和撤回快照均保留，未运行提案不计入场数。

截至local-access-fixed，十二份去重审计覆盖37个关闭阶段、1125场、1233600000计时操作；957场KD中801场有实际JIT，累计969970182次正文。源码9523项、二进制193项、生成JIT镜像2871项哈希及业务/摘要/排空记录一致；这些跨阶段累计包含失败和诊断，不代表性能接受。明细及审计SHA见[证据清单](../../.tmp/ratio-20260924/retention-evidence-inventory.json)。

通用审计：[前16阶段](../../.tmp/ratio-20260924/archive-audit-completed-phases.json)、[六组诊断](../../.tmp/ratio-20260924/archive-audit-diagnostic-phases.json)、[诊断槽后四阶段](../../.tmp/ratio-20260924/archive-audit-pair128-phases.json)、[retention](../../.tmp/ratio-20260924/archive-audit-retention-phase.json)、[startup两阶段](../../.tmp/ratio-20260924/archive-audit-startup2-phases.json)、[phase](../../.tmp/ratio-20260924/archive-audit-phase-fixed.json)、[spin512](../../.tmp/ratio-20260924/archive-audit-spin512-fixed.json)、[两个后继等待阶段](../../.tmp/ratio-20260924/archive-audit-replenishment.json)、[simple512](../../.tmp/ratio-20260924/archive-audit-simple512.json)、[节点数组对齐](../../.tmp/ratio-20260924/archive-audit-node-pair128.json)、[冷路径计数候选](../../.tmp/ratio-20260924/archive-audit-cold-failed.json)、[本地访问候选](../../.tmp/ratio-20260924/archive-audit-local-access.json)。额外PMU/profile工具与采样数据由各自分析另行核对。审计不执行归档代码，只验证内部一致性，不重新证明过去记录的真实性。

`spin512-fixed`覆盖c1/c16、1/2/3/4/8/16/20线程、每配置三轮及每worker100000次，仅KD adaptive共42场、32400000操作。所有业务及排空检查通过，1/2线程的12场没有实际JIT，其余30场有正文证据；这不是三方168场通过。该检查点未通过性能保护，未将其他候选更快样本拼入该阶段。宿主限频恢复、最终输入快照、完整证据包路径与SHA仍待实际完成；[归档清单](../../.tmp/ratio-20260924/final-archive-checklist.md)目前只是未执行草案。

两个后继等待实验均为24场、21000000操作，全部正确排空且均有实际JIT，正文分别为18050703/16968695次；功能完成不代表收益。`replenish8-source`、`productive16-source`保留代码和fixture，五个相关文件已显式恢复为b83f551，当前简化版本不含新增等待。批长、尾部完成分散及局限见[原始计数分析](../../.tmp/ratio-20260924/batch-fairness-observed.md)、[8次等待分析](../../.tmp/ratio-20260924/replenish8-batch-observed.md)。用户随后要求直接简化比例策略；这不是对未测简化版本的性能结论。
