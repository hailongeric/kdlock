# Benchmarks

benchmark 的运行方法、伪代码、性能结果和限制维护在本目录及对应子目录的
README，根 README 只保留目录导航。所有构建和执行都在 recovery guest
`/root/host_fs/kdlock` 中进行；环境、快照和排空要求见
[操作手册](../docs/AGENTS.md)。

## 代码组织

| 入口/组件 | 职责 |
| --- | --- |
| [klock_test.c](klock_test.c) | 既有场景的参数检查、线程创建/join、结果状态 |
| [lock_scenarios/worker.inc](lock_scenarios/worker.inc) | 起跑 barrier、单个 worker 的 ioctl 与可选计时 |
| [lock_scenarios/metrics.inc](lock_scenarios/metrics.inc) | 完整运行的聚合和精确 ioctl 分位数 |
| [tclock_compare/README.md](tclock_compare/README.md) | 完整 TCLock 原生栈委托、Linux 原生、kdlock JIT 的同负载六臂对照及独立硬件采样 |
| [spin_cacheline/clobber_compare.py](spin_cacheline/clobber_compare.py) | 同一实验内核上两种 caller ABI × native/kdlock，交替五轮并报告中位数、JIT 比例及调用者汇编 |
| [spin_cacheline/run.py](spin_cacheline/run.py) | CLI、构建/冻结、扫描和汇总调度 |
| [spin_cacheline/bench_runtime.py](spin_cacheline/bench_runtime.py) | 计划、CPU/布局/计数检查、命令超时、来源状态和源码冻结 |
| [spin_cacheline/bench_session.py](spin_cacheline/bench_session.py) | 一个会话的准备、发布确认、测量和排空 |
| [spin_cacheline/client.c](spin_cacheline/client.c) | 原子起跑、绑核、一次 ioctl 内的批量操作 |
| [spin_cacheline/summarize.py](spin_cacheline/summarize.py) | kdlock 最佳吞吐/原生中位数、最佳会话来源、有效配对和 CSV |
| [spin_cacheline/assembly.py](spin_cacheline/assembly.py) | 排空后按临界区及文件内容去重，生成 `bench/.tmp/spin_cacheline/` 汇编索引与来源哈希 |
| [spin_cacheline/test_assembly.py](spin_cacheline/test_assembly.py) | 临界区去重、内容差异保留、排空门禁、来源哈希及历史证据不变性检查 |
| `spin_cacheline/provider/` | 私有观测覆盖层，不修改生产源码 |
| `spin_cacheline/profile*.py`、`dispatch_floor/` | 独立采样和入口成本诊断，复用同一会话检查 |

`.inc` 与客户端入口一起编译，保留既有单文件构建命令；Python 入口保留
现有 `run.Session` 和验证函数的导入接口。Demo 驱动的代码地图见
[workload_modules/README.md](../workload_modules/README.md)。

## Spinlock cacheline 对比

最新 [9/19 当前版本三方复测](tclock_compare/results/20260919-state-access.md)
完成 clobber ABI 下 90 场对照和 30 场长批次单线程检查，全部正确排空。
20 线程、1/16 cacheline 下，kdlock 为 2.965/2.904 Mops/s，比 TCLock 高
29.0%/71.1%，相对 Linux 为 −1.7%/+61.5%；4 线程仍明显落后。
本轮没有改锁实现，三方实际代理比例、波动及单线程成本均在结果页。

当前说明与历史证据按职责分开：

| 查阅内容 | 入口 |
| --- | --- |
| 当前三方运行方法与统计口径 | [tclock_compare](tclock_compare/README.md)；默认两种 ABI，可用 `--abis clobber` 选择新 ABI |
| 获取、等待、现场恢复及 TCLock 对照 | [EXECUTION_PATHS](spin_cacheline/EXECUTION_PATHS.md) |
| 当前实际批长与 JIT 比例 | [9/19 日志复算](tclock_compare/results/20260919-state-access.md#batch-length)；不是新 benchmark |
| 两后端扫描及汇编查看 | [spin_cacheline](spin_cacheline/README.md)；`run.py` 的 best/median 不同于三方五轮中位数 |
| 状态访问、预取与入口取舍 | [状态访问](spin_cacheline/results/20260918-state-access.md)、[预取](spin_cacheline/results/20260918-prefetch.md)、[入口与缓存](spin_cacheline/results/20260918-spin-entry.md) |
| 首次两 ABI 三方矩阵、采样与冷晋升失败 | [9/18 三方结果](tclock_compare/results/20260918-native-stack.md) |
| 已被替代的早期阶段 | [历史索引](spin_cacheline/results/HISTORY.md)；保留原报告 Git 版本、归档及哈希 |

`spin_native_cache=1` 和 `spin_prefetch=2` 是当前默认。热锁检测仍为固定频率
阈值；按收益切换原生/探测/代理尚未实现，见 [待办](../docs/TODO.md#hotlock-monitoring-and-adaptive-admission)。

专用 provider、客户端及脚本在 `spin_cacheline/`，Demo 内核模块在
[workload_modules/spin_cacheline](../workload_modules/spin_cacheline/)。
硬件采样和 `dispatch_floor/` 是单独诊断，不计入无采样吞吐成绩。
扫描和采样排空后生成按临界区去重的 `native.S`、`JIT.S`、`bin.txt`；后者是
JIT 机器码反汇编。目录、来源哈希及补导出方法见
[汇编查看](spin_cacheline/README.md#assembly-inspection)。

## 既有场景客户端

[`klock_test.c`](klock_test.c) 是既有 Demo 场景的 pthread/ioctl 客户端，模式、
功能验收和用例选择见 [tests/README.md](../tests/README.md)。在 guest 编译：

```sh
cd /root/host_fs/kdlock
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c \
  -o bench/klock_test -lpthread
```

`KD_TEST_METRICS=1` 为这些场景添加 worker 总时间、ioctl p50/p99、线程 CPU
时间和完成次数；失败样本的性能字段为空。这些是带观测的功能负载，不能与
cacheline 对比或纯原生基线混合，详见
[测量流程](../docs/JIT_EXECUTION.md#33-带观测的负载测量)。
上游 TCLock mutex 与当前 guest 的接口差异及比较边界见
[比较器评估](../docs/DESIGN.md#13-performance-comparator-contract)。
