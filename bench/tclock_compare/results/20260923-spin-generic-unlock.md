# 2026-09-23 统一 spin 解锁入口验证（三轮）

> 保留统一解锁的ABI与JIT回归证据。下列108场性能属于continuation布局优化前的冻结版本；当前完整性能见[168场三轮矩阵](20260923-spin-default-heat-full3.md)。

统一解锁后，**108/108 性能场次、9000 万次计时操作全部通过并排空**；48 场竞争 KD 均执行实际 JIT。六组相关测试、22 项运行器测试以及 nested/early 各两场也通过。20 线程热度分流壳相对同期保留壳：c1 最大吞吐提高 1.56%–3.60%，c16 下降 0.24%–0.77%；三轮仍有明显波动，不能把本次差异单独归因于解锁改动。

## 改动与执行流

`KD_SPIN_DIRECT_UNLOCK` 无条件调用 `kd_spin_unlock_clobber_v1`。调用端不再读取锁字并选择冷/热解锁；普通冷获取也按 broad-clobber ABI 传递 lock、CALL 前 SP、CALL 后 IP 和 BP。获取侧的 CPU 热度 C `if` 保留，寄存器保存继续由编译器依据 clobber 决定，没有手工 push/pop。

provider 先检查锁字低字节是否为 5：命中时 release 清零该字节、减少本 CPU 的 `nondelegated`、恢复获取时的抢占 pin 后返回，保留 pending/tail；其他状态进入原来的 fast-owner、native-ACK、ticket 解锁核心。原 `kd_spin_direct_native_unlock` 导出暂留兼容，新配对壳不再使用它。冷态物理释放本身不用 SP/IP/BP，但统一完成入口仍要求该元数据满足 JIT COMPLETE 校验。

| 路径 | 修改前 | 修改后 |
| --- | --- | --- |
| 冷获取后原线程执行 | 完整 CAS/pending/MCS → 正文 → 调用端检查低字节 5 → 普通 C 冷解锁 helper → release/减计数/unpin | 获取与正文相同 → broad-clobber 解锁 CALL，传 lock/SP/IP/BP → provider 检查 5 → release/减计数/unpin |
| 热获取后原线程执行 | 正文 → 调用端检查低字节 → broad-clobber 解锁 CALL → 原解锁核心 | 正文 → broad-clobber 解锁 CALL → provider 检查低字节 → 原解锁核心 |
| 已代理的 JIT 正文 | 调用端锁字读取及冷/热解锁分支 → 可识别的解锁完成边界 | 直接到达同一解锁完成边界，SP/IP/BP 校验及 COMPLETE/owner/ACK/退休协议保留 |

JIT 完成边界由翻译器/wrapper 识别，被代理正文不执行 provider 的 byte-5 物理释放检查。普通原生路径则是把检查移入 provider，并没有删除该检查；冷调用新增统一 metadata/broad-clobber 义务。

归档反汇编确认 c1/c16 源正文至解锁 CALL 分别为 8/53 条指令，on/off 均只有一个通用解锁 CALL；均不再读取 byte 5 或引用旧 helper。c1 JIT 从正文标签至 `JMP exit`，历史热度分流壳为 28 条，本轮 on/off 均为 19 条；若计入正常分派则为 32→23 条。移除的九条包括四条锁字分支指令、四条额外块 budget 指令及一次 witness 写入。当前正文只有一个块、一处 witness；共同分派的 budget 初始化仍在。

c16 的全部 36 个 KD 会话生成物也已核对，其中 24 场实际执行 JIT：on/off 正文均为 94 条指令，计入分派均为 98 条；历史 on 为 103/107 条，同样减少九条。每份均只有一个正文块、一处 witness、零正文条件分支/额外 budget 访问；单线程的 12 份仅证明已发布，仍按零 JIT 报告。共同分派中的 budget 初始化与入口条件跳转保留。

两种壳仍有差别：on 从逻辑调用者栈 `[R12-0x30]` 取锁参数，off 用立即数；on 的 8 字节 spill 槽仍在。两者仍由 GCC 在获取前保存 RBP/R15/R14/R13/R12/RBX。以上是机器码事实，未测得这些指令各自节省的周期数。详细提取与指令清单见归档 `codegen-review.md/json`。

## 验证范围

| 检查 | 结果 |
| --- | --- |
| 基础及相关单元 | 6/6；涵盖 cold/非代理获取、普通/byte-5 混合 MCS、pin 配对、generic unlock ABI/JIT COMPLETE 与拒绝/续跑 |
| 冻结运行器测试 | 22/22；全部通过 |
| nested 功能 | 2/2，80 万次操作，785760 次实际 JIT 正文 |
| early 功能 | 2/2，80 万次操作，199811 次实际 JIT 正文 |
| 性能 | 108/108，9000 万次计时操作；36 配置均有三轮有效且排空样本 |
| 性能 JIT | 53566167 次正文；48/48 竞争 KD 场次为 PASS；24 场单线程 KD 为 NO_JIT |
| 20 线程 JIT 比例 | 24 场为 99.74775%–99.88405% |
| 独立离线审计 | 147 项检查，errors=[]；重新计算场次、计数、汇总与哈希 |
| 冻结一致性 | 每个 live 目录 250 个源码文件；性能 9 个、nested/early 各 5 个二进制匹配清单 |

所有 live 场次业务与批次 IRQ/preempt 恢复检查通过，源模块/翻译器/请求排空，最终 guest 空闲；未检测到内核或 live daemon 故障。unit.log 中的 translator 失败文本来自基础 daemon 负例测试，最终单元套件通过。三次 provider 构建各有 **11 条 objtool 警告**，各另有 36 行 Perl locale 警告；不记为无告警构建。

性能矩阵为 1/16 cacheline × 1/4/20 线程 × 六项 × 三轮，共 108 场。六项是 Linux、TCLock、KD observe/adaptive 各自的保留壳与热度分流壳。Linux/TCLock 每轮各测一次，供相同配置 KD 比较；各后端顺序随轮次交替。每线程 100000 次；显式准备/发布、单 CPU 48000 次预热及后续等待均在计时外。功能模式为 c1/t4、on、observe/adaptive，显式 `--repeats 1`。

## 三方成绩与波动

每格为 **Mops/s / ns/op**，采用三轮有效最大吞吐及同一获选会话的摊销时间；O/A 为 observe/adaptive，off/on 为本轮冻结运行器中的保留/热度分流调用壳。

| cacheline | 线程 | Linux | TCLock | O off | O on | A off | A on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.304 / 57.79 | 13.625 / 73.39 | 9.096 / 109.94 | 12.477 / 80.15 | 10.696 / 93.49 | 13.191 / 75.81 |
| 1 | 4 | 3.675 / 272.10 | 3.226 / 309.94 | 1.871 / 534.51 | 1.853 / 539.61 | 1.817 / 550.22 | 1.994 / 501.57 |
| 1 | 20 | 5.385 / 185.69 | 5.020 / 199.21 | 4.029 / 248.22 | 4.174 / 239.60 | 4.096 / 244.14 | 4.160 / 240.39 |
| 16 | 1 | 13.650 / 73.26 | 11.515 / 86.85 | 15.296 / 65.37 | 12.292 / 81.35 | 9.120 / 109.65 | 12.111 / 82.57 |
| 16 | 4 | 2.141 / 466.96 | 2.199 / 454.80 | 1.664 / 600.98 | 1.541 / 648.90 | 1.617 / 618.42 | 1.574 / 635.12 |
| 16 | 20 | 2.738 / 365.17 | 3.264 / 306.35 | 3.931 / 254.37 | 3.922 / 254.97 | 3.983 / 251.05 | 3.953 / 253.00 |

20 线程三轮吞吐的 min/median/max 单位为 Mops/s；波动为 `(max-min)/median × 100%`。两种差值分别使用两组最大值、中位数计算，不是三轮配对差值的中位数。

| cacheline / 模式 | off：min / median / max | on：min / median / max | off / on 波动 | on/off 最大值差 | on/off 中位数差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 / observe | 3.991 / 4.003 / 4.029 | 4.013 / 4.148 / 4.174 | 0.93% / 3.87% | +3.60% | +3.63% |
| 1 / adaptive | 4.005 / 4.008 / 4.096 | 3.925 / 4.086 / 4.160 | 2.27% / 5.74% | +1.56% | +1.95% |
| 16 / observe | 3.911 / 3.927 / 3.931 | 3.902 / 3.911 / 3.922 | 0.52% / 0.51% | -0.24% | -0.42% |
| 16 / adaptive | 3.926 / 3.934 / 3.983 | 3.905 / 3.914 / 3.953 | 1.45% / 1.22% | -0.77% | -0.51% |

c16 的 on 在三个相同轮号中均略低于 off；c1/adaptive 的逐轮差为 −2.06%、+3.87%、−0.25%，不能仅凭最大值 +1.56% 宣称稳定提升。c1/observe 的三轮差为 +3.63%、+3.60%、+0.55%。

波动也影响原生基线和单线程：Linux c1/t20 为 4.547、3.957、5.385 Mops/s，波动 31.40%；KD c16/t1/observe/off 为 15.296、7.335、6.865 Mops/s，波动 **114.94%**。该单线程配置按最大值看 on/off 是 −19.64%，按中位数则是 +62.17%。样本均通过业务/排空检查，因此全部保留；异常波动原因未确定，也没有选择性补测或丢弃。全部原始样本见 [records.json](../../.tmp/spin-generic-unlock-20260923/performance/records.json)，36 配置及获选会话见 [summary.json](../../.tmp/spin-generic-unlock-20260923/performance/summary.json)。

## 冻结输入与比较边界

本轮以 `d9cdedd` 加已存在的工作区改动及统一解锁补丁冻结。既有 MCS 政策按每次实际队尾发布采样，不再采用历史冷队列深度门槛；这与[历史三轮报告](HISTORY.md#20260923-spin-three-round)的冻结源码不同。历史与本轮性能差不能归因于统一解锁一项；本轮 on/off 仍包含不同获取调用壳，两者也都使用新的通用解锁 provider，off 不是旧解锁实现的对照。

验证期间宿主还有并行编辑：运行器和 workload 去掉 on/off 选择，相关文档/测试也变化。guest ext4 输入始终是本轮已冻结、仍支持双壳的版本，没有在运行中同步这些编辑。`host-drift-during-validation.json` 列出 11 个后来变化的文件；解锁头文件、provider 与本轮直接相关单元输入未变化。**22 项运行器测试与本次成绩仅验证归档中的旧双壳 harness；本批次不覆盖后来宿主运行器/默认值变更，其验证以对应独立记录为准。** 334 个初始宿主文件清单、实际测试差异、各会话源码/ELF 清单共同标识本轮输入；`all_hashes_match` 指冻结输入一致，不表示结束时宿主所有文件仍与 guest 相同。

本轮未跑 2/3/8/16 线程性能、RCUHT、全量单元、SELFTEST、PMU 或真实 IRQ/NMI 压力。nested/early 为上述四场 spin 验证，不代表其他嵌套组合或 mutex JIT 已覆盖。批次 IRQ/preempt 恢复不等于逐操作验证；三轮范围显示本批次波动，不能单独证明统计显著性或微架构根因。

## 命令、环境和归档

全部构建、测试、模块及性能测量在 recovery guest 完成，内核 `6.1.159-kdclobber2`，Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；`nokaslr`、voluntary 抢占。快照 `pre_static_boot_20260915` 已查 monitor；40 个 vCPU 分别固定到宿主 CPU0–39，所选 CPU0–19 在同一 guest NUMA 节点。使用固定 venv、`LC_ALL=C`，显式设置恢复确认及快照标签；未重建内核。

本轮冻结运行器性能 argv 如下；三轮来自其当时的默认值。该命令仅用于重现归档 harness，不能直接套用于后来移除选项的源码。

```sh
python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --iterations 100000 --cachelines 1 16 --threads 1 4 20 \
  --spin-cold-fastpath on off --hotlock-mode observe adaptive \
  --output /root/kdlock-evidence/spin-generic-unlock-20260923/performance
```

`validate.py` 给 runner-tests/nested/early/performance 分别加 120/600/600/3600 秒 timeout；四项退出码均为 0，性能运行耗时 471.88 秒。完整 argv 在 `commands.json`，单元日志在 `unit.log`，全部 live 冻结材料保留在各子目录。

六组单元命令为：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_cold.py spin/test_spin_nondelegated.py spin/test_spin_preempt.py codegen/test_spin_paired_jit.py'
```

- guest：`/root/kdlock-evidence/spin-generic-unlock-20260923/`。
- [宿主完整归档](../../.tmp/spin-generic-unlock-20260923.tar.gz)，SHA256：`83ce82f28f5f5e2f48c43dc73830a309e9285c053e57fa9b8436ccd972676e7a`。
- [最终运行状态](../../.tmp/spin-generic-unlock-20260923/final-state.json)、[独立审计](../../.tmp/spin-generic-unlock-20260923/independent-audit.json)、[机器码核验](../../.tmp/spin-generic-unlock-20260923/codegen-review.md)；完整指令清单保存在 `codegen-review.json`。
