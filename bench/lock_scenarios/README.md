# 场景客户端计量与配对实验

本页维护 `klock_test` 的计量、配对和翻译剖析方法；完整 spinlock 吞吐使用
[cacheline benchmark](../spin_cacheline/README.md)。全部运行仅在 recovery guest，
先确认 [环境与排空](../../docs/AGENTS.md)。

### 3.3 带观测的负载测量

`bench/klock_test` 保留原位置参数和 ioctl ABI，显式设置 `KD_TEST_METRICS=1`
后不再逐次打印完成信息，而在所有 worker join 后输出一行
`KD_BENCH_METRICS {JSON}`。未设置或设为 `0` 时保留旧输出；旧 `Total Time`
包含创建、回收和打印，使用毫秒墙钟，不能作为新测量结果。

执行顺序如下。准备阶段仍沿用对应 mode 的晋升、翻译和发布检查，不能省略：

```text
构建/加载 -> 注册、晋升、翻译、发布 -> 准备完成
  -> 分配样本数组、创建 worker、设置 comm/role
  -> 全部 worker 到达 barrier
  -> 各 worker 记录单调时钟/线程 CPU 起点
  -> 逐次记录 ioctl 前后单调时钟和成功次数
  -> 各 worker 记录终点并返回 -> join -> 汇总、排序、输出 JSON
  -> 核对同阶段新增 body witness、生成物和完整状态 -> 排空/退休/卸载
```

| 字段 | 含义与边界 |
| --- | --- |
| `schema=1`, `complete` | 格式版本和本驱动是否完整成功；不表示 JIT 或内核 oracle 通过 |
| `threads`, `mode`, `role_base`, `loops_per_ioctl`, `workload`, `ioctls_per_thread` | 请求参数；`KD_TEST_COMM`、`KD_TEST_MIXED`、绑核和模块参数仍须另存，混合角色不能当作同质负载 |
| `requested_ioctls`, `completed_ioctls`, `workers` | 请求数、成功返回数及每个 worker 的完成数/错误码；不是锁次数、状态更新数或 JIT 次数 |
| `wall_ns` | 最早 worker 起点到最晚终点；不含创建和 join，仍包含 barrier 释放后的调度差、计时及样本写入开销 |
| `worker_cpu_ns` | 各 worker 的 `CLOCK_THREAD_CPUTIME_ID` 增量之和；不含 daemon、外部 peer/combiner 的 CPU 时间，可能大于 `wall_ns` |
| `ioctls_per_second` | 完成 ioctl 数除以 `wall_ns`；不能直接称为临界区吞吐量 |
| `ioctl_p50_ns`, `ioctl_p99_ns` | 全部成功 ioctl 延迟的 nearest-rank 分位数，秩为 `ceil(p*N/100)`；每次 ioctl 可含多轮 CS、等待和原生/JIT 混合路径 |

测量最多保留 1048576 个 64 位样本，共 8 MiB，不静默抽样。测量模式要求
正的 loops/runs；workload 可为 0。所有模式均拒绝负数、混杂字符、数值溢出、
非法 mode 和 role 加法溢出，且在打开设备前报错。
任一 ioctl、设置线程名或计时失败，退出码非零，`complete=false`，五个性能
字段均为 `null`，但已经成功执行的 ioctl 仍计数。创建/打开设备/join 等致命
失败可能没有 JSON；缺少记录不是空负载 PASS，也不能据此重放已有副作用。

现有 `test_04` 的准备后主负载和 `test_08` mode 5 的 continuous stress 自动
启用测量。日志路径为 daemon 日志名加 `.workload.log`，另外保留同名前缀的
`.before.dmesg` / `.after.dmesg`；三者通过已有 `Evidence file:` 协议归档。
mode 5 的前置轮次、pinned holder 和 quota/native 阶段不计入这一个测量。
mode 8 的另外两场独立会话及 mode 4 的角色负载保持原有取证，不冒充已测量。
按前后快照核对新增、entry/lock 匹配的返回后 body；旧阶段的 witness 不证明
当前测量执行了 JIT。快照若截断或不能对应，保留为证据缺口。

```sh
# Guest: measurement/recording changes only, not a new daily smoke prerequisite.
make -C tests/unit run TESTS= PY_TESTS='test_benchmark.py test_regression.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite core
```

手动运行时，在[手动准备流程](../../docs/PROJECT_GUIDE.md#36-拆开观察模块daemon-和负载可选)
已经完成且确认对应入口发布后，可给原来的负载命令加上 `env KD_TEST_METRICS=1`，
并重定向 stdout/stderr 保存；仍须按该流程记录 dmesg、生成物与最终状态。
不要只在运行器外设置该变量期待它传入：运行器仍清除未声明的 `KD_*` 环境参数。

这只是**带观测的 ioctl 测量基础**。JIT witness、内核打印、完整状态 oracle
仍开启，调度/等待/hostcall/native 后缀仍包含在时间内；本 driver 不拆分这些成本，
也没有冷/稳态摊销、缓存传输或三方性能结论。显式重复配对入口见下一节。少量样本的 p99
仅是上述秩的观测值。`mutex_jit=0` 调用原生 mutex，是显式 debug/native 对照，
不是“原生代理”实现，不能据此凑齐 native / native delegation / JIT 三组。
测量不启用任何已延期的访问时 guard、flags 或版本隔离功能。

三方对照的当前边界见 [比较契约](../../docs/DESIGN.md#13-performance-comparator-contract)。
本地原版 TCLock mutex 对象已在当前 guest 头文件上确认缺少任务字段，不能直接
加载作为第三组；LiTL 的用户态拦截也不控制 ioctl 内部的锁。不要运行 TCLock
上游的换内核/启动 VM/清理 QEMU 脚本来绕过当前环境约定。
同内核的 native-with-hooks/JIT 配对实验使用下一节的独立入口；`target_process`
不匹配的原生对照仍包含现有 selector hook 开销，不等于未修改 Linux。
当前 guest 能看到 CPU PMU 节点，但 PATH 中没有 `perf`；未测到硬件事件不等于
硬件不支持。只编译的兼容性调查不是新的 unit/live PASS 或性能测量，证据见
[比较前置调查](../../docs/VALIDATION.md#tclock-comparator-feasibility)。

### 3.4 原生锁与 JIT 配对实验

`tests/tools/paired_benchmark.py` 显式选择普通 mode 2/5 的相同双服务临界区，复用
`bench/klock_test`、内核完整状态 replay oracle 和 `regression.run()` 的空闲、
冻结源码、停止边界与归档逻辑。它不进入 `CASES` 或日常套件，也不把依赖 JIT
事件才能推进的 SELFTEST 角色变成原生负载。不要单独手动拼接 `benchmark_arm.sh`
的内部环境；通过此入口保留配对和准备参数。

```sh
# Guest: confirm recovery/idle first; choose a NEW output directory.
python3 tests/tools/paired_benchmark.py --mode 2 5 --threads 4 8 \
  --workload 100000 --loops 16 --runs 2 --cpus 0-7 --repeats 2 --dry-run
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/tools/paired_benchmark.py \
  --mode 2 5 --threads 4 8 --workload 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 2 --timeout 300 --output /tmp/kdlock-paired-manual
python3 tests/verify_evidence.py /tmp/kdlock-paired-manual
```

上述选择有四个参数点，每点两对，合计 16 个独立会话。每个参数点按
`native -> jit`、`jit -> native` 交替；`--repeats` 必须为 2-100 的偶数，
整个显式选择最多 128 对。`--mode`、`--threads`、`--workload` 可列出多个值，
重复值去重后做笛卡尔积；不会把不同参数点的计时汇总为一个均值。
至少两个线程；总 ioctl 样本不超过 `2^20`，包括准备在内的状态更新不超过
已有完整校验上限一千万次。每个 benchmark 子命令另有 120 秒限制；超时仍是失败。

每臂执行流为：

```text
确认前臂排空 -> 默认构建 -> 新 provider/source 模块会话
  -> mutex_jit=1；native 目标 kd_unused，JIT 目标 klock_test
  -> 保存模块参数、实际构建哈希、boot、物理 lock、控制台设置
  -> JIT 臂启动 daemon --metrics；每次真实翻译子进程单独计量
  -> 相同准备调用 (1,1,1,1) -> 连续 promotion (1,48000,10,1)
  -> JIT: 验证生成体和两服务桩，等待静止，停止 daemon/翻译者
  -> 两组均静置 2 秒；确认无 writer/frame；JIT 为 NORMAL，native 无条目
  -> before.dmesg -> 指定的计时负载 -> after.dmesg -> 再查注册项/镜像
  -> 退休并卸载 -> 完整状态、完成数、时钟/标量、owner、hostcall 校验
  -> 本臂归档 -> 下一臂；成对核对同输入和无重叠会话
```

准备括号依次是 threads、loops、workload、runs，mode 与计时负载相同。
准备和测量都固定 benchmark comm 为 `klock_test`、role base 为 0，并记录相同
请求及实际继承的 CPU mask；这是允许集合，不是每线程固定 CPU、实际 CPU 驻留
轨迹或独占 CPU 预留。准备后的状态为 12001 次转移，最终必须等于
`12001 + threads * loops * runs`，由已有内核 oracle 逐字段重放核对。
翻译等待时长单独存在，不能据此声称两组缓存、温度或调度噪声完全相同。
每个 phase 前后、发布观察和最终汇总都只读核对相同的控制台设置；跨臂也必须
相同。这是离散采样，不保证两次采样之间没有外部改写。

JIT 测量必须有前后快照之间**新增**的匹配 entry/物理 lock 的返回后 body，
同一注册项前后为 NORMAL、代码地址和镜像哈希不变。每个已记录 body 必须对应
两个成功执行并返回 JIT 的服务；本普通路径不允许 quota/native 续跑。
原生臂无 daemon、条目、镜像、安装或 body。两组均保持 `mutex_jit=1`，区别只是
目标筛选，不能用 debug 开关制造第三种“原生代理”。单个 JIT 臂仍可能混有直接
原生获取，body 数不是全部 ioctl/临界区都执行 JIT 的证明。

每臂的 `protocol.tar.gz` 保存 `initial.json`、三个 phase 的命令/状态/JSON 计时、
发布记录、前后快照、最终日志和 `arm.json`；生成物另存于 `artifacts.tar.gz`。
运行根的 `comparison.json` 按 repeat 保留原生/JIT 指标、测量 body 数、带观测
吞吐比以及新的 `costs` / `console` 字段。没有新字段的历史配对仍可读取，但不会
补造计量；新旧计量记录不能混成一对。失败时停止，保留失败臂和 `incomplete_pairs`，
不自动重试、删除或平均；
若连排空/捕获都未完成，离线校验失败，不能生成有效比较。`STOP` 仍只在臂边界
生效，可能留下一对未完成结果。

新计量按以下边界解释，不把可重叠的时段相加：

| `costs` 字段 | 实际含义 |
| --- | --- |
| `preparation_elapsed_ns` | 模块加载后的 initial 记录至测量前 publication；包含 warmup、promotion、daemon/就绪等待及固定静置，不包含模块构建/加载，也不是纯翻译成本。 |
| `phase_process_ns` | 各 phase 从控制器记录开始到 benchmark 子命令结束的区间，含启动/等待/输出及控制器开销。C driver 的 worker envelope 仍单独保留。 |
| `translation` | 真实 translator 子进程的记录及 wall/user/system 汇总；还保留 fault/context-switch 计数，RSS 取最大值，不求和。原生臂次数为 0、RSS 为 null。 |
| `measure_process_outside_workers_ns` | measure 控制器区间减去 C worker envelope；不是 kernel 锁或调度开销的单独测量。 |
| `measured_cs` / `measured_jit_share` | 计时临界区次数及本阶段返回后 body 比例；不能外推到所有指令。 |

翻译记录必须匹配已发布的 RIP/pid/tgid/lock kind，时间在本臂准备区间内、不重叠，
且全部成功；缺失、失败、refusal、错误身份或控制台变化使配对失败。原始 daemon
日志照常归档。具体 wait4/CPU/RSS 契约见 [daemon 计量](../../daemon/README.md#translation-accounting)。
结果仍包含 witness、日志、状态 oracle、调度、排队和服务开销。下方可选计量只拆分
若干 C 边界，不提供完整 kernel 队列或纯 JIT 指令时间，未测硬件计数或 kernel 总内存，也没有
完成 TCLock 第三组或普遍加速/摊销结论。发布前后检查不是不可变代码版本机制。
仅改配对控制层时复用 `test_benchmark.py` / `test_regression.py`；改 daemon 计量
再加入已有 `test_daemon_policy`，不额外跑基础或完整矩阵。实际结果仍以
[VALIDATION](../../docs/VALIDATION.md) 的冻结版本为准。

长臂可能覆盖内核日志，导致前后快照与 body 证据丢失；输入上限不是日志容量
保证。保留完整 witness/错误日志，按当前容量选择单臂工作量，以独立重复增加
观测；不要通过删除日志、截掉丢失前缀或把缺失记录当零来制造通过。

性能比较还要保留控制台设置。`mutex_debug` 的正常排队和 JIT 入口日志现为
`KERN_INFO`，并未关闭 DSM_DEBUG 或删除日志；warning/error 和返回后 witness
不变。控制台等级为 4 且 `ignore_loglevel=N` 时，INFO 留在内核缓冲区但不输出
到控制台。若等级升到 7 或开启 ignore_loglevel，串口开销仍可能回来。日志属于
原生 kdlock 框架，不是把 `printk` 翻译进临界区；INFO 本身也不是零成本。
当前配对入口已自动采集并核对以下内容；手动实验也应保存，不要为获得更好数字
而悄悄修改全局控制台设置：

```sh
cat /proc/sys/kernel/printk
cat /sys/module/printk/parameters/ignore_loglevel
cat /proc/consoles
```

此前 mode 5 的约 35 倍时间异常已有独立的
[日志等级复测](../../docs/VALIDATION.md#mutex-routine-log-severity)，不再作为当前未定位的
JIT 翻译成本。修改该宏时复用 `test_mutex_outer_progress.py` 检查真实格式/等级及
保留日志；实际调度影响用显式配对和已有复杂 mode 4 验证，不新增基础测试入口。

#### CPU 受限的 mutex 测量

`--threads` 是 worker 数，`--cpus` 是允许运行的 CPU 集合；线程较多不保证同时
有足够的已链接 waiter。当前私有队首可以原生完成自己的请求，最后一个 follower
也会自行成为 owner 原生执行，不必执行 JIT。因此“热点已晋升 + 代码已发布 + 负载成功”
不能替代实际返回后 body。当前等待策略及 TCLock 对比见
[设计边界](../../docs/design/locking.md#pinned-busy-polling)。

下面仅预览同一负载在两个 CPU mask 上的选择，不执行测试：

```sh
python3 tests/tools/paired_benchmark.py --mode 5 --threads 8 \
  --workload 100000 10000 --loops 16 --runs 2 --repeats 2 --cpus 0-1 --dry-run
python3 tests/tools/paired_benchmark.py --mode 5 --threads 8 \
  --workload 100000 10000 --loops 16 --runs 2 --repeats 2 --cpus 0-7 --dry-run
```

实际实验沿用上面的 recovery、独立 `--output`、逐臂清理和失败即停止流程；
未指定 `--jit-timing` 时额外边界计时关闭，`mutex_jit=1` 仍必需。不自动重试
缺少 body 的参数点，不增加隐藏的 force-promotion、角色 gate 或更多并发用例来
制造通过。保存 `comparison.json` 的 incomplete pairs；可单独调查原计划未开始
的 CPU 组，但不能改写原失败 journal，或把孤立的原生样本配成 JIT 性能结果。

已有[实测](../../docs/VALIDATION.md#mutex-oversubscription-assessment)中，2 CPU 短负载的
245 次 slowpath 没有产生 combiner/JIT；状态虽正确，JIT 门槛仍失败。长负载也
只有很少代理。这是常见配置的参与率限制，不归为可忽略的罕见错误。CPU/wall、
p50/p99 必须结合实际 body 比例解释；这些短实验不证明轮询成本、睡眠唤醒收益、
公平性或跨 CPU 配置的因果关系。CPU-mask 调查不是日常或完整回归的前置条件。

#### 可选的 JIT 边界计时

`kdlock_km` 增加 `jit_timing=1` 装载参数，默认关闭，sysfs 为只读 `Y/N`。
它与必需的 `mutex_jit=1` 无关，也不是 daemon 的 `--metrics`。通过配对入口的
`--jit-timing` 同时为 native/JIT 两臂选择相同参数；不能运行途中开关以混合统计。
关闭时执行路径不额外读时钟、累计计数或打印计量记录，但仍有分支/辅助调用和
入队时间字段的清零，不能宣称与加入计量前逐指令相同。模块初始化清零统计，
所有 executor 排空后卸载汇总。

```sh
# Guest, explicit experiment only. Omit --jit-timing for the off comparison.
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/tools/paired_benchmark.py \
  --mode 2 5 --threads 8 --workload 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 2 --jit-timing --timeout 300 \
  --output /tmp/kdlock-jit-timing-manual
```

执行流：验证入口及 frame scope -> `dispatch` 开始 -> 每次 `wrapper` 调用 ->
按退出包调用 `hostcall` 或 `control` -> 继续 wrapper 或按既有出口返回 ->
`dispatch` 结束。失败/拒绝也按实际经过的边界计数；计时异常仅使记录无效，
不会改变执行结果、入口重放判定、寄存器包或真实 owner。
若既有出口要求原生续跑，backend 先开始 `native_*_handoff`，再验证/登记 borrowing、
发布远端状态及本地 waiter。必须早于 spin 的 `kd_exec_remote_native()`，因为祖先
可能在本地节点被唤醒之前就获知 native 出口。随后真实 owner 进入
`kd_exec_native_wait()`，开始内层 `native_*_wait`，处理 unlock/ACK 并等待完成。
公共等待函数返回前结束 wait，backend 收到成功返回后结束 handoff，再做 frame
清理。最终 ACK 之后计时只用预先保存的局部时间与后端常量，不读取 waiter 的
request/task/node。新增 handoff 不需要 frame 字段；下面的队列计时
在 spin/mutex 节点末尾各增加一个 64 位字段，不修改 frame 或两元素 wrapper 参数。

队列计时执行流：初始化节点 -> 在交换 tail 前记录 `queued_at_ns` -> 发布入队。
若请求成为队首，在取得私有 gate 和原生 L 后结束计时，再处理其他 waiter；
若由 combiner 代理，先保存 dispatch 调用前的时间，调用返回后仅在 `frame->executed`
为真时按该时间记账，不把正文或 native 后缀算进本请求的等待。未执行正文的
拒绝不消费起点，随后仍计到真正执行或原生获取。记账在 wake/native 发布之前
清零节点时间，spin 也在释放节点计数、进入 combiner 之前结束自身等待；不在
最终 slowpath 返回时读取已复用的节点时间。

| 阶段 | `ktime_get_ns()` 观测边界 |
| --- | --- |
| `dispatch` | 准入/scope 通过后至高层 dispatcher 返回；含其记账、日志和内部计量开销，不含 backend frame 建立/清理、入口前等待。 |
| `wrapper` | 实际 `translated(regs, args)` 的调用/返回，包括 wrapper 和生成代码；不是只有源临界区指令。合成故障没有实际 wrapper 调用，不计入本项。 |
| `hostcall` | 服务查表、属性验证和 typed native invoke；不含后续 CALL 返回包推进。 |
| `control` | 锁控制目标分类及处理，包括可能的阻塞和嵌套代理；不含 dispatcher 返回之后 waiter 的 native 后缀与 ACK 等待。 |
| `native_spin_wait` | spin 真实 owner 进入公共 native wait 至其返回，含轮询、unlock/finish 和远端 relay 等待；失败返回也计数。 |
| `native_mutex_wait` | mutex 真实 owner 的相同边界，含必要的调度等待；不转移 Linux mutex owner。 |
| `spin_queue` | kdlock 节点入队前至原生 L 获取完成，或首次实际执行正文的 dispatch 调用前；含此前等待和准入准备，不含该正文与后续批次。 |
| `mutex_queue` | mutex 私有队列的相同边界；嵌套 B 直接走 Linux mutex 获取，不属于本项。 |
| `native_spin_handoff` | backend 决定 native 后、登记 borrowing 之前，至公共 owner wait 成功返回后；包含远端/本地发布、waiter 的早期 native 执行、等待和内层计量，不含前面的 dispatcher 或后面的 frame 清理。 |
| `native_mutex_handoff` | mutex 的同一交接边界，保留原生 owner；不是在 waiter 上采样 CPU 时间。 |

当前启用会话每次卸载有且仅有十行 `kd_jit timing: phase=... samples=... ns=... invalid=0`，
原生对照臂十项均为零；关闭时无这些行。时钟倒退或累计超出有符号 64 位范围时
对应 `invalid=1`，保留执行结果但拒绝本次计量，不把异常数据当零或回绕值使用。
`arm.json` 和 `comparison.json` 的 `costs.jit_boundaries` 保留总数、总纳秒及每次
调用均值；统计涵盖**整个模块会话，包括准备期**，不是只对应 measured phase。
历史报告仍可读取，不补造新增字段；当前会话缺少新增两行时不能套用历史格式放行。
开关不同的臂不能配成一对。

仅普通 mode 2/5 的非嵌套双服务路径有如下计数契约：每 N 个返回后 body 对应
N 次 dispatch、3N 次 wrapper、2N 次 hostcall、N 次 control、四项 native wait/handoff 为零。
对应后端的 queue 次数匹配既有 slowpath 统计且不少于 N，另一后端为零；队首自己
取得原锁也计入 queue，不能只按 JIT body 计数。服务/完整状态/native 计数仍满足
原有判定。缺行、重复、非法值、计数不一致均使实验失败。
此范围的 `dispatch_residual_ns` 是 dispatch 减去其他三段，包含日志、记账和
计量自身等未拆分成本，不能叫作纯代理开销。其他嵌套模式的父子区间可能重叠，
不能照搬这个减法；并发调用的累计 elapsed 也不能当成整轮墙钟或 CPU 时间。
比较开/关的 worker 时间时同时保留 JIT 参与比例和调度差异，不据此直接推导
单次观测成本。handoff 包含对应 wait，不能将二者相加；已完成的对应请求两者次数
应相同且 handoff 总时间不小于 wait。handoff 覆盖旧 wait 漏掉的发布/早期后缀，
但同时含借用准备、调度、unlock/ACK 和观测开销，不是纯 native 指令或 CPU 时间，
也不含最后一次 unlock 返回后的代码。远端不同层的交接区间仍可能彼此重叠。
队列时间只覆盖成功发布的 kdlock 节点：不含分配节点之前的时间、无节点回退，
也不覆盖所有 fastpath 或原生 Linux 队列等待。等待区间可彼此重叠，不能从
dispatch 中扣除或加到墙钟时间。完整锁获取、native 纯执行成本、观测成本、
硬件计数及摊销仍是未完成任务。

现有复杂用例可显式启用同一参数，统一入口会将选择写入每项环境，并核对该
脚本每次装载的 sysfs 值；默认选择及目录中的固定用例身份不变：

```sh
# Guest; new evidence directory, same recovery and drain requirements.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case mode-4 --case mode-5 --case mode-8 --jit-timing --timeout 300 \
  --output /tmp/kdlock-native-handoff-manual
```

直接调用 shell 时可显式设置 `KD_JIT_TIMING=1`；统一入口会清除未宣告的 `KD_*`
环境，所以使用 `--jit-timing`，不要只在外层导出变量。该选项负责选择和记录，
不能代替计量 oracle：复杂脚本保留原有 JIT、完整状态、owner/ACK 判定；另按每次
已排空会话核对十行、`invalid=0`、各后端 begin/complete 与 wait/handoff 次数，
并检查 handoff 包含 wait。失败停机不产生完整交接计量，不能据缺行填零或制造通过。
没有入队前资源拒绝的这些代表路径，再将 queue 次数与各后端已排空的 slowpath
统计关联；不能把该等式推广到存在未入队回退的压力场景。
不把同一会话在多个 phase 日志中的副本重复计数，也不在嵌套模式使用普通配对的减法。

修改公共计量时复用 `test_jit_entry_scope.py`、`test_exe_registry.py`、
`test_remote_outer.py` 和 `test_benchmark.py`；改 backend 交接起止点时还选
`test_spin_outer_progress.py`、`test_mutex_outer_progress.py`，观察真实 producer 的
开始/借用/发布/等待/结束顺序。修改队列记录点/布局时还选
`test_spin_shadow.py`、`test_spin_outer_progress.py`、`test_mutex_outer_progress.py`、
`test_mutex_resources.py` 和 `test_exec_capacity.py`。只有选择器/装载规则变化时再选
`test_regression.py`；不增加新单元入口或日常套件，也不因计量改动扩展极端组合。

### 3.5 翻译器剖析

这是显式性能调查，不是新的日常用例或 daemon 选项。翻译 CLI 只生成文件，
不会上传；先按[手动准备流程](../../docs/PROJECT_GUIDE.md#36-拆开观察模块daemon-和负载可选)
准备一个有效入口，再停止新负载、等待旧调用者和 daemon/翻译子进程退出。
provider 必须仍为 ACTIVE，frames/writers 为零；尚未执行 retire/unload。
不要在运行中的回归脚本里临时插入命令，或在仍有执行者时覆盖工作区。

执行流为：

```text
普通 daemon 翻译并发布 -> 排空调用者/翻译者，保留 ACTIVE provider
  -> 复制该条目的 callee/IJ 表到独立空目录
  -> CLI 新建有效 device lease -> cProfile 记录同一翻译流程 -> 生成独立镜像
  -> 比较 jit.S/jit.bin 与已发布生成物 -> 保存 profile/日志/退出码
  -> 另跑既有负载验证已发布 JIT -> 排空/退休/卸载
```

以下变量必须来自**当前会话**：`ASM_DIR` 为已发布条目的 `asm/` 路径；
`LOOKUP_PID` 为 registry 的 pid（内核条目通常为 0，不是 tgid）；`ENTRY_RIP`
为十六进制入口；`LOCK_KIND` 为 `spin` 或 `mutex`。不要复用历史 RIP 或手工设置
`KD_DEVICE_FD`。确认上述排空条件后，仅在 guest 运行：

```sh
PROFILE_WORKSPACE="$(mktemp -d /tmp/kdlock-profile.XXXXXX)"
mkdir "$PROFILE_WORKSPACE/asm"
cp "${ASM_DIR:?}/callee_table.txt" "$ASM_DIR/ij_table.txt" "$PROFILE_WORKSPACE/asm/"
(
    cd "$PROFILE_WORKSPACE" || exit 1
    KD_JIT_BODY_WITNESS=1 timeout --kill-after=5s 60s python3 -B -m cProfile \
        -o profile.pstats /root/host_fs/kdlock/disassem/disassem.py \
        "${LOOKUP_PID:?}" "${ENTRY_RIP:?}" "${LOCK_KIND:?}" > translation.log 2>&1 || exit $?
    python3 -B -c 'import pstats; pstats.Stats("profile.pstats").sort_stats("cumulative").print_stats(40)'
)
```

非零退出不能计作成功样本。保留原始 `.pstats`、完整日志、生成物、源码和会话
身份；用相同输入在另一空目录重复不带 `-m cProfile -o profile.pstats` 的 CLI
命令，单独记录 wall/CPU。cProfile 有显著额外开销，且 cumulative 时间包含子调用，
不能把父子行相加或当作生产 pass 的真实耗时。`build_jit_binary` 的时间包含等待
外部汇编工具，Python profiler 不剖析这些进程内部。RSS 也包含测量进程树的影响。
检查独立镜像不代表它被上传/执行，仍须保留既有 NORMAL、body 和状态验收。

当前符号匹配把 `CONTEXT_SYMBOLS` 的固定 glob 合并预编译，仍逐次读取实时符号表，
保留大小写、完整匹配和编译器克隆名规则，不缓存地址或准入结论。真实符号/区间、
生成字节、新旧普通耗时及复杂 JIT 结果见
[符号匹配验收](../../docs/VALIDATION.md#context-symbol-matching)。改变匹配规则时选择
[5.2 的相关单元/审计](../../docs/testing/entry_admission.md#52-运行时续点)及受影响复杂/拒绝用例，不加重复基础 smoke。
