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

最新测量为 [9/18 TCLock 原生栈委托三方对照](tclock_compare/results/20260918-native-stack.md)：
180/180 稳态会话正确并排空，覆盖两种 caller ABI。竞争配置 TCLock 为 kdlock
中位吞吐的 1.06–2.05 倍，但并不普遍超过 Linux；六场独立采样定位共享诊断
状态与请求元数据热点。并发冷晋升失败仍未修复，稳态准备策略和失败记录均保留。

此前的 [9/18 统一 combiner 现场后四组对照](spin_cacheline/results/20260918-unified-context.md)，
120/120 会话完成，报告五轮中位数。新 ABI 的 20 线程吞吐为 1.6294/1.6370 Mops/s，
与统一循环前基本持平，仍低于对应原生；实际 JIT、数据和排空检查通过。
下文旧扫描的 best/median 口径与四组对照不同，成绩只属于各自冻结输入。

入口为 [spin_cacheline/README.md](spin_cacheline/README.md)，包括同一把原锁下的
展开临界区、原子起跑、每线程一次 ioctl 批量抢锁、原生/kdlock 配对、实际 JIT
正文计数和 CSV 解释。当前每次正文返回后执行相同的 4 组局部乘加，为下一次
抢锁留一个短间隔；主指标为 **kdlock 最高有效吞吐 / 原生有效吞吐中位数**，
并显示最佳会话的 JIT 状态与两组有效样本数。这是观测最佳值，不保证每次解锁
都发生线程交接。详细口径见[结果解释](spin_cacheline/README.md#结果解释)。

[执行路径与开销伪代码](spin_cacheline/EXECUTION_PATHS.md) 从首次注册展开到
JIT wrapper 返回及 waiter 恢复，列出重复查表、全局锁、frame 校验/复制和
诊断计数。锁外乘加发生在原 waiter 恢复后；combiner 的连续代理批次仍持有原锁。

[2026-09-17 的完整扫描结果](spin_cacheline/results/20260917-stackless.md) 已按
每线程 10 万次、1/4/8/12/16/20 线程完成 120 个会话。带实际 JIT 的最高观测
吞吐为 **0.647 Mops/s**（1 条 cacheline、4 线程），多线程最高 best/median 为
**0.2935**（16 条 cacheline、16 线程）；所有测量及排空检查通过。
相较 [9/15 的相同负载](spin_cacheline/results/20260915-post-work.md)，
多线程最佳吞吐提升幅度中位数为 **52.9%**，仍明显慢于原生。

随后完成 [frame 单锁路径精简的四点定向复测](spin_cacheline/results/20260917-frame-fast.md)：
16/16 会话通过，20 线程的 1/16 cacheline 吞吐为 **0.855/0.850 Mops/s**，
较同日完整扫描对应点提升 **49.5%/48.6%**；4 线程提升 **12.0%/15.5%**。
这是部分配置、每组两个样本的观测结果；JIT 比例变化和重启因素见结果页。

同日 [waiter 包复用与原子 frame lease 的四点复测](spin_cacheline/results/20260917-waiter-packet.md)
同样 16/16 会话通过：20 线程的两点达到 **1.029/0.951 Mops/s**，较 frame
精简版提高 **20.3%/11.9%**；4 线程两点下降 **2.4%/1.7%**，未观察到收益。

增加锁外乘加前，2026-09-15 的[十万次完整重跑](spin_cacheline/README.md#rerun-100k-no24)
选择 1、4、8、12、16、20 线程，排除 24 线程；五种 cacheline 规模共 120 个
会话完成并通过校验，具体性能、NO_JIT 分类及此前失败记录放在该 README。

专用观测 provider、客户端和脚本在 `spin_cacheline/`，Demo 临界区模块在
[`workload_modules/spin_cacheline/`](../workload_modules/spin_cacheline/)。
`dispatch_floor/` 和硬件采样是单独诊断，不计入正式性能扫描。

正常扫描和 `profile.py` 在每个 kdlock 会话测量、排空和卸载后，自动在
`bench/.tmp/spin_cacheline/<结果目录名>-<随机后缀>/sc_body_N/` 保存
`bin.txt`、`JIT.S`，以及用于翻译前对照的 `native.S`。**按临界区分组，不按线程数
或 repeat 建目录**；同一临界区的相同汇编只保存一次，来源会话合并到元数据。
查看目录内的 `README.md` 可按 cacheline 规模选择汇编。
`bin.txt` 实际是 **JIT 机器码**的反汇编；三种文件的含义、历史结果补导出命令和
guest 到宿主机的复制方法见[汇编查看目录](spin_cacheline/README.md#assembly-inspection)。
最近完整扫描的 60 个 kdlock 会话对应 5 组不同临界区，当前本地查看位置和验证范围见
[汇编导出验证](spin_cacheline/README.md#assembly-validation)。

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
