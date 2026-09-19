# Native 协议测试库存

本页按角色与所有权维护既有断言；运行入口见 [测试说明](../../tests/README.md)。
部分旧准备量和 CPU 放置尚未适配当前本地热锁发现，不能把历史 PASS 当作当前
通过。执行与恢复边界见 [JIT 执行指南](../JIT_EXECUTION.md)。

### 6.4 原 Waiter 的信号与退出

`KD_NATIVE_WAITER_SIGNAL=10/9` 将真实 SIGUSR1/SIGKILL 发送给已经执行 JIT
前缀、正在原生 B 上等待的逻辑 waiter。它不是 `test_19` 中的旁路原生
interruptible/killable peer。`KD_NATIVE_WAITER_API` 选择 B 的真实 API；
所有用例都要求保留 JIT 已完成的写入，并完成借用 A 的最终 owner ACK。
本节默认 `KD_NATIVE_WAITER_RACE=0`，B owner 在取消完成前保持锁；释放竞争
使用 `KD_NATIVE_WAITER_RACE=1`，其两种合法返回和操作见 6.5。

| API 选项 | B 调用与信号 | 离开 JIT 的原因 | B 的预期结果 |
| --- | --- | --- | --- |
| `0`，默认 | `mutex_lock`，信号 `10` 或 `9` | 单次 `jit_fail_pending_lock=2` 注入的 PENDING E2BIG | 不可中断等待，取得并释放 B |
| `1` | `mutex_lock_interruptible`，信号 `10` | 直接调用实际 API 的普通 CALL miss，无资源注入 | 原生返回 `-EINTR`，不进入或解锁 B |
| `2` | `mutex_lock_killable`，信号 `9` | 同上，目标为实际 killable API | 原生返回 `-EINTR`，不进入或解锁 B |

默认用例使用当前 guest 的 `TASK_UNINTERRUPTIBLE` 路径，不是自然容量耗尽：

```text
A combiner 执行 JIT 前缀，更新 record -> PENDING mutex_lock(B) 退出
  -> 原 waiter 从当前 CALL 包续跑，在 Linux B wait_list 排队
  -> B 的真实 owner 确认 waiter/保留 A owner 后调用 send_sig
  -> 观察 128 次：真实 pending/fatal 信号、不可中断等待、队列及 A/B owner 保持
  -> owner 释放 B -> waiter 必须取得 B，并带着 pending 信号完成后缀
  -> waiter 释放自己的 B，将 A unlock 交给原 owner
  -> final ACK 返回，记录恰好一次；调用者不再持有 A/B
  -> SIGUSR1：返回用户态执行一次 handler，ioctl 成功且不重试
     SIGKILL：Linux 在返回用户态边界结束任务，客户端不能正常返回
  -> 所有参与者退出，检查 native/task/node 计数排空及 RCU 清理
```

API 1/2 不将 mutex API 包在 helper 中，也不把它注册成 combiner-side 服务。
普通 CALL miss 保留真实 callee RIP、当前 GPR 和返回栈；本次不再进入 JIT：

```text
A combiner 执行 JIT 前缀，更新 record -> CALL miss 到实际 cancellable B API
  -> 原 waiter 原生进入 API，在真实 B wait_list 排队
  -> B owner 确认身份和 A owner 后 send_sig，仍持有 B
  -> Linux 返回 -EINTR，waiter 离开 B 队列，不执行 B 临界区或 B unlock
  -> waiter 原生完成错误分支的 record，提交 A unlock，等待真实 owner ACK
  -> ACK 后发布完成标记；B owner 确认自己仍持有 B，之后才允许释放 B
  -> SIGUSR1 返回用户态执行一次 handler；SIGKILL 在用户态返回边界结束任务
```

这里取消的是原 waiter 的新原生 B 获取，不是撤销已执行的 A 或丢弃委托 frame。
B API 的 `-EINTR` 由负载的错误分支处理，所以 SIGUSR1 客户端的 ioctl 仍成功。
错误分支只完成独立 record，不执行 B 的受保护状态变换。
脚本在准备期完成翻译后停止 daemon，测量期间不重编译；设备中的 CALL_MISS
保留用于取证。这不证明该 mutex API 本体可准入，也不验证并发替换 JIT 版本。

在已确认 recovery 快照、没有调用者/模块运行的 guest 执行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=10 bash tests/live/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=9 bash tests/live/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 \
  bash tests/live/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 \
  bash tests/live/test_10_native_resume.sh 4 4
```

脚本使用 CPU 0-6 的现有 mode 4 角色配置，读取 `mutex_jit=1`，并将 role 0
换成单进程、单 ioctl 的信号客户端，避免误杀 timeout supervisor 或另一个
pthread。B owner 仅对在真实 wait_list 中核对过的测试任务发信号，不伪造
pending 标志或锁字；不增加测试专用 task 引用来掩盖生产生命周期问题。
该测试只允许 mode 4、stage 4、pending contention，不能与 register、rename、
OOO 或资源注入选项叠加。`pending-int` 是客户端的 SIGUSR1 选项名；B 的 API
只由 `KD_NATIVE_WAITER_API` 选择，客户端选项名本身不改变锁 API。

`native_waiter_signal_protocol.py` 将同一 PID、entry、A 地址及 owner 贯穿
body witness、B 排队、完整副作用、final ACK 和客户端结果：

- API 0 还要求当前 PENDING 包、128 次 pending/队列观测、取得 B；总计
  12002 个独立 record、12008 次受保护状态变换。
- API 1/2 的强制取消要求 `jit_fail_pending_lock=0`、没有 PENDING 诊断，且设备的实际
  CALL_MISS 条目匹配 entry、mutex kind、非零代码地址和 kallsyms 中的 API
  目标。`-EINTR`、未取得 B、ACK 后仍持有 B 必须同时成立；总计 12002 个
  record、12007 次状态变换，不能沿用成功取得 B 的预期计数。
- SIGKILL 的 137 状态只能出现在 role 0，其他角色必须成功退出；单独看到
  进程死亡不能通过。每项必须恰好一次匹配的 body witness 和 native/ACK。

日志在 `waiter-signal.log`、`waiter-signal.json`、`role-0.log` 和
`role-status.tsv`；API 1/2 另保留卸载前读取的 `cancel-publication.json`。
取消路径发信号后只使用已保存的 PID/owner 标识及 release/acquire 完成标记，
不再解引用可能已退出的 waiter `task_struct`。观察超时报告失败并允许 B owner
释放锁，不能将超时或预期 SIGKILL 状态当作成功。

这是有界的原生 mutex 等待/取消测试，不是任意委托请求取消协议：不支持在 native
后缀中直接 `do_exit`、丢弃尚未确认的请求、抢占任意持锁指令或从入口重放。
128 次观测不证明遍历所有调度；最终计数检查也不替代 6.2 的真实 RCU 读者探针。
只修改 kdlock 的测试负载/客户端，没有 guest 内核修改或新的 owner handoff。

修改共享信号客户端后，另行回归旁路原生参与者的 interruptible/killable 取消。
这两项将信号发给 native peer，不是已经执行 JIT 的逻辑 waiter：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/live/test_19_mutex_signals.sh 1
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/live/test_19_mutex_signals.sh 3
```

### 6.5 原 Waiter 与 B 释放的竞争

在 6.4 的 API 1/2 上启用 `KD_NATIVE_WAITER_RACE=1`，保留真实 JIT 前缀和
普通 CALL miss，只改变测试中信号与 B 释放的调度。信号由 guest 用户态
controller 发送；B owner 不调用 `send_sig`，也不等待 A ACK 才释放 B。

```text
A combiner 执行 JIT stores -> CALL miss -> 原 waiter 原生进入 B API
  -> B owner 确认真正的 wait_list 成员和 A owner，发布 waiter PID/phase=1
  -> owner 睡眠轮询释放门；controller 核对单线程客户端并打开 pidfd
  -> 两个线程从同一 barrier 出发，独立执行：
       CPU 7: pidfd_send_signal(waiter)
       CPU 9: 写 native_waiter_release=1 -> B owner 亲自 mutex_unlock(B)，记录前后时间
  -> 原生 API 决定返回值，不由测试或 combiner 设置：
       0: waiter 真正拥有 B，执行一次 B 临界区并自行解锁 B
       -EINTR: waiter 没有 B，不执行 B 临界区或 B unlock
  -> 两条分支均保留 JIT prefix，完成一次 record 和 A unlock/owner ACK
  -> SIGUSR1 客户端执行一次 handler；SIGKILL 客户端退出
  -> join 全部角色，再检查 owner/frame/task 排空及最终状态
```

睡眠轮询只让被唤醒的 waiter 有机会离开 Linux optimistic-spin 并检查信号，
不伪造取消。当前内核在部分等待路径先 trylock 再检查 signal；因此即使信号
先送达，也可能获取成功。偏置只影响调度，不是返回值或内部线性化点的证明。
若获取和 A ACK 早于信号，客户端仅在用户态等待信号，不能增加测试专用
`task_struct`/frame 引用延长生产对象寿命；pidfd 固定 PID 身份而非借用锁 owner。

| 参数 | 默认值与约束 |
| --- | --- |
| `KD_NATIVE_WAITER_RACE` | `0`；`1` 仅允许 mode 4/stage 4、pending contention、API 1/2 |
| `KD_NATIVE_WAITER_RACE_US` | `0`；范围 `[-50000,50000]` 微秒。负数延迟释放，正数延迟信号 |
| `KD_NATIVE_WAITER_EXPECT` | `either`；可选 `acquired`/`cancelled`，真实结果不匹配即失败 |

除 CPU 0-6 的 workload 外，controller 还要求 CPU 7/8/9 可用，以及 Python
提供 `os.pidfd_open` 和 `signal.pidfd_send_signal`。缺少依赖不是 SKIP/通过。
先按 6.4 确认 recovery 和排空，在 guest 执行；以下两条是无偏置用例：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 KD_NATIVE_WAITER_RACE=1 \
  bash tests/live/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 KD_NATIVE_WAITER_RACE=1 \
  bash tests/live/test_10_native_resume.sh 4 4
```

在上述命令的 `bash` 之前增加环境变量
`KD_NATIVE_WAITER_RACE_US=-50000 KD_NATIVE_WAITER_EXPECT=cancelled`
或 `KD_NATIVE_WAITER_RACE_US=50000 KD_NATIVE_WAITER_EXPECT=acquired`，组成四个
有偏置检查。不要把偏置不符的失败改写成通过；保留实际返回、时间及源码身份。
无偏置的少数运行不证明所有竞争顺序都出现，结果与失败记录只维护在 VALIDATION。

判定器保留 6.4 的 JIT/实际 CALL_MISS/无 PENDING/owner ACK 检查，额外关联
`race-trigger.json` 的 pidfd 目标和 syscall 时间窗口，以及 B owner 的两个
`kd_waiter race unlock`、waiter 的 `kd_waiter race result`。sysfs 写成功不等于
B 已解锁。返回值选定分支后，12002 个 record 仍须恰好一次；取消对应 12007 次
状态变换，获取对应 12008 次，并检查实际 owner，而非只相信汇总计数。
取消的 A ACK 可以早于 B 解锁；获取后的 ACK 可以早于 B owner 的解锁后日志。

另外保留 `race-trigger.log`、client ioctl/handler 日志和七个角色的退出码。
`delivered=0` 表示本用例没有使用 kernel `send_sig`；真实信号证据来自 pidfd
记录和原生 pending/handler/exit。SIGKILL 允许来不及打印 ioctl 返回行，但不能
打印正常的最终 client return。controller 失败时仍要等待所有调用者，不能
强制卸载；B owner 的超时只帮助退出失败负载，不构成验收通过。

这仍是新原生 B 获取的有界竞争测试，不支持丢弃已执行 A 的 frame、native
后缀中直接 `do_exit` 或任意任务退出。新分支的用途/顺序注释放在 workload、
controller、客户端和判定器中；默认关闭，无生产锁、两元素 ABI 或内核修改。
共享 trigger 的 native-peer 回归使用 `KD_SIGNAL_RACE=1`：`test_19` 的
probe 2/4 是非队首取消检查，probe 1/3 是队首获取检查，分别配合负/正偏置。
偏置/期望为 `KD_SIGNAL_RACE_US`/`KD_SIGNAL_EXPECT`，不能与本节参数混用。
另保留 6.4 的 probe 1/3 强制取消对照；不能将队首的提前信号等同于已取消。

### 6.6 独立队列的并行 Native Frame

`test_23_mutex_parallel_native.sh` 默认使用两组真实 mutex `A0/B0`、`A1/B1`，
每组各有 holder、combiner、逻辑 waiter 和 trailing caller。八个 ioctl worker
固定在 CPU 0-7；两组 combiner 分别在 CPU 1/5，逻辑 waiter 在 CPU 2/6。
双 frame 首轮的两个逻辑 waiter 使用单进程信号客户端，其余角色和退休后重载
仍使用 benchmark；不向 benchmark 的线程组或 timeout supervisor 发信号。
每个 waiter 都有独立记录，B 仍由自己的 A combiner 获取，不新增远端 mutex frame。

```text
两组串行负载准备 -> 驱动保留间隔（不打开 CPU 门槛） -> 连续执行两组频率采样
  -> 两个实际 entry 均已发布 NORMAL -> 停止 daemon -> 独立锁晋升（无翻译）
  -> arm 竞争
每组 holder 持 A，等待真实私有队列出现 combiner / waiter / trailing 三个节点
  -> holder 解 A -> combiner 取得原 A，为 waiter 执行 JIT
  -> JIT 更新独立 record 与 A 的 sequence/digest，取得原 B，再更新 record
  -> 普通 CALL miss -> 原 waiter 原生进入 kd_parallel_native
  -> 原 waiter 改名 kd_renamed，保留自己的 A/B 借用关系
两组 waiter 均到达 native callee，且各自 A/B owner 仍为不同的 combiner
  -> 每名 waiter 获取/释放独立原生 C，C 的真实 owner 为自己，A/B owner 不变
  -> 控制器观察两次 C 返回，此时 source 仍 OPEN，两个 frame 均存活
  -> 有界暂停两个 frame，通过独立 mutex 的真实 CALL 入口填满 64 个代码块
  -> 新入口缺少条目，进入独立三请求队列，在 wrapper 前拒绝后各自原生完成
  -> 旧 frame 仍为 2，镜像/已有块不变；真实获取不同 mutex 填满 shadow 表
  -> 最后一个无 shadow 的锁：非目标 holder 与两个目标 Linux waiter 原生完成
  -> 两个旧 frame 仍存活；两名非目标 B 竞争者失败 trylock 并实际排队
  -> 核对单进程客户端身份，以 pidfd 发送 SIGUSR1；两个原生等待均取消
  -> 用户态观察 EINTR/一次信号，再明确重试一次；重新核对两张 B wait_list
  -> 核对两个原 waiter 的单进程身份并保留 pidfd：先排空者 SIGKILL，另一名 SIGUSR1
  -> 真实 compiler fork/exec 建立 writer
  -> 父进程退出而子进程保留引用
  -> retire 返回 EBUSY，进入 DRAINING；子进程仍能读源码，但发布被 ESHUTDOWN 拒绝
  -> 拒绝新 writer，释放测试暂停；已有 task/origin 路由仍服务 owner unlock
  -> 指定第一组完成后缀 -> B unlock/owner ACK -> A logical unlock/owner ACK
  -> 第一组以 kd_renamed 发布 post-unlock done，再恢复 klock_test 名称
  -> 第一名原生竞争者取得/释放 B，并确认另一 frame 的 B 仍拒绝 trylock
  -> 第一个 waiter 在内核后缀/ACK 完成后因 SIGKILL 退出，不返回用户态 ioctl
  -> pidfd 确认退出，source.frames=1，第二名 waiter 仍存活；释放第二组退出观察门
  -> 第二组再次核对自己的 A/B owner 和未完成记录，再完成后缀与两个 ACK
  -> 第二组仍以 kd_renamed 完成记录，再恢复名称
  -> 第二名原生竞争者取得/释放自己的 B
  -> 第二名 waiter 在 ioctl 返回前处理一次 SIGUSR1；其余 caller 与两名 B 竞争者返回
  -> join 全部 supervisor（仅第一个 waiter 为 137）-> 核对记录、镜像哈希和排空
  -> 单独的 orphan writer 仍让 retire 返回 EBUSY -> 释放并确认子进程退出
  -> 源 pin 仍阻止测试模块卸载 -> retire 全部条目为 NATIVE_ONLY 后释放 pin
  -> 保留旧 kdlock/registry，卸载并重载测试源码模块，核对旧 RIP/原锁地址确实复用
  -> 同样八个角色制造原生竞争，各 A 的 Linux wait_list 达到 3
  -> 六个新记录原生完成，无新增 JIT/frame/代理 ACK -> 正常卸载完整会话
```

两组采用不同的词法 entry。普通 miss 会把对应 entry 置为 CALL_MISS/not-ready，
因此不能假定同一 entry 随后仍可派发；测试不改写发布状态，也不恢复 daemon
来维持执行。该用例要求两个 native frame 的存活区间重叠，不要求两段 JIT
指令在同一时刻运行，更不验证并发重编译或不可变版本。

在已确认 recovery、CPU 0-13 可用、调用者和模块均排空的 guest 执行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_PARALLEL_FIRST=0 \
  bash tests/live/test_23_mutex_parallel_native.sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_PARALLEL_FIRST=1 \
  bash tests/live/test_23_mutex_parallel_native.sh
```

`KD_MUTEX_PARALLEL_FIRST` 默认 0，仅接受 0/1，决定哪组先完成，不改变锁协议。
脚本显式加载并读回 `mutex_jit=1`，只通过 `mutex_parallel=1` 的 opt-in workload
复用 mode 3 ioctl；普通 mode 3 不变。`mutex_parallel_armed` 只能在准备完成后
置 1；双 frame 分支还显式开启/读回 `native_resume_rename=1`。除下述内置改名、
peer 和原 waiter 信号流程外，不要与其他信号、资源注入、remote-chain
或其他 workload 参数混用。
脚本在非 shared-CPU 分支自动使用 `mutex_parallel_source_hold` 暂停两组 native
callee，最长 10 秒；控制端等待两次 arrival 和原生 C 返回最多 6 秒，子进程
readiness/退出/读取
各有 3 秒边界。无论观察是否失败都会释放测试暂停并等待所有 worker，但失败
不能算通过。它只改变测试调度，不构造 frame 或 owner。
双 frame 分支构建 `KDLOCK_SELFTEST=1 KDLOCK_NUMA=0`，保留实际加载的模块副本，
供 shadow 表只读观察和额外锁 promotion；shared-CPU 分支保持默认构建。
只有调用者和模块均排空后才恢复默认 SELFTEST=0 构建，不能改写加载中的代码。

验收同时要求两个有效产物、匹配各自 entry/A 的返回后 body witness、两个真实
callee RIP 和设备 CALL_MISS target、四次 task/lock 匹配的 owner ACK。两个
`kd_parallel arrive` 必须早于第一组 resume，第一组 done 必须早于第二组
retained-owner 检查。每组 12001 次串行准备加三个竞争请求，共 12004 次 A/B
临界区执行；检查独立 sequence/digest，以及六个竞争请求恰好一次的 record。
第一组逻辑 A ACK 不要求物理 A 已释放，combiner 仍可保留它完成自己的批次。

`Evidence:` 下保留 `published.json`、`after.json`、`protocol.json`、两组镜像
前后哈希、八个角色日志/退出码和最终 dmesg。准备不足、串行化到没有 frame
重叠、超时或重复副作用都算失败，不能用聚合 `started=completed` 替代逐任务检查。
等待超时只让测试角色有机会释放自己持有的锁；不丢弃委托请求，也不替 owner
解锁。仍有 ioctl worker 时保留模块，按 recovery 流程处置，不强制卸载。
`source-busy.json` 先记录 OPEN 时 modules=1/frames=2/writers=0，再记录真实
fork/exec 使 writers=1，父进程退出后引用仍在。EBUSY 后只有 state 变为 DRAINING；
子进程真实读取 16 字节 callee 文本，并确认 header-only 发布返回 ESHUTDOWN。
`source-retired.json` 要求 frame=0/writer=1 时仍 EBUSY，子进程最终关闭后才验证
源码 pin 阻止普通卸载、全部 entry 失效、modules/frames/writers 归零和新 writer
拒绝。`writer/` 保存子进程身份、读取哈希、关闭记录及日志。driver 调用生产
`compile_entry()`，只替换 Python 脚本为引用探针；不能把这个子进程计为翻译/JIT。
失效前的 CALL_MISS 证据单独保留在 `after.json`，不会被退休覆盖。

随后脚本自动使用 `mutex_parallel_retired=1` 重载同一个测试模块。这个测试参数
只改变 native callee 的 owner 判定和等待队列观察，不改译后前缀或生产锁协议。
`source-reload.json` 记录 ELF 中两个外层 `mutex_lock` CALL 的确切返回地址、
模块 SHA256、重载前后函数/锁地址及旧 registry，要求地址确实相同，不允许将
地址未复用算作通过。同一个 RETIRED provider 保留到第二轮结束，不重新启动
daemon、不改 entry 状态，也不重复预热。`reloaded/` 保存同样八个竞争角色的
退出码；真实 Linux 等待队列必须各出现三个 waiter，六个新记录的 before/held/
called/after 都为 1，每组 sequence=3、digest=486、最终 A/B owner 为 0。
oracle 先严格检查两个 reload marker 之间的原生记录和零 JIT/ACK，才将该区间
与原来的 JIT 记录分开校验；marker 缺失、未提供 metadata 或多出的 JIT 都失败。
原来的四个 ACK、24008 次转换和最终 provider 统计仍须通过，不能被重载阶段掩盖。

#### 改名后的原生嵌套与解锁

两名借用 A/B 的原 waiter 在原生 callee 中复用 `kd_test_rename()` 改为
`kd_renamed`。该测试 helper 在 task lock 下修改本线程 comm，不调用未导出的
内核 API、不新增 task 引用，也不在 JIT 中执行改名。先观察两名 waiter 的
arrival，再分别调用普通 `mutex_lock/unlock(C)`，C 为各 lane 独立的新 mutex。

此时 source 仍 OPEN，comm 已不匹配目标；解锁 hook 必须依赖 active-task
记录进入 hook。C 的获取走原生路径，其真实 owner 为 waiter 自己；C 的 unlock
不得消耗 A 的路由引用或生成 A/B 的 owner ACK。`kd_parallel routed native:`
检查 C 的获取/释放各一次、释放后 owner=0，以及 A/B 仍由原 combiner 持有。
控制器收到两条完成记录后才开始资源压力，不能用稍后关闭 source 后的路由
代替这一 OPEN 阶段检查。

waiter 在之后的资源压力、peer 取消/重排及 DRAINING 阶段保持改名。B/A 的
两个 ACK 和 post-unlock done 都发生后才恢复 `klock_test`，防止提前恢复名称
掩盖 active-task 路由丢失。观察器逐 task/lock 检查顺序、真实 owner、comm 和
抢占/IRQ 状态；`protocol.json.native_routing` 要求两个改名 waiter、两次 C
获取/释放和两次 ACK 后恢复名称。C 不增加 JIT/frame/ACK，也不混入原来的
24008 次 A/B 状态转换；shared-CPU 与退休后重载分支均不执行此扩展。
清理必须同时检查 `kd_renamed`，不能因名称变化漏掉仍在途的 worker。

#### 保留 B 与原生竞争者

双 frame 分支自动设置只读参数 `mutex_parallel_peers=1`，shared-CPU 与退休后
重载阶段保持 0。在代码池及 shadow 压力队列均排空、两组 native callee 仍被
暂停时，CPU 12/13 各启动一个单进程 `mutex_signal_client`，参数为
`0/1 kd_native parallel-peer`，
selector 分别为 22/23。不向 benchmark 的 pthread 或 timeout supervisor 发信号：

1. 读取 B 的真实 owner，并与对应旧 frame 的 owner 身份核对；调用原生
   `mutex_trylock(B)` 必须失败，然后调用原生 `mutex_lock_interruptible(B)`。
2. 短 ioctl（selector 24、loop_count=1）在 `B.wait_lock` 下遍历两张真实 Linux
   wait_list，分别观察恰好一名匹配的首次 peer。最多等待 10 秒；调用前 ready
   标志不够，optimistic spinning 也不能计作已经进入 wait_list。
3. 控制器为两个 PID 打开 pidfd，先核对未退出、单线程/TGID、comm、实际可执行
   文件与完整参数，并匹配内核排队 task。两者都通过后才各发送一次 SIGUSR1。
   任一身份不符不发送；pidfd 绑定身份，不添加测试持有的 task_struct 引用。
4. `mutex_lock_interruptible` 必须返回 EINTR，peer 仍有非致命 pending signal、
   已从自己的 Linux wait_list 移除、没有获取/释放 B，两个旧 A/B owner 均未变。
   不清除信号或修改 owner；ioctl 把 EINTR 暴露给用户态，信号处理器计数必须为 1。
5. 客户端仅在这次预期失败后明确发起第二次 ioctl，同一 task/PID 才能领取重试。
   再次 trylock 失败后进入普通 `mutex_lock(B)`；selector 24、loop_count=2 必须
   重新观察两名 peer，不能复用首次排队日志。两次设备快照都要求
   OPEN/modules=1/frames=2/writers=0。
6. 只有两者取消并重新排队后才向两个原 waiter 发信号，再进入 writer/retire
   流程、释放暂停门。
   第一组 waiter 解 B 时仍通过真实 owner 执行；它的原生竞争者随后取得 B，
   在持有这把 B 时尝试另一把 B，必须失败且其 owner 仍为另一 combiner。
7. 第一名竞争者真实 `mutex_unlock(B)` 后才发布完成位。第二组原 waiter
   同时等待第一组最终 ACK/done、该完成位和下面的任务退出观察门，再检查自己保留的 A/B
   再继续。第二名竞争者最终取得/释放自己的 B；所有 supervisor 均须 join。

两名 peer 都使用原生 Linux mutex，不能成为 JIT 执行者、借用其他 owner 的锁或
产生 kdlock ACK。每名 peer 的 acquired/released 计数必须各为 1，受 B 保护的
值必须正确；整个组合仍只有两个 JIT body 和四次原 waiter 的 owner ACK。
五个失败 trylock 分别是两个初始检查、两个重试检查和第一名 peer 的跨 B 检查；
第二名 peer 的 `cross_try=2` 表示不执行跨锁尝试，不是 Linux API 返回 2。

`native-peers/` 保存两个客户端的三段日志、退出码、两轮排队观察及 `signal.json`。
最终 `protocol.json.native_peers` 要求 failed_tries=5、queued=4，
cancelled/acquired/released 均为 2；`native_peer_signals` 另要求两个 pidfd 信号、
两个用户态 EINTR 返回及两个明确重试。CLI 的 `--native-peers` 需要该证据目录，
不再是仅启用内核日志检查的布尔开关。
校验器同时核对 task、owner、lock 和时间区间，不将聚合计数当作竞争证明，
也不允许将 peer 记录藏入退休后 reload 区间。这里只取消原生 peer 的 Linux 等待，
不放弃已代理请求，不引入 owner handoff 或额外 task 引用；不证明公平性、任意
退出/取消顺序或通用 hook reader 生命周期。原无取消的版本由同一用例升级，
不再增加一轮基础前置；初次无取消验收仍保留在 VALIDATION 的历史记录。

#### 原 Waiter 的信号与退出

在相同两种排空顺序中，逻辑 waiter 的客户端参数为
`0/1 klock_test parallel-waiter`，selector 为 `8 * lane + 2`。每名客户端只执行
一次 ioctl，不自动重试 EINTR；在原生 callee 中仍改名为 `kd_renamed`。
这不同于上面的非目标 peer 取消 Linux 等待：原 waiter 已有 JIT 副作用和借用的 A/B，
不能丢弃请求、转移 owner 或重跑入口。

1. 两个 frame 完成原生 C 操作、资源压力及 peer 重新排队后，控制器核对
   OPEN/modules=1/frames=2/writers=0、两组 arrival 和当前均无 ACK/resume。
   两个 pidfd 都要通过 PID/TGID、单线程、exe、完整 argv、comm 与 kernel task 检查。
2. 两名原 waiter 都核对成功后，给 `FIRST` 对应进程发 SIGKILL，另一名发 SIGUSR1。
   此时两者都必须仍存活；写出 `waiter-signals.ready` 后，主脚本才建立 orphan
   writer、关闭 source 准入并释放 `mutex_parallel_source_hold`。
3. 第一名 waiter 在原生代码中检查 pending/fatal 均为 1，完成原有 record 和
   B/A owner ACK，再从系统调用退出时被 SIGKILL 终止。不得出现其用户态返回日志。
4. 第二个真实 frame 最多在 `mutex_parallel_exit_hold` 等待 10 秒。控制器保留
   同一个 pidfd，观察第一名任务确实退出，并等待 DRAINING/modules=1/frames=1/writers=1；
   第二名 pidfd 必须尚未退出。此时 dmesg 中第一组已有完整 ACK/done，第二组还没有 resume。
5. 控制器释放第二道测试门，第二名 waiter 核对原 A/B owner、pending=1/fatal=0，
   完成后缀和两个 ACK；ioctl 成功返回并观察恰好一次 SIGUSR1。其余原检查继续执行。

`waiter-signals.json` 保存发送时间、两个 pidfd 身份、退出后的 source 状态及
当时 dmesg 前缀的长度/哈希；最终 oracle 将该前缀与完整日志核对。
`waiter-controller.log`、两个 `role-*-2.log` 和 `role-status.tsv` 必须共同匹配：
仅索引 `4 + FIRST` 的 supervisor 退出码为 137，其余七个为 0；超时的 124 不是通过。
`protocol.json.original_waiter_signals` 要求两个信号、一个 fatal exit、一个保留的
native frame 和一个非致命信号后的返回。只看到 137、ACK 或 `/proc` 消失都不够。

成功与失败路径都释放测试门并 join 控制器，不替真实 owner 解锁，不额外持有
task_struct 引用。共享 CPU、退休后重载和普通 mode 3 不启用这个扩展。
这证明的是一次有界的“信号待处理直到内核后缀完成”流程，不支持 native 后缀
直接 `do_exit`、遗弃未完成 frame、任意 task/RCU 生命周期或通用 hook 热卸载。

仅该工作负载/路由观察器变化时，在 guest 选择相关单元和原有复杂用例：

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_mutex_parallel_protocol.py test_mutex_resources.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case parallel-drain-0 --case parallel-drain-1 --case parallel-node-pressure
```

前两个入口组合改名路由、peer 取消/重排、原 waiter 信号/退出、容量和退休；第三个保护共享驱动的真实
节点压力。若修改共享信号客户端，再追加 `test_mutex_signal_protocol.py` 和
`native-peer-1/3` 两项 live，分别保留 SIGUSR1/SIGKILL 协议；不把它们作为
每次改名路由修改的前置条件。原 waiter 信号/退出组合的本次冻结证据见
[验收记录](../VALIDATION.md#original-waiter-exit)，改名路由的初次验收保留在
[历史记录](../VALIDATION.md#renamed-native-frame-routing)。

#### 代码池耗尽

代码池阶段只在上述双 frame 分支执行，不新增用例名称。daemon 停止后，
先对独立的 `kd_pool_lock` 做 12000 次必要晋升准备，不运行翻译；随后才 arm
原来的两组竞争。两个 frame 都到达 native 后，一个新 ioctl 顺序调用 64 个
`noipa`/`noinline` 函数，各有真实 `mutex_lock` CALL，全部操作原生锁并检查
一次性记录。原池已有两个 JIT 条目及冷入口，因此后部站点无法注册，末站点
必须缺席。
这是真实代码块分配耗尽，不通过修改计数、合成 key、缩小池或重写 registry 制造。

接着在 CPU 8/9/10/11 启动该独立锁的 holder/owner/waiter/trailing caller。
holder 等待三个真实 kdlock 队列节点；后三者使用最后一个未注册站点。owner
尝试代理 waiter 时，`mutex JIT not ready` 必须匹配其真实 task、waiter、entry、
lock 和 CPU 9，然后走未执行交接。三个请求均由自己持有并解锁原 mutex，记录
各更新一次，不产生 JIT body、native frame 或 owner ACK。三者返回时两个旧
frame 仍存活，之后才允许 source retire/DRAINING、旧请求续跑和原来的四个 ACK。

`code-pool.json` 保存 prepare/held/filled/drained 四个只读快照，要求 frame
数为 0/2/2/2、源码会话仍 OPEN、没有 writer，最后注册表恰有 64 个不同块。
已有条目及其块不变，新条目保持 UNINIT，最后站点不存在。初次从已加载模块
ELF 的 `mutex_lock` 重定位求确切返回地址；后续仅在模块哈希和全部函数加载
地址相同时复用这些偏移，不重复耗费持锁观测窗口解析同一 ELF。
四阶段 dmesg、`code-pool-fill.log`、`code-pool-queue/` 的四个退出码一并保留。
最终 `warm=12000 filled=64 claimed=63 updates=12067 lock=0` 不能代替逐请求
owner/值检查；退休须使全部 64 个条目失效，重载后同一旧表保持 terminal。
先验证重载区间再验证代码池区间，拒绝把额外代码池事件藏进重载区间。

两份镜像上的实际 JIT 仍只有原来的两个 body，64 个冷站点及新增的
三个原生请求不计为 JIT。此处验证根请求在 wrapper 前的回退，不是进度中断
后的恢复包/GPR 证明；不覆盖全部 511 个槽、代码回收、并发镜像替换或任意资源
组合。结果与失败准备记录见 [代码池验收](../VALIDATION.md#code-pool-with-live-frames)。

#### Mutex Shadow 表耗尽

双 frame 分支同时设置只读参数 `mutex_parallel_shadow=1`，普通 mode 3、
shared-CPU 和退休后重载保持 0。准备时，观察器从模块 ELF 获取真实 mutex
数组基址、步长及唯一 `mutex_lock` CALL 返回地址；通过已有 SELFTEST promotion
参数晋升这 1025 把锁，不写 shadow 表。计数参数 `mutex_selftest_shadow_count`
仅在 SELFTEST 构建存在，在实际表锁下只读统计已分配槽，不缩小 1024 槽容量。

1. 原代码池队列排空且两个旧 frame 仍暂停时，selector 25 顺序获取/释放这
   1025 把原 mutex。真实 hook 分配剩余 shadow 槽；表满后的新锁在路由引用和
   节点登记前直接转原生。每个临界区核对自己的 owner、是否存在 shadow 及
   恰好一次状态更新，不运行翻译或 JIT。
2. CPU 8 的非目标 `kd_native` holder 使用 selector 26 持有最后一把无 shadow
   的 mutex；CPU 9/10 的两个目标请求用 selector 27/28 获取同一把锁。
   holder 在 `wait_lock` 下观察恰好两个身份匹配的真实 Linux waiter 后才解锁。
   三名角色各更新一次保护值，必须以自己的 task 为原生 owner，均无 shadow。
3. 三名 supervisor 全部 join 后再次采样。prepare/held/filled/drained 的 source
   必须仍 OPEN、modules=1、writers=0，frame 数为 0/2/2/2；计数从实测旧占用
   增加到 1024。此处 drained 仅指新压力队列，不能表示旧 frame 已排空。
   然后才运行 B peers、writer 退休及两个旧 frame 的原有四次 ACK。

`shadow-pool.json`、填表日志和 `shadow-pool-queue/` 保留上述身份、快照及退出码。
`protocol.json.shadow_pool` 检查 1025 个不同锁的记录、三个排队请求和逐个匹配的
`mutex shadow fallback`；新增数必须等于 1024 减实测旧占用，不能硬编码旧占用。
所有记录均处于两个旧 frame 的重叠区间，不能藏进后面的重载区间。更新值在
解锁前保存，日志在解锁后输出，不要求两个目标请求的日志顺序等于持锁顺序。

这是未启动请求的 shadow 分配失败与真实原生互斥，不是新 JIT 正例，也不证明
PENDING 恢复包或任意资源耗尽。原两个译后 body、独立 B 竞争、四个 ACK、退休
及地址复用断言均保留；结果见 [shadow 验收](../VALIDATION.md#mutex-shadow-with-live-frames)。

这是真实队列/JIT/native/owner-ACK 的组合测试，不使用构造 frame 或额外 task
引用。它不固定 RCU 读者，不替代 6.2 的延后释放证明，也不单独采样全部 GPR；
测试模块在整个 ioctl 中有自身 fops/module 依赖保护，这不证明通用源码模块
热卸载安全；源码、锁对象和 hook 的不同寿命见 [DESIGN 3.1](../design/lifetimes.md#31-source-lock-and-hook-lifetimes)。
完整寄存器续跑仍由[操作章节](../JIT_EXECUTION.md#3-环境与操作)的 register gates 验证。它本身不耗尽节点；同 CPU
节点压力见[同 CPU 的 mutex 拒绝](mutex_protocols.md#67-同-cpu-的-mutex-jit-拒绝)。跨 NUMA/远端多请求、其他资源组合和 native 后缀内直接退出
仍需后续实现或验证。
