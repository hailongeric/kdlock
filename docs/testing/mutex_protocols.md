# Mutex 协议测试库存

本页按角色与所有权维护既有断言；运行入口见 [测试说明](../../tests/README.md)。
部分旧准备量和 CPU 放置尚未适配当前本地热锁发现，不能把历史 PASS 当作当前
通过。执行与恢复边界见 [JIT 执行指南](../JIT_EXECUTION.md)。

### 6.1 Mutex 资源与恢复包

```text
__kd_mutex_lock_clobber_v1 / __kd_mutex_lock（旧调用者）
  task 已在代理路径 / 未晋升 / mutex_jit=0 -> 原生 mutex
  shadow 表满 / task 登记失败 -> 原生 mutex；不登记 JIT、不预留 node
  登记 task、请求翻译及 ABI -> _kd_mutex_lock_abi
    gate 空闲 -> 获取原生 mutex；physical_owner=current
    gate 忙且没有 node -> 保留 task 登记，在自身栈上等 gate，再获取原锁
    gate 忙且有 node -> 保存入口状态 -> 汇编 slowpath / 队列
      未执行交接 -> 先取得原锁，再释放 node、恢复调度状态，返回原临界区
      clobber COMPLETE -> 放弃旧 C 帧，仅保存三个续点字段，清理 node/task 后恢复
      FULL / 旧 ABI / native -> 释放 node 前保留完整 pt_regs，恢复调度状态
        -> 已完成跳到 unlock 后 / native 跳到当前续点并保留 owner ACK
```

`test_mutex_resources.py` 提取生产的节点函数、shadow 查找、hook、入口与
原锁获取/释放辅助函数。它检查 256 个占用/可用栈组合、顺序与乱序复用、
非法释放、满表碰撞及已有条目不变，以及 cold/已有 shadow 下的 hook 回退。
真实 `_kd_mutex_lock_abi` 分别从 hook 和直接 API 接收三种合法 slowpath 结果。
在恢复抢占的替身中立即复用刚释放的 node，随后比较整个 guest `pt_regs`
（当前 168 字节），确认 consumer 使用自己的副本。native 续跑保留 task
登记与物理 owner；borrowed unlock 只能交给通知入口，不能由 waiter 直接解锁。

变异负例同样要求先编译成功，再由断言检出。物理锁、task API、调度、
汇编 slowpath 和跳转指令均为替身：这里不执行 JIT，也不证明真实 owner ACK、
RCU、抢占并发或硬件 flags 恢复。它不模拟任意故障或授权入口重放。
真实执行继续由 mode 3/4/5、寄存器续跑、`test_11` 和深度/远端矩阵验收。
6.7 的满槽扩展将其中的 no-node 路径与另一个真实存活的 JIT/native frame
组合；6.6 另补真实 shadow 表满及原生竞争，但仍不能替代这里的缺栈、碰撞、
已有条目不变和完整恢复包边界。

#### 同队列的同 CPU 续跑

`native-4-4` 现将普通 PENDING 检查升级为同 CPU 原 waiter 续跑，不另增日常
用例或先运行旧的简单版本。它使用 `mutex_jit=1`，保留真实 B 竞争、JIT 前缀、
当前 CALL 包续跑和最终 A owner ACK。`KD_NATIVE_SHARED_CPU` 默认 0，只接受
0/1；启用必须为 mode 4、stage 4、`KD_NATIVE_PENDING_CONTENDED=1`，不与其他
注入、信号、寄存器、源码/栈变化等变体组合。非法组合在 live 准备前拒绝。

七个真实角色中，A 的 waiter/combiner/trailer（role 0/4/6）全部绑定 CPU 4；
其余 role i 绑定 CPU i：role 3 是 A holder，role 1/2/5 是 B 的原生
holder/direct/trailer。mutex 测试屏障使用 `cond_resched()` 让同 CPU 角色
有机会推进，调用点不持 raw lock、不禁止调度；spin 屏障不变。生产锁协议、
node 容量和 guest hook 不变，也没有创建第二个 JIT context：

```text
A holder 等待三个实际队列请求后释放 A
  -> combiner/CPU 4 持有原 A，代理 waiter 的真实 JIT 前缀
  -> B CALL 的 PENDING 阶段注入 E2BIG；保留当前 RIP/GPR/虚拟 CALL 栈
  -> 原 waiter/CPU 4 从 mutex_lock(B) 续跑，进入原生 B 的 Linux wait_list
     combiner 仍是 A 的物理 owner，暂停该批代理；不重放入口
B 原生 holder 解锁 -> waiter 真正取得 B，核对 A owner 未变
  -> waiter 完成 B 的剩余工作并自行解 B
  -> waiter 请求 borrowed A unlock，同 CPU 的真实 owner 处理并返回最终 ACK
  -> waiter 核对一次性记录和执行上下文 -> 所有角色、node/引用及模块排空
```

这里的 E2BIG 仍来自 `jit_fail_pending_lock=2`，不是自然容量耗尽；真实发生的
是同 CPU 排队/调度、B wait_list 竞争、原生取得 B 和 A owner 通知。最终逻辑
ACK 不要求物理 A 已释放：combiner 的批次可能仍需持有它。

`role-cpus.tsv` 和 `role-status.tsv` 保存请求绑定及七个退出码；内核 role 日志
关联实际 task/self/CPU。`pending-contended.json` 还要求 JIT body 与 entry/A
一致、PENDING 包与 native_begin 的 RIP/SP 一致、waiter/两物理 owner 身份正确，
并检查获取 B、最终 ACK、完成记录的顺序。获取 B 和 ACK 后完成记录均在 CPU 4，
`preempt=0 irq=0`；before/called/after 各一次、返回值正确。只设置 taskset
或看到聚合成功计数不足以通过。

修改该驱动/观察器时，选择以下相关单元及复杂 live，不附带基础 sweep：

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_regression.py test_mutex_signal_protocol.py test_native_after_outer.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case native-4-4 --case registers-4-3 --case waiter-usr1
```

后两项保留独立的完整 GPR/返回栈与真实信号合同，并覆盖共享驱动的非同 CPU
路径。直接定位可使用 `KD_NATIVE_SHARED_CPU=1 KD_NATIVE_PENDING_CONTENDED=1`
运行 `test_10_native_resume.sh 4 4`，仍须事先确认 recovery。本节不替代 6.7 的
跨队列 context refusal，也不证明任意超额订阅、公平性、flags 或 RCU 生命周期。

### 6.2 Task 引用、最终 ACK 与 RCU

正常获取路径由 `kd_mutex_task_get()` 建立 acquisition 引用；同一 task 的多次
获取共用一个表项，表项持有一个真实 `task_struct` 引用。native 续跑不额外
增加 acquisition 引用，也不由 waiter 提前释放已有引用。

```text
task get -> 发布 RCU 可读记录 -> 保留物理 owner 的 native_begin
  waiter 请求 unlock -> owner 的 native_wait 处理
    B->A：真实 owner 解 B；最终逻辑 A ACK 后，物理 A 可留到 owner 批次结束
    A->B：提前解物理 A；仍保留 B 的 owner 和 task 记录，直到最终 B unlock
  本 frame 的保留锁全部逻辑释放
    -> 从 native frame 表移除 -> task put
       最后一个 acquisition 引用：hash_del_rcu -> call_rcu
    -> release 发布 ACK，waiter 才能返回并丢弃请求栈
  旧 RCU 读者退出 -> 回调 put_task_struct + kfree
```

`test_22_mutex_task_lifecycle.sh` 在发布 guest hook 之前启用
`KDLOCK_SELFTEST` 探针，直接调用生产 task、frame 和 native request 函数。
三个固定在不同在线 CPU 的 kthread 分别充当 owner、waiter 和 RCU 读者。
读者从记录仍在表中时开始，跨越最终 ACK 后才退出。两种解锁顺序都检查：

- 真正的分配失败不发布记录；两次 get 共用表项，非最终 put 保留路由。
- 中间 ACK 后，剩余原锁仍由 combiner 持有，task 记录仍有效。
- 最终 ACK 返回时记录已不可查、重复通知不再路由，但旧读者的记录内存未释放。
- 等待读者和工作线程退出，再用 `rcu_barrier()` 确认真实释放回调恰好执行一次。

在已确认 recovery 快照且没有模块/调用者运行的 guest 执行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/live/test_22_mutex_task_lifecycle.sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_TASK_CPUS=0,20,21 \
  bash tests/live/test_22_mutex_task_lifecycle.sh
```

第二条使用当前双 NUMA guest 的 CPU 编号；其他拓扑须先核对。
每次预期 `orders=2 acks=4 deferred_frees=2 failures=0 JIT=0`，并要求内核无
错误、task/frame 排空。脚本保存 `Evidence:`、卸载自测模块并重建默认版本。
若核心协议断言失败，探针会 fail-stop，不能带着存活读者/请求卸载代码。

这是实际内核协议测试，但不执行 JIT。续跑 RIP/RSP 是不跳转的构造包；outer
batch 回调只释放真实 A，不运行生产队列调度。测试不证明汇编跳转、任意信号/
退出竞争、多请求远端调度或热卸载安全。自测入口与释放计数在默认构建中均不存在。

### 6.7 同 CPU 的 Mutex JIT 拒绝

复用 `test_23`，仅将 lane 1 的 combiner 从 CPU 5 改到 CPU 1，与 lane 0 共用
CPU；逻辑 waiter 仍在 CPU 2/6。两组 entry 都必须先发布 NORMAL，daemon 随后
停止，不注入 context、不改代码状态、不构造 frame。此场景强制 lane 1 先完成：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case parallel-shared-cpu
# Equivalent direct invocation, only in the confirmed recovery guest:
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_PARALLEL_SHARED_CPU=1 \
  KD_MUTEX_PARALLEL_FIRST=1 bash tests/live/test_23_mutex_parallel_native.sh
```

```text
lane 0 combiner/CPU 1 -> JIT 前缀写入，取得 A0/B0 -> 普通 CALL miss
  -> waiter/CPU 2 进入 native callee，暂不解锁；combiner 可调度但保留 frame
lane 1 holder 等到上述真实 native 到达后，才释放 A1
  -> lane 1 combiner/CPU 1 取得原 A1，尝试执行已就绪的 waiter entry
  -> context_busy：CPU 1 的 frame 属于另一 task，返回 NO_RUN，未调用 wrapper
  -> combiner 完成自己的原生 CS，再由被拒绝 waiter 取得原 A1/B1
  -> lane 1 waiter 自己完成 CS、解锁并发布 done；不借用 owner、不产生 native ACK
lane 0 waiter 看到 lane 1 done，重新检查 A0/B0 owner 和此前写入
  -> 完成原生后缀 -> 原 combiner 确认 B0/A0 unlock -> 全部调用者排空
```

这里未执行的 lane 1 从原始临界区入口运行是正常队列交接，不是失败重放；
已经执行 JIT 的 lane 0 仍只从当前 callee RIP 续跑。kernel module 仅新增
`mutex JIT context busy:` 定位日志，记录 combiner task、waiter、entry、lock、CPU，
不改变既有拒绝分支、guest hook、物理 owner 或两元素 ABI。

oracle 交叉核对拒绝日志、原生 combiner 身份、waiter/owner、两个 entry 的前后
设备状态和 body witness：要求恰好一次 context refusal、至少一次同 CPU node
多槽预留，只有 lane 0 的 entry 有 body/变为 CALL_MISS，lane 1 的 entry 仍 NORMAL。
lane 0 到达必须早于拒绝，lane 1 done 必须早于 lane 0 恢复；不以聚合计数代替
此存活区间证明。每个记录和 A 保护的 sequence/digest 仍须恰好一次且 owner 排空。

该场景的预期是 **1 个 JIT body、1 个 native frame、2 次 owner ACK、1 次拒绝**；
不能记成两个 native frame 重叠，也不能把整个测试归类为无 JIT 的拒绝负例。
`role-cpus.tsv` 保存全部角色绑定，`after.json` 保留未执行入口仍就绪的证据。
这是一个有界的同 CPU 调度组合，不证明任意超额订阅、公平性、IRQ/NMI 栈深度或
所有寄存器/RCU 生命周期；这些仍保持独立测试和现有限制。

#### 节点满槽与 task 分配失败

跨队列同 CPU 拒绝回归使用 `parallel-node-pressure`，覆盖上述合同后再增加真实
node 耗尽和另一新请求的 task 分配失败，不先重复 `parallel-shared-cpu`。
后者仍可单独点选作故障定位。node 容量是真实占满，task 分配失败使用已有
单次注入，不能把两者都写成自然资源耗尽：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case parallel-node-pressure
# Equivalent direct invocation, only in the confirmed recovery guest:
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_PARALLEL_FIRST=1 \
  KD_MUTEX_PARALLEL_SHARED_CPU=1 KD_MUTEX_PARALLEL_PRESSURE=1 \
  bash tests/live/test_23_mutex_parallel_native.sh
```

`KD_MUTEX_PARALLEL_PRESSURE` 默认 0，仅接受 0/1；启用必须同时使用 shared CPU
和 FIRST=1。它额外将 lane 1 的两个 follower 放到 CPU 1，并启动第九个角色
（lane 1、role 5、selector 13）；观察到满槽后才设置
`mutex_task_fail_once=1` 并启动第十个角色（lane 1、role 6、selector 14）。
两个额外请求均绑定 CPU 1，不修改生产容量或注入 node/context：

```text
lane 0 combiner/CPU 1 保留 node、原 A0/B0 和真实 native frame
lane 1 holder/CPU 4 持有 A1；owner/waiter/trailer 在 CPU 1 排队占用另外三个 node
  -> role 5 已取得 A1 task 引用，但取得不到 node；日志关联 task/entry/A1，slots=f
  -> 控制脚本设置 task 单次失败，再启动 role 6；核对另一条 task fallback 日志
     role 6 在取得 A1 task 引用和进入其私有队列之前失败，直接等原生 A1
  -> 两种拒绝均观察到后打开 fixture release gate；holder 自己释放 A1
  -> role 5 在自己的栈上等私有 gate，再取得原生 A1；role 6 不等这个 gate
     两者都真实持有 A1/B1 并完成一次 CS，不借锁、不执行 JIT、不发 owner ACK
     与 lane 1 队列谁先获取不作公平性假设
  -> lane 1 队列仍触发一次 context refusal，原生完成自己的 CS
lane 0 waiter 等 lane 1 waiter 和两个额外请求都完成，才重查原 A0/B0 owner 并续跑
  -> 保留原 owner 的 B0/A0 ACK -> 所有角色、引用、node 和模块排空
```

`mutex_parallel_pressure_release` 只是测试 holder 的释放门，默认 0；脚本最多
为每种拒绝轮询 120 次、每次间隔 50ms。任一观察失败仍打开门并 join 已启动的
所有调用者，然后将测试判为失败。它不能代表原锁已经解锁，也不能制造 node
或 owner ACK。脚本要求单次 task 注入已消费；不能只看参数写入成功。
workload 的等待有 10 秒上限，超时仍是失败，不允许提前卸载存活的 kdlock frame。

验收要求 lane 0 native arrival < 满槽拒绝 < task 分配拒绝 < lane 1 context
refusal，两个额外请求都完成于 lane 0 resume 之前；核对独立 task/record、own owner 和
完整副作用。只有 lane 0 的 entry 执行 JIT 并变为 CALL_MISS，lane 1 仍 NORMAL。
该组合预期 **1 个 body、1 个 native frame、2 个 ACK、1 次 context refusal、
1 次 node fallback、1 次 task fallback**。lane 0/1 分别 12004/12006 次 CS，
共八个竞争记录。`pressure_done=3` 是两个完成位，不是三个请求。
`pressure-observation.log`、`task-observation.log`、十个角色退出码和
`protocol.json` 随原证据保留。

生产仅增加 node/task fallback 定位日志。两者都是未启动请求，不是 JIT 失败后
的入口重放；node 日志记录 bitmap，因为缺失 shadow stack 也可能拒绝预留，
单看 node_overflow 不足以证明四槽全满。task 拒绝仅说明尚无 A1 路由引用；
原生后缀的 B1 hook 仍可按现有规则建立自己的记录，不能禁止或漏掉其配对释放。
这是一个有界组合，不证明真实内存耗尽、任意超额订阅、公平性、重命名路由或
任意任务退出安全；独立 RCU/信号/寄存器用例仍须保留。

### 6.12 同 CPU 的嵌套 Mutex JIT

以下保留该用例的角色和判定定义。当前禁止抢占忙等策略下，2026-09-17 的
重跑出现 soft lockup，详见 [失败记录](../../tests/README.md#mutex-pinned-mode4-failure)。
旧版可调度等待的 PASS 不适用于当前策略；同 CPU 的进度依赖需要满足
[独立可运行条件](../design/locking.md#pinned-busy-polling)，未进行旧版对照来确定本次故障归因。

既有 `mode-4` 的第一阶段使用七角色、两个 CPU，替代此前七个角色各占一个 CPU 的放置。
`test_08_mutex_jit_modes.sh` 加载测试模块时启用 `mutex_nested_schedule=1`；
mode 5 显式关闭该观察器。生产锁、节点容量、物理 owner、两元素 args 和 guest
内核不变；该观察器不是访问时 guard，也不新增条件码保护或 native 续跑出口。

| 角色 | CPU | 用途 |
| --- | --- | --- |
| 0 | 1 | 被代理的 A/B 嵌套请求，最终回到自己的任务 |
| 1 | 0 | B 初始原生 holder；确认 A executor 真实入队后才释放 B |
| 2 | 1 | B 直接 waiter |
| 3 | 0 | A 初始 holder |
| 4 | 0 | A 直接 waiter，成为嵌套请求的 combiner/executor |
| 5 | 1 | B 后继 waiter |
| 6 | 1 | A 后继 waiter |

```text
warmup/promotion -> 翻译生成物 -> 对应 RIP/TGID 发布为 NORMAL
  -> 先启动 A/B holder，再启动其他角色；原生准备屏障允许 cond_resched
  -> A holder 释放 -> role 4 持有原生 A，执行 role 0 的 JIT
  -> JIT 在嵌套 B lock CALL 退出 wrapper，留下实际 body witness
  -> executor 走原生 mutex 等待 B；同 CPU 的 B holder 得以运行
  -> holder 在 B.wait_lock 下发现 waiter.task 正是 A 的物理 owner
  -> 核对双方 CPU 0 和不同 owner 身份，释放 B
  -> executor 获取 B，恢复并完成本次 JIT，按原协议释放锁
  -> 七个原始任务返回，随后停止 daemon、退休/卸载并核对最终状态
```

仅 `nested_queued` 增加不足以证明实际等待，因为该计数可能先于入队。
观察器只读 B 的真实 wait_list，并在其 wait_lock 下采样 PID/CPU；释放该锁后不再
解引用 waiter，也不增加 task 引用。等待十秒仍未观察到时记录错误并允许 holder
继续释放 B，不能把超时后原生完成算成通过。角色 CPU/身份/IRQ/preempt 日志均在
原始任务上采样，不进入翻译正文；退出时必须与入口一致，IRQ/preempt 均为零。

`mutex_signal_protocol.py nested` 将实际角色、owner、等待事件、NORMAL 发布和唯一
entry/A 匹配的 body witness 关联，并要求七个 worker 退出零、无 native frame/ACK。
驱动另查 `jit_success>=1`、`nested_queued>=1`、`nested_jit>=1`、`jit_resume=1`、
复杂 A/B 状态、精确总计数和零错误。`Evidence:` 目录保留角色日志、CPU/退出码 TSV、
`published.json`、观察器开关、最终日志和 `protocol.json`，统一 runner 收入协议归档。
daemon 在角色运行时仍然存在，只在工作完成后停止；该实验不提供不可变版本保证。

```sh
# Guest only: affected oracle and two existing mutex cases.
make -C tests/unit run TESTS= PY_TESTS=test_mutex_signal_protocol.py
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case mode-4 --case mode-5

# Explicit OOO diagnostic when that branch is affected; not another routine case.
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_OOO=1 bash tests/live/test_08_mutex_jit_modes.sh 4
```

OOO 复用同一角色和判定，另保留原有 A-before-B 解锁分支/精确计数，仍须全程 JIT
完成，没有原 waiter native 后缀。普通 `mode-4` 另包含下述
[共享原生 B 阶段](mutex_protocols.md#615-两个-a-combiner-共享原生-mutex-b)；显式 OOO 变体只运行
本节阶段，不重复与 OOO 无关的共享 B 负载。此前三项的归档及实际结果见
[VALIDATION](../VALIDATION.md#mutex-nested-scheduling)。
本节验证 executor 为同 CPU 的 holder 让出运行机会；6.1 的 `native-4-4` 则检查
PENDING 后原 waiter 续跑和 owner ACK，6.7 的 `parallel-node-pressure` 检查独立队列
context/node 拒绝。三者不能互相替代。四个角色安排在 CPU 1 不证明四个节点同时
占满；这些有界观测不证明任意超额订阅、公平性、task/RCU 生命周期或 flags 正确性。

### 6.15 两个 A Combiner 共享原生 Mutex B

普通 `mode-4` 在七角色/双 CPU 阶段排空并保留生成物后，重新加载独立模块会话，
以 `mutex_jit=1 mutex_shared=1` 检查 A0、A1 共用同一个原生 mutex B。
这不是 spin 的远端 B combiner：两个 A executor 分别调用原生 mutex 获取 B。
测试片段在 `workload_modules/lock_scenarios/fragments/mutex_shared_workload.c`，仍由既有驱动/协议单元承接，
不新增日常 case，也不取代独立 B 的双 frame 退休/信号用例。

| 角色 | CPU | 用途 |
| --- | --- | --- |
| 0 / 4 | 0 / 4 | A0 / A1 初始 holder，等本地三个请求入队 |
| 1 / 5 | 1 / 5 | A0 / A1 直接 waiter，成为各自物理 combiner |
| 2 / 6 | 2 / 6 | 被代理的嵌套请求；A0 有普通 CALL miss，A1 完成 JIT |
| 3 / 7 | 3 / 7 | A0 / A1 队尾，保留真实批处理/交接条件 |
| 10 | 8 | 获取 B 前改名为非目标 `kd_native`，使用 Linux 原生 mutex |

```text
两条 root 分别 warmup 1 次、promotion 12000 次
  -> 三个生成物（包括随 warmup 提升的 B）全部等待 NORMAL 发布
  -> 从已加载模块的两个真实 mutex_lock CALL 返回地址选择 A0/A1 entry
  -> 停止 daemon，记录镜像哈希，再设置 mutex_shared_armed=1
  -> A0 executor 执行 JIT，写入前缀并持有原生 A0/B
  -> 普通 CALL miss：保留 callee RIP/CALL SP，交回 role 2 原生续跑
  -> role 2 的观察器开放 A1 holder 和非目标 peer 的工作负载门
  -> A1 executor 执行自己的 JIT 前缀，在同一个 B 的 Linux wait_list 上等待
  -> 原 waiter 在 B.wait_lock 下两次观察 A1 executor 与 peer 均实际入队
  -> 确认 A0/B 仍属于 role 1，A1 属于 role 5，A1 尚未执行 B 数据操作
  -> role 2 完成原生后缀，请求真实 owner 执行 B、A0 的 unlock/ACK
  -> A1 获取 B 并完成 JIT；peer 以自身为真实 owner 获取/释放 B
  -> 九个调用者全部返回，再退休/卸载、检查记录和模块排空
```

真实等待队列只读；锁内采样 task PID，离开 wait_lock 后不再解引用 waiter，
也不增持 task/frame 引用。两次保留状态观察相隔约 10ms，等待超时记为失败，
只允许工作负载的原 owner 正常释放锁，不伪造 ACK。观察器属于明确的普通
CALL miss 原生后缀，不进入生成代码，不新增指令退出或 flags 保护。

`mutex_signal_protocol.py shared` 关联两个源 CALL 返回地址选出的 NORMAL A entry、
两个匹配 A/entry 的 `body=1`、一个 `held=2` 的 native frame、B/A0 两次 owner ACK，
以及非目标 peer 的真实 owner。还要求 `jit_success=jit_resume=nested_queued=nested_jit=1`。
两个 root 均应 `before=held=after=12002`、各有 12005 次 A 访问，完整数值按全部
12002 次操作独立重算；B 的复杂状态总计 24005 次。A0 取得第 24003 次，后两次由
A1 和 peer 分别完成，不假定二者获取顺序；ACK 日志位于原生 unlock 之后，不能要求
它一定先于新 owner 的日志。所有原始任务最终 IRQ/preempt 均为零。

每阶段各保留 `final.log`、`protocol.json`、发布/CPU/退出码及 `artifacts.tar.gz`。
共享阶段还保留 source objdump、CALL 返回地址、所有生成物的发布记录和前后镜像哈希。
额外 B 镜像不是额外远端 B 执行证据；case 最终 dmesg 也不能代替第一阶段的日志。

```sh
# Guest only; mode-4 already includes both phases.
make -C tests/unit run TESTS= PY_TESTS='test_mutex_signal_protocol.py test_mutex_stack_protocol.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case mode-4 --case mode-5 --case registers-4-3
```

普通 CALL miss 会改变对应条目的学习状态，因此先停止 daemon，避免本轮重编译；
这不是不可变版本机制。固定角色/有界等待不证明任意取消、公平性、锁对象生命周期，
更不补齐已延期的访问检查、局部或通用 flags 语义。结果单独记入 VALIDATION。
