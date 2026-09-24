# 2026-09-24：低竞争比例准入调查（EXPERIMENTAL检查点，性能验收未完成）

目标是改善3/4线程短代理批次，同时保持1/2/8/16/20线程性能。**目标尚未完成。** 简化政策已保存为EXPERIMENTAL检查点`36512ed`；随后独立的节点数组128字节对齐在16/20线程相对simple512恢复约8%–9%，但c16/8中位仍低于原基线9.42%，c16/1低2.68%。两阶段各42场正确排空，均不能记为完整性能保护通过。旧检查点`b83f551`、所有失败候选及原始快慢样本继续保留；目录名`final`不代表通过。

节点数组对齐已独立提交为`f320d9f`。后续冷原生快速成功不计数候选未取得一致收益，已决定拒绝，运行输入在下一项独立实验前恢复到f320d9f。候选省略首次CAS成功，失败仍在pending/MCS前记录，使用独立标识`mcs_entry_ratio512_cold_failed`；该标识只保留在归档源码和结果中，不混入恢复后的`mcs_entry_ratio512_simple`成绩。

节点notification的128字节区域隔离已完成42场并拒绝：扩大节点未改善8线程且损害16/20线程，六项布局/fixture文件已恢复d253d23/f71dc2e。当前节点仍为128字节、通知偏移64/65、数组按128字节对齐，批次上限1024；失败结果单列如下。

统一128次采样/比较候选已完成42场并拒绝：相对local-access，c1/c16的4线程中位分别低10.76%/10.36%，c16/8仍未满足原基线保护。六项输入已恢复24896bd的512次政策；新512补集计数候选不属于下列已关闭结果。

## 本地busy保护与已pin入口专化（f71dc2e实验检查点）

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

[定向检查](../../.tmp/ratio-20260924/checks-local-access.log)通过基础2组、采样fixture/10项错误变体和抢占路径fixture，共4组；运行器26/26通过，两次W=1构建保留22条既有objtool警告。[冻结benchmark机器码检查](../../.tmp/ratio-20260924/local-access-frozen-codegen.md)/[JSON](../../.tmp/ratio-20260924/local-access-frozen-codegen.json)核对六个访问/采样函数没有CMPXCHG或LOCK前缀；已pin记录入口410字节，无抢占计数读取/增减或调度分支，通用入口仍保留条件pin。独立构建的[检查](../../.tmp/ratio-20260924/local-access-codegen.md)另存，未启用benchmark正文计数，ELF身份不同；两份均通过形态核对。这不是性能或实时IRQ证明。

冻结provider ELF SHA-256：`0ac556136aa91b689698b232f1dbc18fb45b79e3d47d3e738bcba089c7546f18`。[闭合目录审计](../../.tmp/ratio-20260924/archive-audit-local-access.json)核对259项源码、5项二进制和126项JIT镜像，业务/摘要/排空记录一致。当前作为独立实验检查点f71dc2e保存，不能记为本轮目标已完成；后续256批次上限实验已拒绝并恢复1024，其结果单列如下。

## 统一128次采样/比较（已拒绝，恢复512次）

`unified128-fixed`将MCS采样/比例比较与spin单锁记录统一到128次，单锁时间窗口同比缩为312500000 ticks；CPU400亿及mutex窗口保持。策略以`mcs_entry_ratio128_simple`单列。42/42场、32400000操作正确排空，30场实际JIT、26715960次正文；但相对local-access，c1/c16的4线程中位分别低10.76%/10.36%，c16/8相对原before-fixed的中位/最大仍低8.57%/9.38%。因此拒绝，六项输入已恢复24896bd，见[恢复收据](../../.tmp/ratio-20260924/sync-unified128-restored.json)。

[全部14组原始三轮及min/median/max/spread、同场最佳ns/op](../../.tmp/ratio-20260924/unified128-results.md)、[对before完整比较](../../.tmp/ratio-20260924/unified128-before-comparison.json)、[对local完整比较](../../.tmp/ratio-20260924/unified128-local-comparison.json)与[records](../../.tmp/ratio-20260924/unified128-fixed/records.json)保留全部快慢样本。[定向检查](../../.tmp/ratio-20260924/checks-unified128.log)通过3组、10项采样错误变体、26项运行器检查及生产W=1构建，保留11条既有objtool警告。[闭合审计](../../.tmp/ratio-20260924/archive-audit-unified128.json)核对259项源码、5项二进制和126项JIT镜像，provider SHA-256为`36e6fcf15685e0e567b01d11535f980ee4565facfdde585bb5c614ef9e7a4b76`。未运行该候选完整三方168场或nested/early；正确性和审计通过不等于性能接受。

## 节点notification区域128字节隔离（已拒绝）

`node-region128-fixed`将单节点128→256字节、通知偏移64/65→128/129，使四节点数组增加512字节/CPU；未改tail编码、配对唤醒、比例或1024批次上限。冻结ELF的per-CPU节大小0x1e40、对齐128，节点数组位于0x1580、大小1024，CPU状态位于0x1980。这些是相对节布局，不是实际per-CPU基址或缓存机制证明。

42/42场、32400000操作正确排空，30场实际JIT、26291925次正文。相对local-access，c1/c16的16/20线程中位下降6.47%–7.53%，c16/8又低2.32%；因此拒绝。六项布局/fixture文件已恢复d253d23/f71dc2e的128字节节点及64/65通知偏移，数组128字节对齐与批次上限1024保持。尚无本轮性能保护通过结论。

以下保留所有14组；最大吞吐与ns/op取同场。[对before全部三轮/min/median/max/spread](../../.tmp/ratio-20260924/node-region128-comparison.txt)、[对local-access完整比较](../../.tmp/ratio-20260924/node-region128-vs-local-comparison.txt)、[records](../../.tmp/ratio-20260924/node-region128-fixed/records.json)/[summary](../../.tmp/ratio-20260924/node-region128-fixed/summary.json)保留全部精度和快慢样本。

| c/t | 中位 / 最大 Mops/s | spread % | 最佳ns/op | 对before中位 / 最大 % | 对local中位 / 最大 % |
| --- | --- | ---: | ---: | --- | --- |
| 1/1 | 31.563 / 31.781 | 3.04 | 31.47 | +0.47 / +0.69 | +0.62 / +0.68 |
| 1/2 | 2.077 / 2.185 | 7.81 | 457.75 | +1.11 / -9.35 | -3.64 / +1.18 |
| 1/3 | 2.172 / 2.209 | 4.03 | 452.63 | +37.32 / +38.21 | +2.09 / +0.41 |
| 1/4 | 2.379 / 2.437 | 5.22 | 410.30 | +21.60 / +22.62 | -2.43 / -2.59 |
| 1/8 | 3.908 / 3.910 | 1.88 | 255.75 | +5.61 / +4.96 | -1.92 / -7.47 |
| 1/16 | 4.546 / 4.589 | 0.97 | 217.90 | -7.91 / -10.05 | -7.53 / -7.28 |
| 1/20 | 4.642 / 4.650 | 0.43 | 215.07 | -8.00 / -8.10 | -6.69 / -6.71 |
| 16/1 | 26.638 / 26.663 | 0.11 | 37.51 | -0.20 / -0.64 | +2.40 / +0.54 |
| 16/2 | 1.507 / 1.645 | 10.70 | 607.85 | -9.46 / -3.37 | -2.67 / +0.20 |
| 16/3 | 1.621 / 1.643 | 1.60 | 608.64 | +25.89 / +26.38 | -7.89 / -10.48 |
| 16/4 | 1.779 / 1.814 | 2.55 | 551.21 | +9.43 / +11.25 | -1.96 / -1.43 |
| 16/8 | 3.802 / 3.849 | 3.55 | 259.84 | -10.33 / -11.75 | -2.32 / -1.58 |
| 16/16 | 4.306 / 4.314 | 0.32 | 231.78 | -7.10 / -7.58 | -6.47 / -7.04 |
| 16/20 | 4.358 / 4.369 | 0.31 | 228.88 | -8.44 / -8.73 | -6.69 / -7.15 |

[检查日志](../../.tmp/ratio-20260924/checks-node-region128.log)通过基础2组及storage/batch/wait/shadow共6组、5项storage错误变体；W=1 SELFTEST=1/0构建共22条既有objtool警告。[闭合目录审计](../../.tmp/ratio-20260924/archive-audit-node-region128.json)核对259项源码、5项二进制、126项JIT镜像及业务/摘要/排空一致；冻结provider SHA-256为`5b86d373dde1e5047670ed18e3e6c32ac43048e001b996de5149555f07c69b36`。该阶段只有KD adaptive42场，未运行完整三方168场或nested/early；恢复后另采的profile属于诊断，不能合并为该布局收益。

## combiner批次上限256（已拒绝，恢复1024）

在f71dc2e上只将spin批次上限1024→256，保持比例、队列退出和交接协议；两个受影响fixture读取生产常量，并增加cap−1/cap/cap+1完成前缀及未完成后继检查。`cap256-fixed`覆盖c1/c16×8/20线程×三轮，共12/12场、16800000操作正确排空，全部实际JIT、16498308次正文。c16/8中位相对local-access仅+0.11%，而c1/c16的20线程分别−2.42%/−2.47%，因此拒绝；五项生产/fixture文件已恢复f71dc2e，当前上限为1024。

| c/t | r0 / r1 / r2 Mops/s | min / median / max | spread % | 最佳ns/op | 对before中位 / 最大 % | 对local中位 / 最大 % |
| --- | --- | --- | ---: | ---: | --- | --- |
| 1/8 | 3.991 / 3.998 / 4.035 | 3.991 / 3.998 / 4.035 | 1.10 | 247.81 | +8.04 / +8.32 | +0.34 / -4.50 |
| 1/20 | 4.855 / 4.845 / 4.858 | 4.845 / 4.855 / 4.858 | 0.27 | 205.83 | -3.78 / -3.97 | -2.42 / -2.51 |
| 16/8 | 3.925 / 3.828 / 3.897 | 3.828 / 3.897 / 3.925 | 2.48 | 254.81 | -8.11 / -10.01 | +0.11 / +0.37 |
| 16/20 | 4.548 / 4.576 / 4.555 | 4.548 / 4.555 / 4.576 | 0.62 | 218.52 | -4.30 / -4.40 | -2.47 / -2.75 |

最大吞吐与ns/op来自同场；[对before完整比较](../../.tmp/ratio-20260924/cap256-comparison.txt)、[对local-access完整比较](../../.tmp/ratio-20260924/cap256-vs-local-comparison.txt)、[records](../../.tmp/ratio-20260924/cap256-fixed/records.json)/[summary](../../.tmp/ratio-20260924/cap256-fixed/summary.json)保留精度。该小矩阵未覆盖1/2/3/4/16线程，不是全性能验收。

[首份检查](../../.tmp/ratio-20260924/checks-cap256.log)基础和直接相关fixture共4组通过，但随后直接调用Python脚本因缺少source_text导入路径失败；[第二次直接调用](../../.tmp/ratio-20260924/checks-cap256-mutations-build.log)同样失败，均保留。[改用仓库runner的检查](../../.tmp/ratio-20260924/checks-cap256-runner-build.log)通过early/late两项新增cap变体及9项既有变体，生产W=1构建保留11条既有objtool警告。没有把导入失败计作通过。

[闭合目录审计](../../.tmp/ratio-20260924/archive-audit-cap256.json)核对259项源码、5项二进制和36项JIT镜像，业务/摘要/排空一致；冻结provider SHA-256为`5995119447b80e9b3f53342fe006b1967a319d4432782ebdda445a401796613d`。提案、已测源码和所有失败记录继续归档；当前性能保护仍未完成。

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
| [cap256-fixed](../../.tmp/ratio-20260924/cap256-fixed/records.json) | 12 | 上限256未改善c16/8且损害20线程；正确排空，全部实际JIT，拒绝并恢复f71dc2e的1024上限 |
| [node-region128-fixed](../../.tmp/ratio-20260924/node-region128-fixed/records.json) | 42 | 节点扩大到256字节、通知偏移128；正确排空，损害16/20线程，拒绝并恢复128字节节点 |
| [profile-local-c16-t8](../../.tmp/ratio-20260924/profile-local-c16-t8-analysis.json) | 3 | 恢复local-access后的c16/8诊断，通用及perf专用检查通过；无匹配控制，不计作性能结果 |
| [unified128-fixed](../../.tmp/ratio-20260924/unified128-fixed/records.json) | 42 | 统一128次采样/比较削弱4线程收益且c16/8保护仍失败；正确排空，30场实际JIT，拒绝并恢复24896bd的512次政策 |

`startup2-fixed`相对`before-fixed`最大吞吐仍有c16/8低4.60%、c1/20低0.56%、c16/20低1.44%；同代码比例0时c16/8仍低9.58%。`phase-fixed`的c1/3、c1/4低于startup，c16/8中位约3.913对4.116Mops/s，20线程变化小且方向不一。详细三轮分别见[startup summary](../../.tmp/ratio-20260924/startup2-fixed/summary.json)、[比例0 summary](../../.tmp/ratio-20260924/startup2-pct0-fixed/summary.json)、[phase summary](../../.tmp/ratio-20260924/phase-fixed/summary.json)；这些都不属于当前缩短spin批次的测量。

诊断槽定位依据保存的ELF、装载地址和199Hz内核平面IP采样：匹配慢候选的只读身份/少写禁用字段与远端waiter计数处于同一128字节区域，分隔后`kd_spin_diag_find`加权采样周期/op从210–231降至12–20，接近原基线12–15。共享数组增加4KiB；采样period估计与skid不能视为单指令延迟或硬件机制证明。原基线前两场采样受扰动，未删除；完整限制见[修复前分析](../../.tmp/ratio-20260924/profile-comparison-observed.md)、[修复后分析](../../.tmp/ratio-20260924/profile-pair128-observed.md)。

恢复local-access后，c16/8的三场独立profile共24000000操作正确排空，均有实际JIT、累计23275406次正文。199Hz内核平面IP采样的工具/数据/JIT/地址哈希检查通过，零丢失样本，record stderr为空。约77.6%的加权样本落在物理等待函数；已pin热表记录仅约0.276%（25个样本），未观察到独立MCS采样器IP，但内联计数仍归在调用者中。约97%的操作有JIT正文，不等于生成镜像的1.436%周期样本权重。**这是无匹配控制的描述性诊断**：等待占比不能解释服务为何变慢，小函数样本稀疏且可能skid，2.64%权重因缺少内核符号边界仍未归属，flat-IP导出也不能量化节流；不能据此认定某条指令、复制或后继检查造成回退。详情见[诊断说明](../../.tmp/ratio-20260924/profile-local-c16-t8-observed.md)、[分析JSON](../../.tmp/ratio-20260924/profile-local-c16-t8-analysis.json)与[精确IP上下文](../../.tmp/ratio-20260924/profile-local-c16-t8-hot-instructions.json)，不并入100000次性能矩阵。

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

截至unified128-fixed，十六份去重审计覆盖41个关闭阶段、1224场、1339200000计时操作；1056场KD中876场有实际JIT，累计1062751781次正文。源码10560项、二进制213项、生成JIT镜像3168项哈希及业务/摘要/排空记录一致；这些跨阶段累计包含失败和诊断，不代表性能接受，不包含后续未关闭候选。明细及审计SHA见[证据清单](../../.tmp/ratio-20260924/retention-evidence-inventory.json)。

通用审计：[前16阶段](../../.tmp/ratio-20260924/archive-audit-completed-phases.json)、[六组诊断](../../.tmp/ratio-20260924/archive-audit-diagnostic-phases.json)、[诊断槽后四阶段](../../.tmp/ratio-20260924/archive-audit-pair128-phases.json)、[retention](../../.tmp/ratio-20260924/archive-audit-retention-phase.json)、[startup两阶段](../../.tmp/ratio-20260924/archive-audit-startup2-phases.json)、[phase](../../.tmp/ratio-20260924/archive-audit-phase-fixed.json)、[spin512](../../.tmp/ratio-20260924/archive-audit-spin512-fixed.json)、[两个后继等待阶段](../../.tmp/ratio-20260924/archive-audit-replenishment.json)、[simple512](../../.tmp/ratio-20260924/archive-audit-simple512.json)、[节点数组对齐](../../.tmp/ratio-20260924/archive-audit-node-pair128.json)、[冷路径计数候选](../../.tmp/ratio-20260924/archive-audit-cold-failed.json)、[本地访问候选](../../.tmp/ratio-20260924/archive-audit-local-access.json)、[批次上限256](../../.tmp/ratio-20260924/archive-audit-cap256.json)、[节点区域隔离](../../.tmp/ratio-20260924/archive-audit-node-region128.json)、[c16/8独立profile](../../.tmp/ratio-20260924/archive-audit-profile-local-c16-t8.json)、[统一128次候选](../../.tmp/ratio-20260924/archive-audit-unified128.json)。额外PMU/profile工具与采样数据由各自分析另行核对。审计不执行归档代码，只验证内部一致性，不重新证明过去记录的真实性。

`spin512-fixed`覆盖c1/c16、1/2/3/4/8/16/20线程、每配置三轮及每worker100000次，仅KD adaptive共42场、32400000操作。所有业务及排空检查通过，1/2线程的12场没有实际JIT，其余30场有正文证据；这不是三方168场通过。该检查点未通过性能保护，未将其他候选更快样本拼入该阶段。宿主限频恢复、最终输入快照、完整证据包路径与SHA仍待实际完成；[归档清单](../../.tmp/ratio-20260924/final-archive-checklist.md)目前只是未执行草案。

两个后继等待实验均为24场、21000000操作，全部正确排空且均有实际JIT，正文分别为18050703/16968695次；功能完成不代表收益。`replenish8-source`、`productive16-source`保留代码和fixture，五个相关文件已显式恢复为b83f551，当前简化版本不含新增等待。批长、尾部完成分散及局限见[原始计数分析](../../.tmp/ratio-20260924/batch-fairness-observed.md)、[8次等待分析](../../.tmp/ratio-20260924/replenish8-batch-observed.md)。用户随后要求直接简化比例策略；这不是对未测简化版本的性能结论。
