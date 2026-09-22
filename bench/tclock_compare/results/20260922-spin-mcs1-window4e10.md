# 2026-09-22：CPU 窗口400亿、spin MCS阈值1重测

基于`a6ae430`，按用户要求仅调整两个生产参数：

| 参数 | 修改前 | 本轮 |
| --- | ---: | ---: |
| `KD_HOTLOCK_CPU_WINDOW` | 4000000000 | 40000000000 TSC ticks（400亿） |
| `KD_HOTLOCK_SPIN_MCS_INTERVAL` | 4 | 1 |

每次合格spin MCS事件都检查CPU热度，时间差严格小于400亿才判热，等于边界或时间倒退判冷。
窗口由spin/mutex CPU采样共用；mutex仍每1024次入口检查，单锁仍第33次检查25亿窗口。
冷队列门槛`spin_hot_min_queue`仍为4：冷CPU需观察到至少4个已链接节点，才能产生一次合格事件。
设为1的是MCS采样次数，并非队列长度。新壳、per-CPU cookie、寄存器clobber与锁协议未改。

## 本轮单次结果

与上一轮相同：c1/c16 × 1/2/3/4/20线程 × Linux/TCLock/KD两模式两壳，
每配置一轮、每线程100000次，**60/60通过，3600万次操作完成并排空**。
准备、翻译及单CPU 48000次预热不计时。每格为 **Mops/s / 完整操作ns/op**。

on：`cold_clobber`新壳、冷捷径1、队列门槛4；off：同一当前源码的保留`clobber`壳、
冷捷径0、有效队列门槛0。所有本轮KD组都使用CPU窗口400亿/MCS阈值1，未运行旧版KD。

| cacheline | 线程 | Linux | TCLock | observe off | observe on | adaptive off | adaptive on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 17.081 / 58.54 | 14.947 / 66.91 | 8.365 / 119.55 | 14.369 / 69.59 | 9.991 / 100.09 | 13.350 / 74.91 |
| 1 | 2 | 2.722 / 367.37 | 4.778 / 209.29 | 2.586 / 386.76 | 2.202 / 454.21 | 2.030 / 492.59 | 2.190 / 456.70 |
| 1 | 3 | 3.513 / 284.68 | 2.479 / 403.41 | 1.693 / 590.73 | 2.677 / 373.58 | 1.595 / 627.04 | 2.710 / 369.01 |
| 1 | 4 | 3.672 / 272.32 | 2.947 / 339.37 | 1.802 / 554.96 | 1.795 / 557.12 | 1.870 / 534.67 | 1.816 / 550.73 |
| 1 | 20 | 4.180 / 239.24 | 4.973 / 201.09 | 4.046 / 247.15 | 3.803 / 262.98 | 4.175 / 239.51 | 3.823 / 261.56 |
| 16 | 1 | 12.644 / 79.09 | 10.906 / 91.69 | 8.234 / 121.44 | 12.334 / 81.07 | 9.168 / 109.08 | 10.583 / 94.49 |
| 16 | 2 | 1.423 / 702.90 | 2.002 / 499.47 | 1.547 / 646.39 | 1.572 / 635.94 | 1.528 / 654.41 | 1.676 / 596.76 |
| 16 | 3 | 2.055 / 486.58 | 1.905 / 524.86 | 1.288 / 776.40 | 1.927 / 518.99 | 1.312 / 762.48 | 1.936 / 516.51 |
| 16 | 4 | 2.106 / 474.72 | 2.251 / 444.23 | 1.547 / 646.34 | 1.520 / 657.82 | 1.552 / 644.42 | 1.597 / 626.29 |
| 16 | 20 | 2.225 / 449.35 | 3.257 / 307.06 | 3.945 / 253.50 | 3.692 / 270.85 | 3.939 / 253.85 | 3.825 / 261.44 |

本轮新壳相对同期保留壳的吞吐变化：

| cacheline | 线程 | observe on/off | adaptive on/off |
| --- | ---: | ---: | ---: |
| 1 | 1 | +71.78% | +33.61% |
| 1 | 2 | -14.85% | +7.86% |
| 1 | 3 | +58.13% | +69.92% |
| 1 | 4 | -0.39% | -2.92% |
| 1 | 20 | -6.02% | -8.43% |
| 16 | 1 | +49.79% | +15.43% |
| 16 | 2 | +1.64% | +9.66% |
| 16 | 3 | +49.60% | +47.62% |
| 16 | 4 | -1.74% | +2.89% |
| 16 | 20 | -6.40% | -2.90% |

单线程各组新壳均提高，三线程提高47.62%–69.92%。两线程并非一致改善，
c1 observe下降14.85%；四线程在−2.92%到+2.89%之间。
二十线程observe的c1/c16分别下降6.02%/6.40%，adaptive分别下降8.43%/2.90%。
仍存在超过5%的竞争退化，冷捷径及新壳保持默认关闭；新参数按用户要求保留。

## 与上一轮的区别

以下只比较[上一轮](20260922-spin-cold-clobber-queue.md)与本轮各自唯一测量的20线程新壳，
属于不同批次，不能视为稳定收益或把全部差异归于两个参数：

| 配置 | 上轮新壳 Mops/s | 本轮新壳 Mops/s | 变化 |
| --- | ---: | ---: | ---: |
| c1 observe | 3.785 | 3.803 | +0.46% |
| c1 adaptive | 3.920 | 3.823 | −2.47% |
| c16 observe | 3.718 | 3.692 | −0.70% |
| c16 adaptive | 3.757 | 3.825 | +1.82% |

本轮没有出现一致的20线程提速，也没有消除新旧调用壳的差距。
单线程没有MCS采样，不能把单线程短批次变化直接解释为这两个热度参数的收益。
本轮不追加重复轮次，不跨批次取优，也不以历史PMU代替当前测量。

## 验证与环境

- 基础2组及热度定向1组通过，25个错误变体均检出。验证首次合格事件、每次更新、
  400亿严格边界、倒退/零时间、冷热切换、单锁计数不被持续热CPU重置、mutex共用窗口，
  以及队列门槛4、非task丢样、跨CPU隔离和已有pin复用。
- 40场KD中20场有实际JIT，共18073665个计时正文。新壳1/2/3线程的12场均为零JIT，
  明确标为`NO_JIT_COLD`。KD四/二十线程16场均实际执行JIT；二十线程比例99.56545%–99.8626%。
- 所有会话业务增量、worker完成/绑核/error、IRQ/preempt、source/frame/writer退休及排空通过；
  spin/exec invariant、overflow、native fallback、JIT not-ready均为0，无匹配内核错误。
  当前少线程oracle允许plain 2/3线程合法自执行；本轮未出现上轮的验收脚本失败。
- normal provider W=1构建通过，仍有11条既有objtool警告及Perl locale警告。
  只运行基础及直接相关采样测试和本次cacheline矩阵，未重跑nested/early、RCUHT或PMU。
- 全部编译、测试、模块加载在recovery guest。加载参数`mutex_jit=1`，本轮负载仅spin。
  内核`6.1.159-kdclobber2`，Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，
  ext4/nokaslr/voluntary；快照`pre_static_boot_20260915`，vCPU0..39绑定host CPU0..39。
  未修改guest内核；结束后无worker、daemon、workload或后端残留。
- 254份冻结源码和9项二进制SHA256逐份核对通过；运行结束时源码仍与冻结清单一致。
  结果报告与入口文档在结束后更新，不改写已冻结证据。

## 命令与证据

```sh
make -C tests/unit run PY_TESTS=infrastructure/test_hotlock_sampling.py

KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  timeout --kill-after=10s 950s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --cachelines 1 16 --threads 1 2 3 4 20 \
  --hotlock-mode observe adaptive --spin-cold-fastpath on off --spin-hot-min-queue 4 \
  --repeats 1 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spin-mcs1-window4e10-20260922/performance
```

guest证据为`/root/kdlock-evidence/spin-mcs1-window4e10-20260922/`；
宿主保存[summary](../../.tmp/spin-mcs1-window4e10-20260922/performance/summary.csv)、
[独立核对](../../.tmp/spin-mcs1-window4e10-20260922/audit.json)、
[完整归档](../../.tmp/spin-mcs1-window4e10-20260922.tar.gz)。归档SHA256：
`1ee6a571e26ced2aaa9cb4810a0210e3554f2640fe342115bdb24eb54c140f1a`。
