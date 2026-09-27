# 2026-09-28 NUMA 与 mutex 分阶段优化

本报告仅把已完成的阶段记为通过；已建立 mutex 三方初始基线，独立优化仍待验证。
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

## Spin/hash 完整收尾矩阵

135/135 场通过，覆盖全部十五个线程点；每个 worker 都有正进度。
下表每格为 min / median / max Mops/s；KD/TCLock 使用各自最高有效峰值。

| threads | Linux | TCLock | KD | KD/TCLock |
| --- | --- | --- | --- | ---: |
| 1 | 12.786 / 12.791 / 12.795 | 11.882 / 11.892 / 11.895 | 12.136 / 12.142 / 12.154 | 102.18% |
| 2 | 2.432 / 2.444 / 2.469 | 4.870 / 4.954 / 5.026 | 2.434 / 2.496 / 2.599 | 51.72% |
| 3 | 2.842 / 2.880 / 2.972 | 2.608 / 2.639 / 2.651 | 3.604 / 3.702 / 3.723 | 140.43% |
| 4 | 3.020 / 3.035 / 3.074 | 2.758 / 2.762 / 2.833 | 3.642 / 3.745 / 3.761 | 132.77% |
| 5 | 2.997 / 3.056 / 3.070 | 3.089 / 3.099 / 3.113 | 3.596 / 3.635 / 3.654 | 117.40% |
| 6 | 2.943 / 2.995 / 3.048 | 3.687 / 3.694 / 3.703 | 3.525 / 3.583 / 3.590 | 96.94% |
| 7 | 2.947 / 3.062 / 3.064 | 4.441 / 4.451 / 4.484 | 3.453 / 3.541 / 3.545 | 79.06% |
| 8 | 2.957 / 2.975 / 2.980 | 4.785 / 4.791 / 4.818 | 3.793 / 3.795 / 3.804 | 78.96% |
| 12 | 2.934 / 2.961 / 3.013 | 4.715 / 4.721 / 4.745 | 3.756 / 3.767 / 3.774 | 79.55% |
| 16 | 2.874 / 2.948 / 2.992 | 4.693 / 4.694 / 4.696 | 3.762 / 3.770 / 3.788 | 80.67% |
| 20 | 2.965 / 3.136 / 3.898 | 4.747 / 4.783 / 4.784 | 3.828 / 3.828 / 3.836 | 80.18% |
| 24 | 1.832 / 1.848 / 1.853 | 4.320 / 4.340 / 4.453 | 3.240 / 3.251 / 3.255 | 73.08% |
| 28 | 1.685 / 1.696 / 1.741 | 2.620 / 2.624 / 2.625 | 1.987 / 1.989 / 1.993 | 75.95% |
| 32 | 1.630 / 1.647 / 1.763 | 2.633 / 2.640 / 2.648 | 1.986 / 1.987 / 1.989 | 75.10% |
| 36 | 1.608 / 1.632 / 2.364 | 2.630 / 2.637 / 2.640 | 1.982 / 1.985 / 1.986 | 75.21% |

90% 目标只在 1、3–6 线程达到；2、7–36 线程仍有差距。
相对同默认 1024 配置的 9/27 历史收尾，1/2/8/16/20/24/36 线程 KD 中位数均提高
约 0.28%–2.25%；其他线程点没有该同版本基线，不宣称它们无回退。
24 线程少数 node 的全段份额为 1.88%–2.02%，最慢 worker 完成 30208–32256 次；
36 线程两 node 各约 50%。所有 worker 有进度不构成无饥饿或延迟保证。

完整原始证据 `numa-20260928-spin-full`，host `spin-full.tar.gz`，SHA256
`407e35a6021294124133cab12a5f7c1d645392aef128f39497bc81b5fa410500`。

## 真正三方 mutex cacheline 初始基线

独立 `mutex_cacheline`/`run_mutex.py` 生成 `mc_body_N`，复用正文及计时工具，操作内部无
运行时类型分支。Linux 直接调用原始 mutex 函数；KD 使用显式 ABI2 clobber 符号和 prepare，
没有启用 global interception；TCLock 使用固定提交的实际普通 mutex 实现。
TCLock 的 task 扩展字段改为预分配、固定 CPU worker 登记的 context，保留 parking/wakeup、
NUMA/WWJUMP 和六寄存器换栈；原源码及逐文件 SHA256、移植 diff 随仓库保存。
上下文引用只在整组 pthread_join、task 退出及队列/栈排空后释放。

基础及直接相关共 8 组通过。首次两个旧 fixture 的端点假设导致失败（一个未使用变量编译错误，
一个固定旧端点断言），修正后单独重跑两组及基础通过，保留初次失败日志。
包含真实 wrapper ABI2 的 COMPLETE/FULL、直接/bridge 准入、三种 mutex 端点的嵌套 owner/CALL
保留、registry 退休，以及 TCLock 原 C 内联汇编的 128 次换栈与 parking CAS 竞争检查。
42 项运行器测试、15 项共享 client/计时测试通过。加载前实际 TCLock ELF 的换栈/隐式 helper
寄存器审核通过；保留上游换栈造成的 objtool 警告，没有修改内核缓解或 frame-pointer 配置。

首次 27/27 场通过：

| threads | Linux | TCLock mutex | KD mutex |
| --- | --- | --- | --- |
| 1 | 27.980 / 27.982 / 27.988 | 35.110 / 35.116 / 35.131 | 2.143 / 2.149 / 2.152 |
| 16 | 6.716 / 7.190 / 7.227 | 4.544 / 4.568 / 4.704 | 0.788 / 0.790 / 0.804 |
| 36 | 5.224 / 5.359 / 5.646 | 4.440 / 4.477 / 4.631 | 0.524 / 0.538 / 0.598 |

KD 竞争正例有返回正文证据：16 线程 JIT 6.37%–6.78%，36 线程 29.56%–32.51%。
TCLock 测量期真实委托比例 97.79%–98.76%；整个会话的 parking 计数 4–159，证明保留路径实际执行。
这些比例是全测量段，parking 是含预热的累计，均不是最高窗口专属。
KD 基线仍有每次 task 分配/全局注册锁、shadow 全局锁和通用 frame 路径；NUMA 编译 on，
但该 mutex 队列尚为 FIFO，不能把 spin 的 grouping 当作 mutex 已实现。
90% 目标尚未达到。本轮先完成 cacheline 正确性和基线，再逐项优化，不提前用 hash 成绩代替。

证据 `numa-20260928-mutex-baseline-{screen,validation}`；host `mutex-baseline-screen.tar.gz`，
SHA256 `03a41bf49f20c627609f879a3ee3d077601ea99e1468f4be5b35b58471b0eae3`；
client/runner 日志另存 `bench/.tmp/numa-20260928/mutex-bench-tests.log`。

其余 108/108 场也通过，覆盖余下 12 个线程点（三方各三轮）：

| threads | Linux | TCLock mutex | KD mutex |
| --- | --- | --- | --- |
| 2 | 6.482 / 6.491 / 7.089 | 9.497 / 10.245 / 10.303 | 1.135 / 1.136 / 1.201 |
| 3 | 6.041 / 7.408 / 7.927 | 8.105 / 8.635 / 10.742 | 0.914 / 0.956 / 0.972 |
| 4 | 6.444 / 7.338 / 7.511 | 5.828 / 6.080 / 6.132 | 0.831 / 0.855 / 0.924 |
| 5 | 6.867 / 7.316 / 7.573 | 5.705 / 6.000 / 6.970 | 0.799 / 0.829 / 0.837 |
| 6 | 7.253 / 7.349 / 7.407 | 5.099 / 5.178 / 5.485 | 0.796 / 0.808 / 0.836 |
| 7 | 6.797 / 6.936 / 7.507 | 4.225 / 4.336 / 4.492 | 0.800 / 0.803 / 0.828 |
| 8 | 6.684 / 7.205 / 7.404 | 4.377 / 4.441 / 4.653 | 0.788 / 0.808 / 0.814 |
| 12 | 6.208 / 6.849 / 7.061 | 4.297 / 4.468 / 4.720 | 0.796 / 0.807 / 0.811 |
| 20 | 6.478 / 7.274 / 7.336 | 4.313 / 4.401 / 4.498 | 0.773 / 0.799 / 0.810 |
| 24 | 6.078 / 6.270 / 6.401 | 4.373 / 4.547 / 4.620 | 0.596 / 0.620 / 0.633 |
| 28 | 5.616 / 6.132 / 6.352 | 4.447 / 4.516 / 4.547 | 0.536 / 0.536 / 0.588 |
| 32 | 5.067 / 5.606 / 5.616 | 4.401 / 4.506 / 4.546 | 0.538 / 0.541 / 0.648 |

24 线程 KD node1 全段份额 17.00%–17.27%，最慢 worker 完成 47104–50432 次。
所有 worker 进度、业务、内核日志与排空通过。该 108 场比首 27 场多了 TCLock
登记清空检查（队列空闲之外还要求所有 worker 已退出），锁算法相同；两份冻结身份分别保留。
证据 `numa-20260928-mutex-baseline-rest`，host `mutex-baseline-rest.tar.gz`，SHA256
`294c402f244141c3abd27aade369fba410c209b8cc1ed23b10cea99474cef1e9`。


## Mutex native-first 与独立竞争采样

原 mutex owner CAS 成功时跳过热表、shadow、task record 和翻译工作。失败才记录竞争；
独立 per-CPU mutex entries/contentions 在 1024 次失败处右移比较、清零并更新时间，
没有复用 spin MCS。计数 pin 在原生阻塞前释放，实际 owner/ACK 与准入外的 unlock 路由保留。

按计划先试 `(entries >> 10) < 2`，1 线程三轮约 14.8 Mops/s，但首次 16 线程无 JIT，
运行器拒绝并正常排空；诊断复跑同样拒绝。16 个 CPU 最后完整窗口的 entries 为
49716–182593，contentions 为 1024，CPU 全冷；native owner 连续获取使该初始比例不适用。
据此改为下一个覆盖已测窗口的 2 次幂上界 256，并保留独立频率/单锁热度检查。
这不是通用最佳阈值证明，也没有把无 JIT 的吞吐记为竞争优化通过。

调整后 27/27 场通过，KD min/median/max Mops/s：

| threads | KD native-first | 基线中位数 | KD/TCLock 峰值 |
| --- | --- | --- | --- |
| 1 | 14.793 / 14.795 / 14.816 | 2.149 | 40.99% |
| 16 | 3.782 / 3.858 / 3.906 | 0.790 | 82.52% |
| 36 | 1.516 / 1.574 / 2.066 | 0.538 | 44.58% |

16/36 线程返回 JIT 比例分别为 8.29%–8.62% / 20.40%–23.90%。36 线程波动大，
不能以单轮最高值代替中位数。全部业务、worker 进度、内核日志和排空检查通过。
基础与采样/resource 4 组通过；调整阈值后基础与采样 3 组通过，包含精确边界、
busy 重试、跨类型计数隔离及成功 CAS 跳过后续工作的反例检查。

证据 `numa-20260928-mutex-nativefirst-{screen,diagnostic,ratio256,validation}` 包含两次失败，
host `mutex-nativefirst.tar.gz`，SHA256
`f1e3cd978b16086be82a35359106e83fac09888eaae2e01f07461a17afaed682`。


## 无锁 shadow 独立候选：回退

候选预初始化 1024 个独占 cacheline 的 gate，使用全地址 hash、精确不可变 key 和原子发布，
满表继续 native；没有改变真实 owner 或队列出版顺序。生产 resource 检查通过，包括同桶满表、
同/异 key 竞争发布、existing owner 保留及满表 native fallback。初次错误变异触发 fixture 的
空指针解引用，调整检查顺序后基础及 resource 共 3 组通过，保留首次失败。

27 场筛选及 18 场复核全部业务/JIT/排空通过，但性能不满足保护标准：

| threads | 筛选 KD min/median/max | 复核 KD min/median/max | native-first 中位数 |
| --- | --- | --- | --- |
| 1 | 14.633 / 14.636 / 14.637 | 未重复 | 14.795 |
| 16 | 3.320 / 3.681 / 3.833 | 3.103 / 3.213 / 3.276 | 3.858 |
| 36 | 1.817 / 1.877 / 2.147 | 1.769 / 1.967 / 1.983 | 1.574 |

16 线程中位数两次分别下降 4.59% / 16.72%，超过 3%，故恢复 `e75910b` 的 shadow 实现。
36 线程收益不能覆盖受保护点的重复损失。复核 16 线程实际 JIT 为 12.80%–15.17%，
高于 native-first 的 8.29%–8.62%；观测到执行路径份额变化，尚未确定完整成本归因。
后续 task/frame 成本发生改变后可以重新独立检验，不把本次候选叠入已接受实现。

证据 `numa-20260928-mutex-shadow-{screen,recheck,validation}`，host
`mutex-shadow-rejected.tar.gz` SHA256
`c619d26a50775c3dc901e148a36069e6f700f904ec72f76bd3ab46ed945717a9`；
完整候选 `mutex-shadow-rejected.patch` SHA256
`dcef196446632275064c1b503fae4d91b303e19a78414c2f73a3673e4f33f181`。

## 稳定 1024 task records：独立性能未通过，隔离保留

候选用 1024 个 cacheline 隔离、精确 key 原子发布的记录替换逐次分配和全局 registry 锁。
每次 acquisition 仍有精确原子引用，refs=0 的缓存 key 不参与路由，task 引用保留至卸载；
满表走 native。基础及新 concurrency/capacity 共 3 组通过，包含 8 线程同时发布同一 key、
同桶 1024 真实 task 替身、满表、复用、输家引用、零引用拒绝及卸载释放的错误变异检查。
真实 kernel SELFTEST 用 CPU0/1/2 的 owner/waiter/reader 验证两种解锁顺序、4 个最终 ACK，
两个 task 引用只在卸载释放；这是明确 JIT=0 的协议探针，不能替代实际 JIT 性能证据。

27 场及 18 场复核均通过业务、JIT 和排空，但竞争性能下降：

| threads | 筛选 KD min/median/max | 复核 KD min/median/max | native-first 中位数 |
| --- | --- | --- | --- |
| 1 | 17.261 / 17.262 / 17.264 | 未重复 | 14.795 |
| 16 | 1.431 / 1.436 / 1.478 | 1.469 / 1.489 / 1.500 | 3.858 |
| 36 | 0.879 / 0.900 / 0.922 | 0.891 / 0.893 / 0.975 | 1.574 |

筛选 16/36 线程 JIT 份额分别升至 92.03%–94.94% / 92.50%–96.91%。
记录缓存使大量请求进入尚未优化的 delegated runtime；份额变化是真实观测，非完整 PMU 成本归因。
按 3% 规则，不将该独立候选合入已接受基线。实现在实验分支
`perf/mutex-task-cache-candidate-20260928` 保留，先完成局部观测与 batch 路径，再重新检验组合；
当前稳定分支仍为 native-first。不得把单线程收益或 lifecycle 通过写成竞争性能通过。

证据 `numa-20260928-mutex-tasks-{screen,recheck,validation,ack}`，host
`mutex-tasks-candidate.tar.gz` SHA256
`d4d5132fc1b55b331f53439b507f4b1d5cb07dd2b552a4fe1d0fbcc206af19d2`。

## 本地栈、CPU 本地观测与后继预取：保留

四个 waiter 栈分别以其 CPU 的 NUMA node 为首选分配；纯观测计数改为 per-CPU，
排空后求和。真实 owner、task refs、active/reserved/waiter_count 及 ACK 状态仍精确维护。
只预取已入队且仍存活的后继头部、SP/BP packet 和两个相邻 caller-stack cacheline，
不在发布 wake 后访问后继。没有改变锁或队列发布顺序。

基础与 resource/outer-progress/shadow-switch 共 5 组通过。首次 stack-switch fixture 缺少
`u32` typedef，修正后复跑通过；首次 provider overlay 因旧 counter 上下文不匹配而在加载前失败，
只更新两个上下文行后重跑。上述失败均保留。27/27 场业务、实际 JIT、worker 进度、日志与排空通过：

| threads | KD min/median/max Mops/s | native-first 中位数 | KD/TCLock 峰值 |
| --- | --- | --- | --- |
| 1 | 14.926 / 14.928 / 14.956 | 14.795 | 41.37% |
| 16 | 3.847 / 3.918 / 4.084 | 3.858 | 84.81% |
| 36 | 2.033 / 2.141 / 2.324 | 1.574 | 48.89% |

受保护点中位数均未回退。该候选整体筛选通过；这不是三个子改动各自的收益归因，
也没有据此声称 remote-memory latency 已测得或 90% 目标已完成。
证据 `numa-20260928-mutex-locality-{screen,screen-fixed,validation}`，host
`mutex-locality.tar.gz` SHA256
`217b160f5e8e011c997ef54ef9987a08e729c45b8d797286af054dcc1ad35b1d`。

## 专用 mutex batch helper 与单 source lease：保留

普通 ABI2 root 使用专用 preparation/completion/retirement，并复用 batch 的精确 RIP slot；
每请求仍检查 OPEN、publication、backend 和 ABI。实际 QUEUE_OWNER ledger 在正文前建立，
FULL 退出仍 detach packet 并由 generic dispatcher 消费已返回结果一次，不重放正文。
一个 batch lease 覆盖所有同步 native 后缀、owner ACK 和 frame pop，legacy 保留原有私有 lease。

基础及 frame-capacity/JIT-entry/mutex-outer/native-peer/source-lifetime 共 7 组最终通过。
新增检查覆盖 closure 拒绝新 root 而允许已开始正文退休、26 种错误 COMPLETE 状态、
真实 pending dispatcher 的 FULL/native/refusal、借出 packet 后复制与尚欠 ACK 时拒绝 pop。
首次 stale-owner 变异在报告断言后触发 fixture 空指针，补足 fixture 错误退出后基础及 capacity
3 组复跑通过。普通 kernel build 和 27 场三方测量通过；objtool/locale 警告类别与 locality 基线相同。

| threads | KD min/median/max Mops/s | locality 中位数 | KD/TCLock 峰值 |
| --- | --- | --- | --- |
| 1 | 14.788 / 14.790 / 14.877 | 14.928 | 41.15% |
| 16 | 4.682 / 4.797 / 4.832 | 3.918 | 105.16% |
| 36 | 2.793 / 2.931 / 3.110 | 2.141 | 69.72% |

1 线程中位数下降约 0.92%，未超过 3%；16/36 改善。16/36 整段实际 JIT 份额为
5.90%–6.94% / 6.31%–7.66%，不是 peak 窗口专属份额。16 达到同期 TCLock 峰值的 90%，
36 仍未达标。全部业务、worker 进度、JIT 及排空检查通过；未将 mocked blocking/owner
fixture 写成实际复杂 mutex JIT，也没有把本轮简单正文结果推广到任意嵌套。
证据 `numa-20260928-mutex-batch-{screen,validation}`，host `mutex-batch.tar.gz` SHA256
`58c3bb053b996b773ab6f8b93574dbcab4eaf6fd9a2d0cb47dc517302bc038d4`。

## Mutex 有界 NUMA grouping：独立候选回退

实现独立 1024 扫描预算与 1024 正文上限，使用 tail 的原 CPU 身份判断 node；
每个 batch 保留 remote prefix，在普通/native/early handoff 前优先 splice，
未开始正文的拒绝只回退本轮扫描。Legacy/FULL packet 是不可跨越的边界，
预算耗尽先于 dependent successor read。没有扩大 node stride 或更改 owner/ACK。

基础、生产 batch loop 与既有 outer-progress 共 4 组最终通过；新 fixture 在 NUMA on/off
检查 rejection rollback、native/early release、远端优先、1024 正文/扫描边界及 source drain。
保护页覆盖耗尽预算下 `next->next` 的禁止访问。初次函数抽取签名与第二次 fixture
头文件/计数命名编译失败均保留，修正后通过。

27 场筛选及 24/36 线程 18 场复核均有真实 JIT、正确数据及排空，但 36 中位数重复下降：

| threads | 筛选 KD min/median/max Mops/s | 复核 KD min/median/max | batch 中位数 |
| --- | --- | --- | --- |
| 1 | 14.779 / 14.784 / 14.788 | 未重复 | 14.790 |
| 16 | 4.805 / 4.818 / 4.853 | 未重复 | 4.797 |
| 24 | 未测 | 3.125 / 3.261 / 3.861 | 未单独筛选 |
| 36 | 2.645 / 2.760 / 2.889 | 2.399 / 2.524 / 2.702 | 2.931 |

36 两次中位数下降 5.84% / 13.89%，按 3% 规则不合入已接受版本；实现在
`perf/mutex-numa-candidate-20260928` 保留，稳定 mutex 继续 FIFO。编译 NUMA-on 不代表
FIFO mutex 已有 grouping；spin 保持已验证的 NUMA grouping。后续高 JIT 份额的 task cache
若改变成本结构，可另行复验该候选，不能把失败独立结果合并成性能通过。
24 线程每个 worker 均有进度，最少 133632 操作，少数 node 整段份额 8.13%–10.41%，
peak 份额 5.52%–12.35%；没有无饥饿或最大等待时间证明。
证据 `numa-20260928-mutex-numa-{screen,recheck,validation}`，host
`mutex-numa-rejected.tar.gz` SHA256 `d34199c9929ef5d5f069bf3c7364f988bfb45b9c9a87072d0cb097ee6ba19818`。

## Task cache 在专用 batch 上复验：仍回退

在已保留的 locality/batch 版本重新应用 1024 稳定 task cache，继续使用 per-CPU 观察计数。
基础与碰撞/容量/并发发布 fixture 共 3 组通过；真实 pinned task、原生 mutex owner 和最终 ACK
探针通过，两种释放次序共 4 ACK、2 retained task 引用在卸载时释放。该探针 JIT=0；
普通 benchmark 的返回正文 JIT 证据单独统计。

27 场筛选与 18 场复核均业务正确、每 worker 有进度、实际 JIT 且排空，但仍未通过性能门槛：

| threads | 筛选 KD min/median/max Mops/s | 复核 KD min/median/max | 已接受 batch 中位数 |
| --- | --- | --- | --- |
| 1 | 17.260 / 17.265 / 17.377 | 未重复 | 14.790 |
| 16 | 2.150 / 2.165 / 2.173 | 2.136 / 2.168 / 2.221 | 4.797 |
| 36 | 1.205 / 1.209 / 1.231 | 1.201 / 1.345 / 1.508 | 2.931 |

16 中位数两次下降 54.87% / 54.80%，36 下降 58.75% / 54.12%。筛选的整段 JIT 份额
16 为 94.07%–95.85%、36 为 93.02%–95.46%；不能把更高 JIT 份额当成吞吐提升。
候选在 `perf/mutex-task-cache-batch-candidate-20260928` 隔离保留，尚不合入已接受版本。
36 复核每 worker 最少 54272 操作、node 1 整段份额 41.52%–44.07%。
随后在此候选上单独复验 lock-free shadow，以区分剩余全局表锁开销；不得据组合实验
改写此处独立候选的失败结果。

证据 `numa-20260928-mutex-tasks2-{screen,recheck,validation,ack}`；host
`mutex-tasks2-candidate.tar.gz` SHA256
`1eb10c9f29df9a027c93fe7be603151e82d2785fe3b69b75896a18b3ca796074`。

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

36 线程 nested/early 功能各完成 3600000 操作，返回 JIT 正文分别为 3081021 / 1113995，
业务、内核日志和排空通过。显式比例 4、单轮、固定迭代，仅作功能验收，不进入性能取优。
证据 `numa-20260928-spin-{nested,early}`；host `spin-functional.tar.gz`。
