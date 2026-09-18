# Linux / TCLock / kdlock 三方对照

使用同一个 `workload_modules/spin_cacheline`，分别加载 Linux 原生路径、独立
[TCLock 后端](../../tclock_backend/README.md)和现有 kdlock JIT provider。
两种 caller ABI 各编译一次，三种后端复用同一份 workload 二进制；完整操作、
锁外四组乘加、亲和性、准备等待与数据判定相同。三方均在一个 CPU 上预热和
晋升；kdlock 等待唯一入口发布并停止 translator/daemon 后，才启动指定数量的
测量线程。这测量已准备好的稳态路径，不覆盖并发冷晋升；首次完整尝试在该
kdlock 阶段发生过停滞，失败证据与后续稳态矩阵分开保留，不能视为已修复。

`run.py` 默认 1/16 cacheline × 1/4/20 线程 × 三种后端 × 两种 ABI × 五轮，
每线程 100000 次，共 180 场；奇数轮逆序，汇总中位数。TCLock 也经同一内核
hook，避免将绕过分派的 direct-call 结果冒充等价后端。原生 arm 不加载 provider。

三种后端在独立会话中运行；TCLock 会话的目标锁由 TCLock 协议独占管理。
保留 `spin_lock` 接口不表示与未修改 Linux qspinlock 的队列/解锁协议兼容，
本对照不覆盖二者同时竞争同一目标锁。原因和访问入口限制见
[协议兼容边界](../../tclock_backend/README.md#与-linux-原生-spinlock-的协议兼容边界)。

[2026-09-18 实测结果](results/20260918-native-stack.md)：180/180 场稳态测量正确
并排空，竞争配置 TCLock 中位吞吐为 kdlock 的 1.06–2.05 倍；另有六场独立
硬件采样和 20 场长批次单线程原生检查。结果页包含全部 ABI、代理比例、失败
记录和开销分析，不能只取最快的 TCLock 样本。
逐阶段实现差异及收益抵消统一见
[执行路径对照](../spin_cacheline/EXECUTION_PATHS.md#tclock-cost-comparison)，
其中区分已测热点、源码推断和未实施的优化候选。

TCLock 原生委托不叫 JIT。`delegation_share` 对 TCLock 使用实际 unlock/完成
计数差值，对 kdlock 使用 wrapper 返回后的正文数；两者均除以完整操作数。
竞争 TCLock 会话必须实际委托；所有会话均检查数据、工作线程退出与排空。
工作负载副本还在每个 SC_RUN 前后检查 IRQ/preempt 状态，不改测量循环。
采样诊断与无采样吞吐结果分开保存，不能用采样期间吞吐作为性能成绩。

`allocator_guard/` 是所有 arm 共用的计时外准备模块：仅分配/释放一页静态
per-CPU 区域，不安装 hook，随后立即卸载。Linux 6.1.159 的 reserved chunk
在小模块卸载后可能保留重叠的 scan/contig hint，使较大的 kdlock 模块在实际
仍有连续空间时加载失败。整页释放触发内核正常的 hint refresh；不改内核或
分配器内存，不掩盖 insmod 失败。其二进制及逐场加载/卸载日志同样冻结保存。

## 运行

只在 recovery guest `/root/host_fs/kdlock`，按[操作手册](../../docs/AGENTS.md)
确认快照、内核身份与空闲状态，启用固定依赖 venv。输出须为新的外部目录。

```sh
make -C tests/unit run PY_TESTS=spin/test_tclock_context.py
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918 \
  --output /root/kdlock-evidence/tclock-native-new/compare
```

先用 `--backends tclock --cachelines 1 --threads 1 4 --repeats 1 --iterations 10000`
验证移植，再运行默认矩阵。`STOP` 仅在已排空的会话边界生效，运行中不修改
冻结源码/二进制。失败会保存证据并停止，不自动重试或强制卸载。

采样复用一个已完成对照的冻结输入，不能先修改代码、文档或重建二进制。
例如对该次输出采集 clobber、20 线程、1 cacheline 的 TCLock 热点：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 600s python3 bench/tclock_compare/profile_backends.py \
  --comparison /root/kdlock-evidence/tclock-native-new/compare \
  --output /root/kdlock-evidence/tclock-native-new/profile-c01-tclock \
  --perf /root/kdlock-tools/perf-6.1.159/perf \
  --arm tclock --abi clobber --threads 20 --cachelines 1 --iterations 1000000 \
  --kernel-source /root/linux-6.1.159-kdclobber1 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-clobber1-20260918
```

分别选择三种 `--arm` 与两种 `--cachelines`，每场使用新输出目录。该入口只采
`cycles:k` 的平面 IP，检查零丢样，不开启 ftrace 或调用链。单线程成本另用
`run.py --backends native --threads 1 --iterations 10000000`，其余默认参数及
内核身份参数相同；长批次结果单独报告，不替换十万次矩阵样本。

## 证据范围

运行器保留源文件、上游身份、私有 kdlock provider 副本、两份 workload、后端
二进制、内核 Build ID、逐场数据与正文计数。`records.json` 包含未执行/失败
记录；`summary.json/csv` 只从数据正确且已排空的样本计算中位数。
性能与限制以[实际结果页](results/20260918-native-stack.md)为准；本轮没有验证
任意 task/per-CPU 临界区、跨 NUMA 或嵌套 TCLock。
