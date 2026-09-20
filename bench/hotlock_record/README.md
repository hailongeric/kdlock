# Hotlock recording component benchmark

直接编译并调用未修改的旧/新 `kd_hotlock_record`，分别测发现阶段、冷地址流
与已晋升命中。该组件不安装 hook，不执行 JIT，不获取业务 spinlock。
它回答采样函数的成本，不能替代完整锁操作吞吐。

内核组件位于 [record_bench.c](../../tests/kernel/hotlock_record/record_bench.c)，
运行器为 [run.py](run.py)。每 CPU 绑定一个 kthread，只在整段循环两端计时。
发现阶段持续调用到观察晋升；终态准备在计时外完成，每线程测 100000 次。
所有状态由真实时钟和原始采样器自然建立，不通过改字段或增大窗口制造结果。
默认每组旧→新、新→旧交替五轮，线程为 1/4/20，合计 90 场；
最近一次本地发现验证显式选择 1/4 线程、三轮，共 36 场。

`worker_ns_call` 是各线程经过时间之和除以实际调用总数，包含竞争等待、调度、
测试循环和停止条件检查；不是硬件指令成本或纯 CPU 时间。
`wall_ns` 使用最早开始至最晚结束，发现阶段另报告达到晋升所需调用数。
每场验证晋升/冷地址状态、IRQ/preempt 平衡，记录源码、模块哈希、反汇编和内核日志。

只在 recovery guest 中运行，先按[操作手册](../../docs/AGENTS.md)确认快照、
运行内核与 source/build 基线。旧版目录必须是事先冻结的源码，不能用已修改的
当前工作树充当旧版。示例：

```sh
export KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915
python3 bench/hotlock_record/run.py \
  --baseline /root/kdlock-evidence/hotlock-before \
  --output /root/kdlock-evidence/hotlock-record-new \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

基线目录至少包含 `include/kd_hotlock.h` 和 `kernel_module/kd_hotlock.c`。
运行器把它们与当前版本分别复制至新证据目录，使用同一组件驱动和编译选项，
不替换生产工作树或普通 provider。CPU 频率门槛的准备在计时外；已晋升测量
还在每个 worker 的绑定 CPU 上真实调用目标锁 24000 次，建立其本地正向缓存。
不直接改采样器状态，计时仍包含 CPU 层持续检查。phase 1 现为循环访问 4096
个冷地址，两版都执行相同调用序列并检查它们均未晋升；不再比较已删除的
永久 IGNORE 状态。历史 phase 1 结果不能与当前冷地址流直接比较。

CPU 分层改造前的批量采样结果与完整 spinlock 稳态回归见
[2026-09-19 批量采样对照](results/20260919-batched.md)。

较早的 64 次检查/共享计数版本只做过驱动兼容性冒烟，已由当前本地发现取代。
那次 6 场记录随 `/tmp/kd-cpu-hotlock-20260919/evidence.tar.gz` 保留，索引见
[历史增量](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#其他冻结增量)；已删除状态的耗时不作为当前结果。

当前 10240 次检查 / 本地发现版本的 36 场组件对照见
[本地发现报告](results/20260919-local-discovery.md)。分别报告冷地址流、已晋升
命中和发现延迟，不用组件降幅替代完整锁吞吐或代理覆盖率。

V2 使用 `record_spin`/`query_spin`，驱动只为冻结 V1 对照保留名称适配。
候选正负检查在各 worker 的所属 CPU、计时结束后进行；主线程不得用本地查询
冒充全局晋升检查。V2 的 spin/mutex 表彼此独立，组件只测 spin 记录函数。

[V2 本地哈希对照](results/20260920-local-hash.md)：36/36 场通过；三阶段耗时均增加，完整操作与策略效果另见联合报告。
