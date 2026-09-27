# 2026-09-28 NUMA 与 mutex 分阶段优化

本报告仅把已完成的阶段记为通过；mutex 三方基线及后续优化仍待验证。
目标是各配置 KD 暖峰值至少达到同期 TCLock 的 90%，并保护低线程性能。

## 环境与口径

recovery guest `6.1.159-kdclobber2`，live Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；身份核验通过。
monitor 确认 `pre_static_boot_20260915` 快照存在。guest ext4 源码逐文件哈希同步，
不修改内核。40 个 QEMU vCPU 分别固定在同号 host CPU；worker 0–35 和 collector 38
的频率上下限均为 2500000 kHz。guest 0–19 属于 node0，20–39 属于 node1。

性能均为 NUMA-on、1024 正文与独立 1024 扫描预算、prefetch=2、kernel UBSAN，
各 worker 预热 48000 次、测量 2 秒，排除前 300 ms 后选最高有效 300 ms 窗口。
三方各三轮，保留全段吞吐和每个 worker 进度；全部有效快慢样本均保留。
表中为 min / median / max，单位 Mops/s；完整 spread 在各 `summary.json`。

## 显式放置基线

基于 `cf3e631` 的锁实现，新增 `--cpus`，准备、预热、测量与汇总保持同一有序放置。
runner 的 41 项测试通过，包括实际 collector 冲突和按 CPU 列表隔离 Linux 分母。
45/45 场业务、上下文、JIT 和排空检查通过。

| workers / CPUs | Linux | TCLock | KD |
| --- | --- | --- | --- |
| 16 / 0–15 | 2.889 / 2.893 / 2.983 | 4.657 / 4.685 / 4.701 | 3.707 / 3.718 / 3.727 |
| 16 / 0–7,20–27 | 1.608 / 1.655 / 1.661 | 2.657 / 2.661 / 2.664 | 1.987 / 1.987 / 1.987 |
| 20 / 0–19 | 2.936 / 2.963 / 3.096 | 4.749 / 4.751 / 4.776 | 3.756 / 3.762 / 3.771 |
| 20 / 0–9,20–29 | 1.609 / 1.621 / 1.650 | 2.654 / 2.662 / 2.670 | 1.981 / 1.986 / 1.986 |
| 36 / 0–35 | 1.613 / 1.615 / 1.877 | 2.632 / 2.634 / 2.641 | 1.967 / 1.972 / 1.973 |

同节点已有差距；跨节点又使两种代理后端都明显变慢，不能把全部差距归因于 NUMA。

## 独立 PMU 诊断

先用真实 workload 外探针检查可用性：cycles、instructions、cache-references、
cache-misses、L1-dcache-loads、L1-dcache-load-misses 有非零计数；LLC-loads 和
LLC-load-misses 返回 `<not supported>`，不解释为零 miss。
随后 cycles、instructions、cache-misses、L1-dcache-load-misses 各单独运行三方
16/36 线程一轮，共 24 场。每场单事件、3 秒，仅计 measure 客户端及继承 worker，
不含准备/预热。全部报告 100% running time、非零 count/runtime、业务与排空通过。
这些是 `performance_result=false` 诊断，生成 `diagnostics.json`，不进入性能取优。

| event / completed operation | TCLock16 | KD16 | TCLock36 | KD36 |
| --- | ---: | ---: | ---: | ---: |
| instructions | 859 | 2111 | 2430 | 4232 |
| cache-misses | 0.0081 | 0.0091 | 3.6125 | 3.5248 |
| L1-dcache-load-misses | 35.71 | 41.47 | 36.76 | 43.29 |

各事件来自不同场次，包含等待代码，不是隔离正文或锁的成本；不据此计算精确正文 IPC。
通用 cache 事件不能区分远端 DRAM、cache-to-cache 或 NUMA 延迟，cycles 也不能作该证明。
KD 多出的总指令支持继续调查执行开销，但不单独证明任何某条指令的耗时贡献。

## 候选一：终态 clobber CALL 融合

已知终态 clobber unlock 在生成代码中先检查 COMPLETE 资格、目标锁/端点及 SP/IP/BP，
成功直接进入共同完成出口，避免在 waiter 栈上写入再读取虚拟返回地址。
任一失败（含普通 FULL 重入）保留逻辑寄存器，构造原 CALL 一次后进入 FULL。
非终态、未知端点与 legacy 翻译保持原路径；wrapper 目录、栈槽和双字输入 ABI 不变。

基础及相关 5 组通过：真实 wrapper 的 ABI1/ABI2、COMPLETE/拒绝、六种失败条件、
FULL/native 续点、IRQ 栈覆盖、正文 witness 与分支预算。
18/18 场 16/36 线程三方筛选通过，KD 全段 JIT 比例 99.897%–99.901%。

| workers | Linux | TCLock | KD |
| --- | --- | --- | --- |
| 16 | 2.860 / 2.897 / 2.937 | 4.692 / 4.699 / 4.701 | 3.744 / 3.754 / 3.762 |
| 36 | 1.587 / 1.642 / 2.450 | 2.643 / 2.643 / 2.644 | 1.988 / 1.989 / 1.992 |

KD 中位数较本次基线提高 0.96% / 0.87%，保留；峰值只达到同期 TCLock 的 80.02% / 75.36%，
尚未达到 90%。Linux36 的高峰也保留，不能用宽范围声称稳定性能。完整低线程回归待后续阶段。

## 候选二：省略未使用的 GS/task 导入

只扫描最终已降低的生成代码（含入口 guard），忽略源指令注释。
仅 GS 或仅逻辑 task 的镜像分别保留对应输入；未知宏/include、未闭合注释及没有需求信息的
独立构建保留两者。regular 与 clobber 入口使用相同策略，不挪动栈槽或输入 ABI。
6 组基础/相关测试通过，含实际 GS 读/写/RMW、逻辑 task 和真实汇编目录核对。
六个 live hash 镜像均确认没有两处未使用的导入，镜像 2172 字节。

18/18 场筛选通过：KD16 为 3.762 / 3.764 / 3.783，KD36 为 1.999 / 1.999 / 2.000。
较融合阶段中位数提高 0.27% / 0.51%；收益很小，不能由三轮范围宣称统计等价。
同期 TCLock16 为 4.686 / 4.705 / 4.715，36 为 2.645 / 2.648 / 2.651，90% 目标仍未达到。
Linux16 为 2.906 / 2.929 / 2.951，36 为 1.624 / 1.635 / 1.881；完整值与 spread 保留。

## 候选三：先检查耗尽的 NUMA 扫描预算

把预算零检查移到依赖 successor/next-next 读取之前，返回的候选、native 边界与
延迟远端链的优先交接不变。4 组基础/相关测试通过，包含 NUMA off/on、长队列、
五种 native 边界及毒化 successor 指针（预算零时必须完全不读取）的可执行检查。

首次 18 场与一次复查 18 场全部通过；表为 KD min / median / max Mops/s：

| workers | 首次 | 复查 |
| --- | --- | --- |
| 16 | 3.760 / 3.765 / 3.768 | 3.755 / 3.756 / 3.761 |
| 36 | 1.982 / 1.984 / 1.985 | 1.984 / 1.985 / 1.988 |

相对候选二，36 线程中位数分别下降 0.77% / 0.71%，小于 3% 拒绝阈值。
保留该有界读取改动，但不宣称它有吞吐收益；完整线程回归仍须检查。
复查 TCLock16 为 4.695 / 4.696 / 4.705，36 为 2.634 / 2.634 / 2.642，目标仍未达到。
两次 Linux36 的全部高低样本保留，不能删除快样本来缩小范围。

## 证据

guest 根目录 `/root/kdlock-evidence/`，各目录均冻结源码、二进制、命令、内核身份及会话日志：

- `numa-20260928-baseline-{standard,split16,split20}`：45 场基线。
- `numa-20260928-pmu-{cycles,instructions,cache-misses,L1-dcache-load-misses}`：24 场诊断及 driver 身份。
- `numa-20260928-fusion-screen`：18 场筛选。
- `numa-20260928-fusion-validation/unit.log`：5 组基础/相关测试。
- `numa-20260928-inputs-screen`、`numa-20260928-inputs-validation`：18 场及 6 组测试。

host 归档位于 `bench/.tmp/numa-20260928/spin-initial.tar.gz`，SHA256：
`8eccf12241b6f46fccc9d48db16a680cc4d4d00d2d57a862e4666720f9a2043d`。
这些原始大文件不随 Git checkout 分发。
输入优化的独立归档为 `spin-inputs.tar.gz`，SHA256：
`00c4b4fc12458330bd1444ded9401ca7951f6d4fc7edc20f43e2207231d966a7`。

扫描候选证据为 `numa-20260928-scan-{screen,recheck,validation}`；host `spin-scan.tar.gz`
SHA256 `ab51aea0a70166e2ea15c8dc63ce8a48ab69d31be3711eda96a823dabcfb946e`。
