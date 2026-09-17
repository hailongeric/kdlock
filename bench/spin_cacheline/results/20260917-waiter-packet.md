# 2026-09-17：Waiter 寄存器包与原子 frame lease

4 个配置、16/16 会话通过数据、实际 JIT 和排空检查：1/16 cacheline，4/20
线程，每线程 100,000 次，每配置两对，原生/kdlock 交替顺序，CPU 0–19、NUMA 0。
对比上一版 [frame 单锁路径精简](20260917-frame-fast.md)，20 线程两点分别提高
**20.3%/11.9%**；4 线程两点分别下降 **2.4%/1.7%**，本轮未观察到该档收益。

实现基于 `f190b65` 加本轮修改：waiter 发布前准备寄存器包，普通单锁 root
就地执行，省去 node→frame→node 两次完整复制；首次复杂出口才保存独立包。
source frame get/put 用同一原子字维护关闭位与计数，移除每次代理的两次全局
source irqsave，模块引用和退休排空继续保留。复用互斥阶段的 continuation SP
存储，frame/context 保持 656/5264 字节，没有新增每请求分配。

## 结果

吞吐单位为 Mops/s；主指标仍为 kdlock 最佳有效吞吐 / 原生有效吞吐中位数，
JIT 占比取同一个最佳会话。旧值为上述上一版相同四点的最佳吞吐。

| cacheline | 线程 | 原生中位 | 旧 kdlock 最佳 | 新 kdlock 最佳 | 新/旧变化 | 新 best/median | 最佳会话 JIT 占比 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 3.079 | 0.725 | 0.708 | -2.4% | 0.2299 | 56.36% |
| 1 | 20 | 3.232 | 0.855 | 1.029 | +20.3% | 0.3183 | 99.87% |
| 16 | 4 | 1.993 | 0.632 | 0.622 | -1.7% | 0.3118 | 58.73% |
| 16 | 20 | 1.940 | 0.850 | 0.951 | +11.9% | 0.4903 | 99.80% |

20 线程仍慢于原生，4 线程没有测得提升。各组只有两个样本，两版之间重启过 VM，
宿主物理 CPU 独占与频率未控制；这是整条执行路径的测量，不能拆分为复制与锁
各自的周期收益，也不能外推到其他线程/cacheline 配置。4 线程约 56%–59% 的
操作为 JIT，20 线程约 99.8%；不能把混合总吞吐当成单次 JIT 延迟。

共完成 **19,200,000** 次操作，测量期 JIT 正文 **8,914,146** 次；8 个原生、
8 个实际 JIT 会话，最长测量批次 **2.128 秒**。负载 C/h/inc 哈希与上一版相同，
两组仍执行相同的 4 组锁外乘加，没有在热循环插入调度或额外等待。

## 运行与验证

recovery guest `6.1.159-kdstatic2`，Build ID
`460d77502af4709a0cca794b322cedc20c2cc478`，nokaslr、voluntary，
`bench_quiet=1 jit_timing=0`；内核源码/build/live 身份和恢复快照
`pre_static_boot_20260915` 均已核对。运行前重新构建 provider、daemon、负载
及客户端。专用 provider 的 per-CPU 节为 8064 字节，与上一版相同。

最终扫描的源码、二进制、boot ID 均未变，全部正常 retire/卸载，内核日志无 fault。
宿主独立复算 16 个会话的计数、CPU 放置、正文差值、聚合及最佳值，核对 186 项
冻结源码及 24 项生成映像哈希；61 个生产源码/头文件与宿主一致。
基础及相关 **12 项 unit、6 项 live** 通过，详见
[本轮功能验证](../../../tests/README.md#waiter-packet-validation)。未运行全量套件。

早期独立指针将 frame 增加 8 字节，专用 provider 的 per-CPU 节增至 8128 字节，
首个 kdlock 会话加载因预留块空间不足返回 ENOMEM，尚未测量 JIT。本轮改用字段
复用恢复原大小，再重启同一现有实验内核并以 `-r2` 新目录完整运行。失败的
`spin-waiter-packet-20260917` 目录保留，未混入本表；SELFTEST 空 RSP 的早期
故障与修复同样独立记录在上述功能验证中。此前 mode-4 soft lockup 未重跑或修复。

```sh
# 确认快照后，在 guest 运行；宿主 SSH 外层另有限时。
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 \
KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 timeout 840s \
  python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 16 --threads 4 20 --cpus 0-19 \
  --iterations 100000 --repeats 2 \
  --output /root/kdlock-evidence/spin-waiter-packet-20260917-r2
```

- [汇总 CSV](/tmp/kdlock-waiter-packet-20260917/evidence/spin-waiter-packet-20260917-r2/summary.csv)、[逐会话 CSV](/tmp/kdlock-waiter-packet-20260917/evidence/spin-waiter-packet-20260917-r2/raw.csv)。
- [独立复算与前次比较](/tmp/kdlock-waiter-packet-20260917/audit.json)、[最终身份/排空检查](/tmp/kdlock-waiter-packet-20260917/evidence/spin-waiter-packet-20260917-r2/postflight.json)。
- guest 持久证据：`/root/kdlock-evidence/waiter-packet-20260917/`，以及上述失败与成功的两个 bench 目录。
- [完整归档](/tmp/kdlock-waiter-packet-20260917/evidence.tar.gz)，SHA256：
  `3f297ec5b52a09d61553836dcabbb133ed448b0351fc43a1f0abe74ca8623dc5`。
  宿主可读副本仅提取普通文件和目录，原始符号链接保留在归档中供审计。

本结果页及导航在测量结束后补写；冻结的说明文件属于各次运行开始时的版本。
