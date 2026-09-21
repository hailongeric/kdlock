# 2026-09-21：去除热锁候选后的同期性能对照

比较上一轮两级候选版与当前直接哈希计数版，保留所有未提交修改。此次只构建、
测量和更新结果文档，没有再次修改锁实现。旧报告的吞吐不参与本次比值计算。

## 两组及测量条件

| 项目 | O：修改前两级候选版 | N：当前直接哈希计数版 |
| --- | --- | --- |
| 每 CPU/type 表 | 16 桶、6 候选，Space-Saving 排名/淘汰 | 256 桶、256 精确地址记录，满表不替换 |
| CPU 检查 | 每 1024 次，窗口 400 亿 TSC ticks | 相同 |
| 单锁检查 | 每 1024 次，窗口 25 亿 TSC ticks | count > 1024，即第 1025 次，窗口不变 |
| 锁统计 | score/error 与独立批次计数 | 仅该锁的独立 count/hot/时间戳 |
| 每 CPU 热表对象 | 576 字节 | 13376 字节 |

本次同时改变了表容量、计数/淘汰操作及单锁触发边界，不能把性能变化单独归因于
某个字段或分支。两版都保留原有 spin 入口、抢占、ticket、continuation 和 JIT 协议。

- recovery guest `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，快照 `pre_static_boot_20260915`。
- W=1、SELFTEST=0、NUMA=0 的独立 provider；共同 workload、client、daemon 和
  翻译器。执行 CPU 为 0 至 T−1，均在 NUMA node 0，保持原有 voluntary/nokaslr。
- observe 和 adaptive 分开运行，每种 **c1/c16 × t1/4/20 × O/N × 五轮 = 60 场**。
  奇数轮反序，每线程 100000 次；保留原有单 CPU 48000 次计时外预热和静置。
- 逐场验证完整业务结果、IRQ/preempt、实际 JIT 及排空，冻结源码和二进制。
  完整操作包含获取、正文、释放、锁外计算和循环，吞吐不是独立锁获取延迟。
- observe 固定准入但保留统计；adaptive 包含各 CPU 自然形成热值的影响。
  单线程无竞争时可为 NO_JIT，不能把正确完成的自执行样本写成实际代理通过。

本轮没有重跑 TCLock/Linux，也没有测多锁碰撞流或满表场景的性能。原有满表
功能与真实 JIT 验证见 [tests](../../../tests/README.md#hotlock-direct-validation)。

## 同期结果

**120/120 场通过，共 100000000 次操作，全部正常排空，无内核错误。**
observe/adaptive 各 40/40 场竞争会话有实际 JIT；各 20 场单线程为 NO_JIT，作为
自执行性能样本保留，不算实际代理通过。最终源码/ELF 哈希与宿主代码一致。

五轮完整操作吞吐中位数，单位 Mops/s；变化为 `(N/O−1)×100%`。

| 模式 | cacheline | 线程 | 旧候选 O | 直接哈希 N | 变化 |
| --- | ---: | ---: | ---: | ---: | ---: |
| adaptive | 1 | 1 | 5.746 | 6.025 | +4.86% |
| adaptive | 1 | 4 | 2.004 | 1.990 | -0.68% |
| adaptive | 1 | 20 | 4.946 | 4.928 | -0.36% |
| adaptive | 16 | 1 | 5.872 | 5.748 | -2.10% |
| adaptive | 16 | 4 | 1.709 | 1.717 | +0.52% |
| adaptive | 16 | 20 | 4.579 | 4.579 | +0.01% |
| observe | 1 | 1 | 5.907 | 6.074 | +2.83% |
| observe | 1 | 4 | 1.996 | 1.983 | -0.65% |
| observe | 1 | 20 | 5.001 | 4.995 | -0.12% |
| observe | 16 | 1 | 5.911 | 5.693 | -3.68% |
| observe | 16 | 4 | 1.733 | 1.670 | -3.65% |
| observe | 16 | 20 | 4.765 | 4.757 | -0.16% |

默认 adaptive：四线程 c1/c16 为 −0.68%/+0.52%，二十线程为 −0.36%/+0.01%，
本批接近持平；单线程 c1 提高 4.86%、c16 下降 2.10%。没有一致的整体吞吐提升。
二十线程的 JIT 比例两版均约 97.8%；四线程 c1/c16 的 O 为 46.39%/48.02%，
N 为 50.55%/48.81%，代理比例变化并没有转化为明显的吞吐提高。

observe：二十线程约下降 0.1%–0.2%，c16 四线程下降 3.65%；单线程方向混合。
这组测量保留统计但固定准入，不能拿 adaptive 的局部改善来掩盖它的回退。
全部五轮原始样本保留于 `audit.json` 和各模式 `records.json`；不剔除慢样本、不补测择优。

## 结果解释范围

该负载反复访问同一个业务锁，不能展示超过六把锁时新表的覆盖优势，也不能量化
256 个同桶地址或长期表满的成本。地址精确匹配和满表不覆盖已由上一轮功能测试
验证，本轮不重复执行那组探针。性能运行中保留实际 JIT、业务结果和排空验收。

没有新增 perf 硬件计数器采样，不能将几个百分点的变化精确归因于某条指令。
这是单 NUMA guest、每配置五轮短批次结果；完整原始样本随归档保留。

## 原始证据

Guest 目录：`/root/kdlock-evidence/hotlock-direct-benchmark-20260921/`。
[完整归档](../../.tmp/hotlock_direct_benchmark_20260921/hotlock-direct-benchmark-20260921.tar.gz)
SHA256：`69559e28449a58e8c5f10a2aed6968a70d7c2f34b08734b1453b8bf9fb458e7c`。
同目录 `offline-audit.json` 记录宿主只读一致性核验；不执行归档中的代码。

归档保存 O/N 的独立源码、构建日志、ELF/反汇编/布局、共同 workload 和可执行文件、
两组 plan/records/summary/frozen hashes、120 份 kernel.log 以及最终 `audit.json`。
`host-code-sha256.json` 证明已测 N 与本轮宿主实现一致；此轮没有修改生产代码。

实际运行入口为归档中的 `compare.py`，两次分别使用
`--name observe --hotlock-mode observe` 和 `--name adaptive --hotlock-mode adaptive`，
其余均为 `--versions O N --cachelines 1 16 --threads 1 4 20 --repeats 5 --iterations 100000`，
指定当前 kdclobber2 source 和 mutex-clobber2-20260919 baseline。前置隔离构建由
`build.py` 完成，所有运行只发生在 guest。复现需新证据目录并重新核验环境，
不能直接覆盖这批输出或将其他版本样本合并进来。
