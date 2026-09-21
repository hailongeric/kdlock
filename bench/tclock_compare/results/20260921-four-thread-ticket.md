# 2026-09-21：四线程 ticket 路径优化

基于 `644f2317f6cbedb3265df63572eb6e9d8fe080c7` 的三处生产文件改动。
同期基线和优化版各 60/60 场通过，各完成 50000000 次操作；两组各有
20/20 场竞争 KD 的真实 JIT 正文证据。四线程 c1/c16 中位吞吐提高
**9.4% / 14.0%**，但仍只有同期 TCLock 的 **68.1% / 78.4%**。
20 线程变化 +0.3% / −0.1%，不宣称长批次路径获得明显提升。

## 原因与证据

当前基线的四线程 c1/c16：约 97.0% / 97.8% 操作进入 slowpath，JIT 占比
57.9% / 58.2%，每个 combiner 平均执行的 JIT 正文数的五次中位数仅为
1.99 / 1.98。20 线程对应批长约 837 / 857，JIT 占比均超过 99.7%。
这些数来自原有 `kd_spin lock stats` 与正文计数；准备阶段单线程没有这些
排队事件。未就绪拒绝为零，不能把本次差距解释为 JIT 没有准备好。

两者都使用 fast/pending/MCS，但 TCLock 在队首原生执行时没有 KD 的稳定
origin ticket。KD 旧路径在 pending 前 reserve；进入 MCS 后，队首已 claim，
公共入口却再次确认 OWNED；claim/reclaim 与 release 内部还各有两轮 guard。
短批次下，这些固定工作由很少的正文摊销。KD 还保留 continuation/frame、
wrapper、JIT 准入和恢复等工作，而 TCLock 切真实 waiter 栈执行原生正文。
本轮根据生产路径计数和源码定位并做端到端前后测量，没有 PMU/IP 采样，
不声称测出了各项独立周期数或 cache-to-cache 转移数。

## 实现

1. **延迟根 ticket。** 顶层 fast/pending 成功均使用已有 per-CPU fast owner；
   进入 MCS 分支才 reserve ticket。嵌套请求仍先 reserve，不能覆盖外层 owner。
2. **合并 ticket guard。** claim/reclaim 和 release 的身份校验及状态提交各
   在一次 guard 内完成；中间没有物理获取、释放或阻塞等待，不再先放开再取回。
3. **避免重复 claim。** 正常 slowpath 返回已 claim/reclaim，公共入口直接返回；
   节点和 continuation 容量回退也先 claim，再遵守相同返回契约。

普通队首自执行的 ticket guard 获取由 7 次降为 4 次；顶层 pending 自执行
由 6 次降为 0 次。这里按未提前释放的成功路径计算，不包含其他协议锁，
也不是所有请求的平均成本。基线 pending/fast 所占比例很小，不能把全部收益
单独归因于延迟 reserve；三项联合测量，没有单项消融成绩。

CPU/task/generation、状态及 native borrow 检查保留；物理释放仍恰好一次，
提前释放/重新获取沿用原 ticket，frame/continuation 退休顺序未改变。
每次真实获取的入口 preempt pin 仍只配对一次。没有新增存储、改变恢复汇编、
关闭 JIT、删除正文 witness，或修改 TCLock、guest 内核、mutex 互斥协议。
路径与对象说明见 [EXECUTION_PATHS](../../spin_cacheline/EXECUTION_PATHS.md)，
协议见 [locking](../../../docs/design/locking.md#41-native-lock-and-private-queue)。

## 同条件结果

吞吐为完整 lock/body/unlock/锁外工作吞吐，单位 **Mops/s**，取五次中位数。

| cacheline | 线程 | KD 优化前 | KD 优化后 | KD 变化 | TCLock 前 / 后 | 优化后 KD/TCLock |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 6.248 | 6.160 | -1.4% | 13.661 / 13.880 | 0.444× |
| 1 | 4 | 1.825 | 1.996 | +9.4% | 2.969 / 2.931 | 0.681× |
| 1 | 20 | 4.965 | 4.978 | +0.3% | 5.016 / 4.987 | 0.998× |
| 16 | 1 | 6.102 | 6.176 | +1.2% | 12.166 / 11.167 | 0.553× |
| 16 | 4 | 1.534 | 1.748 | +14.0% | 2.223 / 2.230 | 0.784× |
| 16 | 20 | 4.775 | 4.773 | -0.1% | 3.334 / 3.315 | 1.440× |

四线程 c1/c16 优化后 JIT 占比为 49.1% / 50.1%，每批正文仍约 2 个。
原生自执行路径变快后，代理比例下降与总吞吐提高同时出现；不能只把 JIT
占比提高当成性能目标。20 线程仍约 99.8% JIT。

全部样本保留，没有剔除或失败后重试。单线程存在高值，例如 KD c1 前后各有
一次 12.108 / 12.448 Mops/s，其余样本主要在 5.8–6.6；不将单线程差值解释为
确定收益。两阶段顺序执行，各阶段 TCLock/KD 正反交替；没有交错装载旧/新 KD，
也不保证 guest CPU 独占宿主物理核。四线程 TCLock 中位值前后约 −1.3% / +0.3%，
明显小于本轮 KD 改善，但仍应保留 VM 波动这一测量边界。

环境沿用 recovery/ext4、40 vCPU、CPU 0 起绑核（测量均在 NUMA node 0）、
`6.1.159-kdclobber2`、voluntary、nokaslr，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。加载前确认
`pre_static_boot_20260915` 快照。每线程 100000 次，1/16 cacheline，1/4/20
线程；observe、spin_delegate=on、批次上限 1024，JIT timing 关闭。
单 CPU 48000 次预热及翻译准备不计时，计时前停止 daemon/翻译者。
TCLock ELF 前后完全相同，工作负载、统计及 JIT 验收条件均未改变。
本轮未重测 Linux，不与历史 Linux 数值计算比率。

两组使用同一命令，仅输出目录和上述三处生产文件不同：

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
LC_ALL=C timeout --kill-after=10s 1800s python3 bench/tclock_compare/run.py \
  --cachelines 1 16 --threads 1 4 20 --backends tclock kdlock \
  --repeats 5 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/four-thread-20260921/optimized
```

宿主 SSH 另有外层 timeout。先运行 `baseline`，完成并排空后同步三个生产文件
及两个 fixture，再运行回归与 `optimized`；测量中不修改 guest 冻结输入。
宿主原有未提交文档改动保留，不进入性能因果比较。

## 验证与限制

基础及直接相关单元检查 8/8 通过，plain/nested/early 和关闭代理的原生对照
各 400000 操作通过；前三场有真实 JIT，后者为零 JIT 控制组。详细计数见
[测试记录](../../../tests/README.md#four-thread-ticket-validation)。120 场性能测试
核对业务、完成次数、CPU 亲和性、IRQ/preempt、内核错误和排空；没有本轮
BUG/Oops/WARNING，最终 worker/daemon 退出、测试模块全部卸载。

普通生产 provider 和私有观察 provider 的 guest `W=1` 构建通过，保留既有
换栈 objtool 告警。最终观察 ELF：node 128 B / align 64，通知偏移 64/65；
continuation 768 B / align 64，frame 偏移 32，regs 偏移 104；ticket 48 B。
结构和汇编源未改动，`layout.txt` 及前后 provider 反汇编保留以供复核。

本轮未覆盖 8/16 线程性能、adaptive/冷准备、跨 NUMA、多锁性能、mutex JIT
或远端 native 强制并发时序；没有全量回归。四线程剩余差距仍包括逐请求现场、
入口/退出和 JIT 代码成本，本轮没有分别量化。不能宣称已达到 TCLock 性能。

## 证据

完整 guest 目录：`/root/kdlock-evidence/four-thread-20260921/`。含 baseline / optimized
的冻结源码、ELF、JIT 生成物、环境与逐场日志，四个功能场景、unit/build 日志、
对象布局、差异及 `audit.json`。基线可执行输入与 `644f231` 一致；冻结差异只有
三个生产文件、对应观察副本及 manifest，未改变 benchmark 或 TCLock。

[离线审计与全部样本](../../.tmp/four_thread_20260921/audit.json)、
[最终对象布局](../../.tmp/four_thread_20260921/layout.txt)。原始大型材料不提交 Git。

[完整归档](../../.tmp/four_thread_20260921/four-thread-20260921.tar.gz)，guest 同时保存
`/root/kdlock-evidence/four-thread-20260921.tar.gz`。SHA256：
`13b5986fbb88e308f4d94493634526375b05b5ef4185c82bd4420628106ed09e`。
