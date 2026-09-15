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
| [spin_cacheline/run.py](spin_cacheline/run.py) | CLI、构建/冻结、扫描和汇总调度 |
| [spin_cacheline/bench_runtime.py](spin_cacheline/bench_runtime.py) | 计划、CPU/布局/计数检查、命令超时、来源状态和源码冻结 |
| [spin_cacheline/bench_session.py](spin_cacheline/bench_session.py) | 一个会话的准备、发布确认、测量和排空 |
| [spin_cacheline/client.c](spin_cacheline/client.c) | 原子起跑、绑核、一次 ioctl 内的批量操作 |
| [spin_cacheline/summarize.py](spin_cacheline/summarize.py) | kdlock 最佳吞吐/原生中位数、最佳会话来源、有效配对和 CSV |
| [spin_cacheline/assembly.py](spin_cacheline/assembly.py) | 排空后将原生/JIT 汇编复制到 `bench/.tmp/spin_cacheline/`，生成会话索引和 SHA256 |
| [spin_cacheline/test_assembly.py](spin_cacheline/test_assembly.py) | 导出的会话匹配、排空门禁、哈希、NO_JIT 分类及历史证据不变性检查 |
| `spin_cacheline/provider/` | 私有观测覆盖层，不修改生产源码 |
| `spin_cacheline/profile*.py`、`dispatch_floor/` | 独立采样和入口成本诊断，复用同一会话检查 |

`.inc` 与客户端入口一起编译，保留既有单文件构建命令；Python 入口保留
现有 `run.Session` 和验证函数的导入接口。Demo 驱动的代码地图见
[workload_modules/README.md](../workload_modules/README.md)。

## Spinlock cacheline 对比

入口为 [spin_cacheline/README.md](spin_cacheline/README.md)，包括同一把原锁下的
展开临界区、原子起跑、每线程一次 ioctl 批量抢锁、原生/kdlock 配对、实际 JIT
正文计数和 CSV 解释。当前每次正文返回后执行相同的 4 组局部乘加，为下一次
抢锁留一个短间隔；主指标为 **kdlock 最高有效吞吐 / 原生有效吞吐中位数**，
并显示最佳会话的 JIT 状态与两组有效样本数。这是观测最佳值，不保证每次解锁
都发生线程交接。详细口径见[结果解释](spin_cacheline/README.md#结果解释)。

[锁外乘加后的最新完整结果](spin_cacheline/results/20260915-post-work.md) 已按
每线程 10 万次、1/4/8/12/16/20 线程完成 120 个会话。带实际 JIT 的最高观测
吞吐为 0.461 Mops/s（1 条 cacheline、4 线程），多线程最高 best/median 为
0.1871（16 条 cacheline、20 线程）；所有测量及排空检查通过。

增加锁外乘加前，2026-09-15 的[十万次完整重跑](spin_cacheline/README.md#rerun-100k-no24)
选择 1、4、8、12、16、20 线程，排除 24 线程；五种 cacheline 规模共 120 个
会话完成并通过校验，具体性能、NO_JIT 分类及此前失败记录放在该 README。

专用观测 provider、客户端和脚本在 `spin_cacheline/`，Demo 临界区模块在
[`workload_modules/spin_cacheline/`](../workload_modules/spin_cacheline/)。
`dispatch_floor/` 和硬件采样是单独诊断，不计入正式性能扫描。

正常扫描和 `profile.py` 在每个 kdlock 会话测量、排空和卸载后，自动在
`bench/.tmp/spin_cacheline/<结果目录名>-<随机后缀>/<会话名>/` 保存
`bin.txt`、`JIT.S`，以及用于翻译前对照的 `native.S`。查看目录内的 `README.md`
可按 cacheline、线程数、repeat 和实际 JIT 占比选择汇编；索引随会话完成更新。
`bin.txt` 实际是 **JIT 机器码**的反汇编；三种文件的含义、历史结果补导出命令和
guest 到宿主机的复制方法见[汇编查看目录](spin_cacheline/README.md#assembly-inspection)。
最近完整扫描的 60 组汇编已补导出，当前本地查看位置和验证范围见
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
