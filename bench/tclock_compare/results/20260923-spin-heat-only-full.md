# 2026-09-23：仅CPU热值分流的完整重测

生产实现为 `db42cf4`。`KD_SPIN_DIRECT_LOCK` 在pin后仅判断现有CPU热值，
已删除调用端的 `kd_spin_cold_fastpath` / `kd_spin_delegate` 判断。
本次更新执行路径、性能计划和运行文档，按用户要求重新运行基础/相关单元及完整三方矩阵，
不修改生产实现、参数或验收规则。

**六组单元通过；84/84场性能会话通过，64800000次计时操作完成并排空。**
矩阵为1/16 cacheline × 1/2/3/4/8/16/20线程 × Linux/TCLock/KD两模式两壳，
每配置一轮、每线程100000次。准备、翻译及48000次单CPU预热不计时。

on在编译时选择热度分流壳，并加载 `spin_cold_fastpath=1`、队列门槛4；
off选择同一当前源码的保留clobber壳，并加载采样开关0、有效门槛0。
模块开关只控制provider采样，不能关闭已编译配对壳的热度分支；provider仍控制代理准入。
CPU窗口400亿TSC、spin每次合格MCS事件采样、单锁第33次检查均保持不变。

## 完整单轮结果

每格为 **Mops/s / 完整操作ns/op**，不是独立lock延迟。

| cacheline | 线程 | Linux | TCLock | observe off | observe on | adaptive off | adaptive on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.270 / 57.90 | 14.438 / 69.26 | 9.020 / 110.87 | 14.046 / 71.20 | 9.119 / 109.66 | 12.669 / 78.93 |
| 1 | 2 | 2.465 / 405.71 | 4.883 / 204.81 | 1.982 / 504.60 | 1.847 / 541.54 | 1.817 / 550.30 | 2.101 / 476.00 |
| 1 | 3 | 3.708 / 269.72 | 2.488 / 401.91 | 1.695 / 589.83 | 2.607 / 383.65 | 1.900 / 526.29 | 2.622 / 381.43 |
| 1 | 4 | 3.598 / 277.94 | 3.146 / 317.82 | 1.807 / 553.49 | 1.794 / 557.31 | 1.819 / 549.76 | 1.936 / 516.54 |
| 1 | 8 | 3.953 / 252.98 | 4.403 / 227.13 | 3.115 / 321.02 | 3.202 / 312.30 | 3.208 / 311.68 | 3.083 / 324.36 |
| 1 | 16 | 3.836 / 260.70 | 5.036 / 198.59 | 3.978 / 251.37 | 3.739 / 267.46 | 3.941 / 253.72 | 3.761 / 265.87 |
| 1 | 20 | 4.018 / 248.91 | 5.231 / 191.17 | 4.026 / 248.39 | 3.911 / 255.69 | 4.018 / 248.89 | 3.787 / 264.03 |
| 16 | 1 | 12.827 / 77.96 | 11.760 / 85.03 | 8.068 / 123.94 | 11.565 / 86.47 | 8.037 / 124.43 | 11.963 / 83.59 |
| 16 | 2 | 1.404 / 712.23 | 1.989 / 502.69 | 1.593 / 627.57 | 1.532 / 652.69 | 1.305 / 766.08 | 1.468 / 681.28 |
| 16 | 3 | 1.995 / 501.21 | 2.188 / 456.98 | 1.253 / 798.17 | 1.913 / 522.73 | 1.291 / 774.57 | 1.842 / 543.02 |
| 16 | 4 | 2.154 / 464.33 | 2.413 / 414.38 | 1.547 / 646.60 | 1.532 / 652.82 | 1.527 / 654.89 | 1.544 / 647.83 |
| 16 | 8 | 2.339 / 427.47 | 3.115 / 321.04 | 3.110 / 321.56 | 3.184 / 314.11 | 3.114 / 321.10 | 3.103 / 322.25 |
| 16 | 16 | 2.346 / 426.27 | 3.372 / 296.57 | 4.050 / 246.88 | 3.719 / 268.92 | 3.894 / 256.84 | 3.668 / 272.66 |
| 16 | 20 | 2.478 / 403.59 | 3.284 / 304.50 | 3.928 / 254.60 | 3.681 / 271.68 | 3.944 / 253.53 | 3.737 / 267.59 |

## 同期on/off差异

同一热度模式下，on相对off的吞吐变化由未舍入原始值计算：

| cacheline | 线程 | observe on/off | adaptive on/off |
| --- | ---: | ---: | ---: |
| 1 | 1 | +55.72% | +38.92% |
| 1 | 2 | -6.82% | +15.61% |
| 1 | 3 | +53.74% | +37.98% |
| 1 | 4 | -0.69% | +6.43% |
| 1 | 8 | +2.79% | -3.91% |
| 1 | 16 | -6.02% | -4.57% |
| 1 | 20 | -2.86% | -5.74% |
| 16 | 1 | +43.33% | +48.85% |
| 16 | 2 | -3.85% | +12.45% |
| 16 | 3 | +52.69% | +42.64% |
| 16 | 4 | -0.95% | +1.09% |
| 16 | 8 | +2.37% | -0.36% |
| 16 | 16 | -8.19% | -5.80% |
| 16 | 20 | -6.29% | -5.25% |

本轮单线程提高38.92%–55.72%，三线程提高37.98%–53.74%。两线程结果混合：
observe下降3.85%–6.82%，adaptive提高12.45%–15.61%，on/off均无实际JIT。
十六线程下降4.57%–8.19%，二十线程下降2.86%–6.29%。运行器默认仍选off。

on/off同时改变调用壳和冷队列策略，不能将差异单独归于删除两个开关判断。
[之前完整矩阵](20260923-spin-c-if-full.md)保留原样，不跨批次取优或拼接。
上轮两线程全部退化的模式本轮没有重复，但每配置只有一个样本、off基线也发生变化，
不能据此认定两线程问题已解决或建立稳定性能结论。

## 单元、JIT与排空

- 基础2组及cold/非代理MCS/paired JIT/热度采样4组全部通过，25项错误变体检出。
  ABI fixture验证真实GS读取、双CPU、冷热路径、活跃寄存器、精确续点、嵌套及提前解锁；
  真实wrapper覆盖COMPLETE、入口拒绝和FULL/native续跑。
- 原生MCS fixture完成1/2/3/8线程门槛4及8线程门槛0，共110万次操作。
  2/3线程分别实际入队68761/149429次而保持冷态；8线程门槛4记录399911次CPU样本。
  独占、pin、node及在途计数配平，确定性热度检查覆盖门槛1..16。
- 56场KD中36场实际JIT，共37012941次计时正文。on的1/2/3线程12场为
  `NO_JIT_COLD`，off的两线程4场为`NO_JIT_LOW_CONTENTION`，off的单线程4场为`NO_JIT`。
  零JIT自执行样本通过业务检查，但不计为JIT正例。
- 所有32场4/8/16/20线程KD均有实际JIT，各参与CPU终态cpu_hot/lock_hot为1、role为DONE。
  二十线程8场JIT比例99.2206%–99.8628%。spin/exec invariant、overflow、
  jit_not_ready、native_fallback、jit_disabled及waiters均为0。
- 所有84场业务增量、worker完成/绑核/error、批次IRQ/preempt恢复及排空通过；
  无匹配内核/daemon错误。KD source退休后modules/frames/writers均为0，TCLock quiescent=1。
  最终空闲检查通过，无workload、daemon或后端/provider残留。
- provider、daemon和四种caller构建通过，保留11条既有objtool警告及Perl locale警告。
  全部编译和测试在guest，provider参数`mutex_jit=1`，本轮负载仅spin；未修改内核。
  未重跑全量单元、nested/early、RCUHT、PMU、SELFTEST或真实IRQ/NMI压力。
- 341份host跟踪文件、257份冻结源码和9项二进制在运行后逐份匹配。
  独立审计再次核对84场原始数据、发布图像、退休日志及摘要计算；caller导入表和反汇编
  均引用现有CPU gate，且没有两个已删除的调用端策略变量引用。

## 命令与证据

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_cold.py spin/test_spin_nondelegated.py codegen/test_spin_paired_jit.py infrastructure/test_hotlock_sampling.py'

KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  timeout --kill-after=10s 1800s python3 -u bench/tclock_compare/run.py \
  --backends native tclock kdlock --cachelines 1 16 --threads 1 2 3 4 8 16 20 \
  --hotlock-mode observe adaptive --spin-cold-fastpath on off --spin-hot-min-queue 4 \
  --repeats 1 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spin-heat-only-full-20260923/performance
```

两条命令退出0。内核`6.1.159-kdclobber2`、Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，ext4/nokaslr/voluntary；
monitor确认`pre_static_boot_20260915`快照，40个vCPU各自仅允许对应host CPU0..39。
文档流程修正先于冻结测试；本报告和结果入口在测试/独立审计完成后更新。

guest证据：`/root/kdlock-evidence/spin-heat-only-full-20260923/`。
宿主[CSV](../../.tmp/spin-heat-only-full-20260923/performance/summary.csv)、
[独立审计](../../.tmp/spin-heat-only-full-20260923/independent-audit.json)、
[最终状态](../../.tmp/spin-heat-only-full-20260923/final-state.json)、
[完整归档](../../.tmp/spin-heat-only-full-20260923.tar.gz)。归档SHA256：
`6205210aa8ee5299a26d8e0075cea9665c81caf10212612e7728168411f40bf4`。
