# 2026-09-19：状态访问优化后的 spinlock 三方复测

当前 kdlock 在 20 线程下，1/16 cacheline 的五轮中位吞吐为 **2.965/2.904
Mops/s**，分别比本轮 TCLock 高 **29.0%/71.1%**；相对 Linux 原生分别为
**−1.7%/+61.5%**。4 线程仍比 TCLock 低 **45.7%/27.9%**，也明显低于 Linux。
这些是同环境完整操作的后端比较，不能归结为单一的现场保存成本。

本轮只运行 benchmark，没有修改锁实现。测量版本包含此前的
[后继预取](../../spin_cacheline/results/20260918-prefetch.md)和
[状态访问优化](../../spin_cacheline/results/20260918-state-access.md)。
不将旧三方结果与当前 kdlock 拼接；下表三种后端均在本轮重新构建、运行。

## 完整操作吞吐

**90/90 场正确且排空**：1/16 cacheline × 1/4/20 线程 × 三种后端 × 五轮，
每线程 100000 次，共 **75,000,000 次完整操作**。只选择 `clobber` caller ABI；
每组后端复用相同的 workload 二进制。奇数轮反转三臂顺序。

单位 Mops/s，数值为五轮中位数；代理比例单独取中位数，不必来自同一场。
KD/Linux 和 KD/TC 是各组吞吐中位数的比值。

| cacheline | 线程 | Linux 原生 | TCLock | kdlock | KD/Linux | KD/TC | TC 委托 | KD JIT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 9.9099 | 7.3999 | 8.3554 | 0.843 | 1.129 | 0.00% | 0.00% |
| 1 | 4 | 2.8938 | 1.6705 | 0.9070 | 0.313 | 0.543 | 43.78% | 55.24% |
| 1 | 20 | 3.0147 | 2.2992 | 2.9649 | 0.983 | 1.290 | 80.33% | 99.74% |
| 16 | 1 | 8.1981 | 7.9373 | 7.5923 | 0.926 | 0.957 | 0.00% | 0.00% |
| 16 | 4 | 1.9591 | 1.1989 | 0.8643 | 0.441 | 0.721 | 45.60% | 51.94% |
| 16 | 20 | 1.7982 | 1.6970 | 2.9044 | 1.615 | 1.711 | 79.25% | 99.79% |

TCLock 的计数来自实际原生栈委托完成；kdlock 来自 wrapper 返回后的实际
JIT 正文。20 个多线程 TCLock 会话和 20 个多线程 kdlock 会话均实际代理，
合计分别 **17,486,638** 和 **22,134,540** 次。单线程代理数为零，单独记为
`NO_DELEGATION`/`NO_JIT`，没有将它们算成实际委托通过。

20 线程的五轮波动如下，吞吐单位仍为 Mops/s：

| cacheline | Linux 范围 | TCLock 范围 | kdlock 范围 | TC 委托比例范围 | KD JIT 比例范围 |
| --- | --- | --- | --- | --- | --- |
| 1 | 2.9365–3.0438 | 1.9006–2.8395 | 2.9345–2.9697 | 54.00%–99.47% | 99.71%–99.83% |
| 16 | 1.7860–1.8163 | 1.4342–1.9860 | 2.8639–2.9574 | 53.27%–99.75% | 99.74%–99.82% |

TC 的批次长度变化明显：1/16 cacheline 的平均每批委托正文数，分别在
1.18–271.62 / 1.15–577.90 之间。实现保留 `need_resched()`、队列末端和
batch 上限退出条件，本轮没有单独统计各个退出原因。不能将全部吞吐差异
解释为寄存器保存或请求访问差异；也没有挑选 TC 高委托率的样本替代中位数。
当前 kdlock 在 20 线程下保持约 99.8% JIT，没有靠降低代理覆盖率取得该成绩。

## 单线程长批次

十万次的单线程批次受批长影响明显，不能从上表单独解释无竞争入口成本。
另跑三后端 × 两规模 × 五轮，每场 **10000000 次**，共 **30/30 场、3 亿次操作**，
全部正确且排空，无 TC 委托和 JIT。以下为每次完整操作的 ns 中位数，越小越好：

| cacheline | Linux 原生 | TCLock | kdlock | KD−Linux | KD−TC |
| --- | --- | --- | --- | --- | --- |
| 1 | 37.013 | 52.205 | 44.820 | +7.807 | −7.386 |
| 16 | 42.845 | 58.422 | 50.543 | +7.698 | −7.879 |

当前 kdlock 无竞争时比 TCLock 少约 7–8 ns，但比 Linux 多约 8 ns。
这里包含调用入口、锁和解锁、正文与锁外四组乘加；不是单独的锁指令延迟。
三方共用 clobber caller，因此本轮没有隔离 caller spill 或比较 legacy ABI。

## 环境与执行

- recovery guest：`6.1.159-kdclobber1`，Build ID
  `db937d722ee2f2668acb12dc6f105aeea33b7c5c`。源码/配置/build/running 基线匹配；
  保留 frame pointer、缓解设置、`nokaslr`、voluntary 和 watchdog。
- 40 vCPU、28 GiB、双 NUMA，使用 node 0 的 CPU 0–19；vCPU 不表示独占宿主核。
  固定 Python 依赖与上一轮相同，源码位于 guest ext4。
- Git HEAD `7f6274422c05cb67b9fd356814323f83e9bf4706` 加运行前已有的未提交优化；
  初始 371 个仓库文件与 guest 哈希一致。版本以冻结源码哈希为准。
- kdlock 使用 `spin_native_cache=1`、`spin_prefetch=2`；TCLock batch 上限 1024，
  执行完整原生栈委托路径。Linux arm 不加载 provider。
- 三方统一在 CPU 0 预热 1 次、准备 12000 次。kdlock 等待唯一入口发布并停止
  translator/daemon 后才测量；翻译、准备及 allocator guard 不计入吞吐。
- 基础两个 C 程序和 `spin/test_tclock_context.py` 均通过，合计 3 个单元入口。
  本轮没有重跑复杂功能矩阵、legacy ABI 或硬件采样。provider 按现有默认启用
  `mutex_jit=1`，但只执行 spin 工作负载，不能记为 mutex 验证。

确认快照 `pre_static_boot_20260915` 后，在 recovery guest 执行；SSH 本身另有
外层 timeout。输出路径必须不存在：

```sh
cd /root/host_fs/kdlock
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export KDIR=/root/linux-6.1.159-kdclobber1
export KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 LC_ALL=C
make -C tests/unit run PY_TESTS=spin/test_tclock_context.py

timeout 2400s python3 bench/tclock_compare/run.py --abis clobber \
  --output /root/kdlock-evidence/spin-compare-20260919/compare \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918

timeout 1800s python3 bench/tclock_compare/run.py --abis clobber \
  --threads 1 --iterations 10000000 \
  --output /root/kdlock-evidence/spin-compare-20260919/long \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

这是已准备好的单锁稳态对照，不覆盖此前发现的并发冷晋升停滞，也没有修复
或重新测试该问题。TCLock 会话独占目标锁协议，不代表可以与 Linux qspinlock
同时操作同一锁字；兼容边界见 [TCLock 后端](../../../tclock_backend/README.md#与-linux-原生-spinlock-的协议兼容边界)。

## 证据与复核

两批合计 **120/120 场、375,000,000 次完整操作**。逐场核对所有 cacheline
增量、完成次数、CPU 亲和性、IRQ/preempt 状态、工作线程退出和排空；没有
内核 WARN/BUG、panic 或 lockup。kdlock 退休后 frames/modules/writers 为零，
TCLock 委托数等于完成数且 quiescent=1，最终 guest 空闲检查通过。

宿主只读离线审计独立复算全部吞吐、中位数、交替顺序和正文计数，核对
232 个冻结源码文件与全部二进制；其中 141 个非文档正式输入与初始、当前
工作区哈希一致。新 ABI 生成物身份、测量前后发布身份均匹配。
长批次与主矩阵的执行代码相同：kdlock 模块仅 `.BTF` 有差异；workload 的
差异为构建路径字符串、Build ID 和调试信息，已逐项检查。三后端在各自批次内
使用同一份 workload，不能跨批次混用短/长样本。

- guest 原始目录：`/root/kdlock-evidence/spin-compare-20260919/`，含
  `compare/`、`long/` 的逐场 JSON、日志、源码、二进制与生成物。
- guest 归档：`/root/kdlock-evidence/spin-compare-20260919-evidence.tar.gz`。
- 宿主归档：[evidence.tar.gz](/tmp/kd-spin-compare-20260919/evidence.tar.gz)，
  **4,661,777 bytes**，SHA256
  `29f6e2ddfe88c36616f035a6fce549d5097e953e1911c7f8e0ec2cbded4cea1f`。
- 离线复算：[90 场审计](/tmp/kd-spin-compare-20260919/audit-compare.json)、
  [30 场长批次审计](/tmp/kd-spin-compare-20260919/audit-long.json)、
  [审计脚本](/tmp/kd-spin-compare-20260919/audit.py)。它们只读取证据，不执行归档内容。
