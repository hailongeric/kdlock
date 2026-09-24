# 2026-09-24：低竞争比例准入调查（EXPERIMENTAL检查点，性能验收未完成）

目标是改善3/4线程短代理批次，同时保持1/2/8/16/20线程性能。**当前工作候选的42场KD adaptive正确排空，但性能保护仍失败，目标尚未完成。** 此前完整矩阵`final`、`confirm2-fixed`及后续pilot均按原身份保留；目录名`final`不代表通过。当前候选为`spin512-fixed`，尚未运行它的完整三方168场，也未作为性能验收通过版本。

## 当前工作候选

spin使用GS INC累计物理获取尝试、GS XADD累计实际MCS发布，每128次发布调用受busy guard保护的采样器。独立48字节静态per-CPU比例状态保留原动态热表布局；字节相位方案已拒绝并精确恢复前版本。默认100%门槛，以4个成功采样批次构成512次策略发布窗口；包括初始乐观状态在内，连续两个低窗口关闭准入，后续8窗口保持原生。比例单独关闭保留近期单锁状态，重开时复用采样时间清除过期或倒退状态；真正的CPU频率冷热变化仍清零。

当前将spin单锁改为第513次记录检查严格小于12.5亿TSC ticks的窗口，缩短批次并同比缩短时间界限，大致保持频率门槛；mutex保持第1025次/25亿，CPU窗口仍为400亿。未缩短时间窗口的513次提案从未运行。observe绕过比例/冷却门槛，配对调用壳仍受CPU频率门槛约束。缓存hot不是逐入口过期保证。完整语义与计数限制以[执行流](../../../docs/JIT_EXECUTION.md#21-热度与角色)为准。

当前缩短spin批次的[初次检查](../../.tmp/ratio-20260924/checks-spin512.log)中基础两组通过，错误变体因未使用的局部`window`变量而编译失败；这是测试变体问题，原日志保留。修订为`((void)window,true)`后，[修订检查](../../.tmp/ratio-20260924/checks-spin512-revised.log)检出72项错误变体，并完成W=1的`KDLOCK_SELFTEST=1`及`=0`构建，保留22条既有objtool警告（每种11条）。这些检查不替代性能验收。诊断槽128字节隔离已独立提交`439cd82`，见[局部修复报告](20260924-diagnostic-pairs.md)，它不等于完整比例策略通过。

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
| [spin512-fixed](../../.tmp/ratio-20260924/spin512-fixed/records.json) | 42 | 当前spin第513次/12.5亿候选正确排空，30场实际JIT，累计26363560次正文；高线程保护仍失败 |

`startup2-fixed`相对`before-fixed`最大吞吐仍有c16/8低4.60%、c1/20低0.56%、c16/20低1.44%；同代码比例0时c16/8仍低9.58%。`phase-fixed`的c1/3、c1/4低于startup，c16/8中位约3.913对4.116Mops/s，20线程变化小且方向不一。详细三轮分别见[startup summary](../../.tmp/ratio-20260924/startup2-fixed/summary.json)、[比例0 summary](../../.tmp/ratio-20260924/startup2-pct0-fixed/summary.json)、[phase summary](../../.tmp/ratio-20260924/phase-fixed/summary.json)；这些都不属于当前缩短spin批次的测量。

诊断槽定位依据保存的ELF、装载地址和199Hz内核平面IP采样：匹配慢候选的只读身份/少写禁用字段与远端waiter计数处于同一128字节区域，分隔后`kd_spin_diag_find`加权采样周期/op从210–231降至12–20，接近原基线12–15。共享数组增加4KiB；采样period估计与skid不能视为单指令延迟或硬件机制证明。原基线前两场采样受扰动，未删除；完整限制见[修复前分析](../../.tmp/ratio-20260924/profile-comparison-observed.md)、[修复后分析](../../.tmp/ratio-20260924/profile-pair128-observed.md)。

## 当前42场pilot结果

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

截至`spin512-fixed`，七份去重审计覆盖31个关闭阶段、909场、1062000000计时操作；741场KD中633场有实际JIT，累计829585689次正文。源码7973项、二进制163项、生成JIT镜像2223项哈希及业务/摘要/排空记录一致；这些是跨阶段累计检查数，包含性能失败和诊断，不是909场性能验收通过。明细、每阶段数量及审计SHA见[证据清单](../../.tmp/ratio-20260924/retention-evidence-inventory.json)。

通用审计：[前16阶段](../../.tmp/ratio-20260924/archive-audit-completed-phases.json)、[六组诊断](../../.tmp/ratio-20260924/archive-audit-diagnostic-phases.json)、[诊断槽后四阶段](../../.tmp/ratio-20260924/archive-audit-pair128-phases.json)、[retention](../../.tmp/ratio-20260924/archive-audit-retention-phase.json)、[startup两阶段](../../.tmp/ratio-20260924/archive-audit-startup2-phases.json)、[phase](../../.tmp/ratio-20260924/archive-audit-phase-fixed.json)、[spin512](../../.tmp/ratio-20260924/archive-audit-spin512-fixed.json)。额外PMU/profile工具与采样数据由各自分析另行核对。审计不执行归档代码，只验证内部一致性，不重新证明过去记录的真实性。

`spin512-fixed`覆盖c1/c16、1/2/3/4/8/16/20线程、每配置三轮及每worker100000次，仅KD adaptive共42场、32400000操作。所有业务及排空检查通过，1/2线程的12场没有实际JIT，其余30场有正文证据；这不是三方168场通过。当前继续调查高线程回退，未将旧候选更快样本拼入该阶段。宿主限频恢复、最终输入快照、完整证据包路径与SHA仍待实际完成；[归档清单](../../.tmp/ratio-20260924/final-archive-checklist.md)目前只是未执行草案。
