# Spin 协议测试库存

本页按角色与所有权维护既有断言；运行入口见 [测试说明](../../tests/README.md)。
部分旧准备量和 CPU 放置尚未适配当前本地热锁发现，不能把历史 PASS 当作当前
通过。执行与恢复边界见 [JIT 执行指南](../JIT_EXECUTION.md)。

### 6.3 Spin 虚拟请求取消与续跑

`test_10` 的 `KD_NATIVE_VIRTUAL_RESOURCE=1/2` 复用 mode 8 stage 4 的真实
A/B 持锁者、A 代理队列和 B 的 Linux pending-bit 竞争者。与较早的
`jit_fail_pending_lock` 不同，它在 `kd_spin_nested_lock()` 已建立真实虚拟
ticket、增加一次 preempt pin、并发现私有 B 忙之后才改变资源输入：

```text
combiner 持有 A -> JIT 执行前缀写入 -> lock(B) CALL 为 PENDING
  -> 保存原 CALL 包，暂存 post-CALL RIP/RSP
  -> 取得真实虚拟 ticket/pin -> B 的私有 gate 忙
  -> 1: 当前函数的 context 视图置 NULL -> 原分支返回 ENOMEM
     2: 本 CPU node count 暂设为 4 -> 原分支尝试后减回 4，返回 E2BIG
  -> 原 cancel 路径注销 ticket、归还 pin；尚未发布 B 请求
  -> 自测恢复唯一的合成 count，并核对完整存储及 A/B 持锁状态
  -> finish_known_lock_call 恢复当前 lock(B) 的 RIP/RSP
  -> 原 waiter 在 Linux B 上排队，保留 A 的 combiner 等待通知
  -> B 可用后 waiter 取得/释放 B，后缀副作用恰好一次
  -> A 的 unlock 交回原 owner，最终 ACK 后排空；本次不重返 JIT
```

在已确认 recovery 快照、voluntary/none 抢占且调用者/模块均排空的 guest 执行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_VIRTUAL_RESOURCE=1 bash tests/live/test_10_native_resume.sh 8 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_VIRTUAL_RESOURCE=2 bash tests/live/test_10_native_resume.sh 8 4
```

脚本检查 CPU 0/1/2/3/4/6/8 可用，自动构建 SELFTEST，并始终保持
`jit_fail_pending_lock=0`。不可与 node trace、shadow pressure、rename 等探针
叠加。单次只消费一次只读加载参数，失败的协议断言会 fail-stop，须按 recovery
流程处置；不能在工作线程存活时强制卸载。

验收要求生成物、返回后的 `body=1`、正确的工作负载状态，以及同一个 task、
entry、A/B 地址贯穿取消、native begin、B 排队/取得和最终 ACK。探针比较全部
`pt_regs`、CALL 栈字、frame、节点/context 数组和 combiner shadow 状态，核对
ticket 消失及 pin 平衡；原有 staged RIP/RSP、原生队列和恰好一次断言不放宽。
脚本保留 `virtual-resource.log` 等证据，排空卸载后重建默认模块。

以上两个出口是实际 JIT/原锁/取消/续跑的组合测试，但不是自然池耗尽证明：
context 原本已分配，仅局部视图被置空；count=4 不代表四个真实存活节点。

#### 真实 ticket 耗尽

`KD_NATIVE_VIRTUAL_RESOURCE=3` 复用相同的七角色拓扑，但不注入 context 或
count。脚本在 daemon 停止后，通过既有 SELFTEST 参数晋升 62 把独立测试锁。
CPU 4/6 上的两个 A 候选者各实际获取 31 把，均经过普通 hook、ticket 和原锁
路径；两组锁不共享，不能因此串行化 A 队列。它们跨越各自的 A 获取/解锁，
始终属于原物理 task，不加入逻辑 waiter 的借锁记录：

```text
CPU 4/6：各持 31 把独立原锁、31 个真实 ticket/pin -> 加入 A 队列
  A 的物理 combiner 持有 A，实际占满本 CPU 的 32 个 ticket
  -> 代理原 waiter，JIT 执行前缀写入 -> lock(B) 为 PENDING
  -> kd_spin_entry_begin 找不到空槽，返回 E2BIG；未发布 B ticket
     临时 preempt_disable 已配平，原 32 个 ticket/pin 均保留
  -> 只读探针检查完整 packet/frame/node/context/shadow 未变
  -> 同上交回原 waiter，在原生 B 上排队，完成一次后缀和 A 的最终 ACK
  -> 候选者各自完成 A，重查 31 把原锁仍由自己持有，再逐把解锁归还 pin
```

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case virtual-ticket-refusal
# Equivalent direct invocation in the confirmed recovery guest:
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_VIRTUAL_RESOURCE=3 KD_NATIVE_GATE_PRESSURE=1 \
  bash tests/live/test_10_native_resume.sh 8 4
```

每个候选者的 `kd_ticket held` 检查 31 个真实 gate owner、公有/私有锁字与
preemption 增量，`released` 必须报告 31 把锁全空、pin 增量归零。
拒绝日志 `kind=3 allocated=0 injected=0` 区别于前两个已预留后取消的出口；
共有的 `retired=1` 表示失败后没有 B ticket，并不表示曾成功预留。脚本还要求
该 combiner 的持锁区间跨越实际拒绝、native begin 和最终 ACK。
额外持锁代码的入口只注册、不翻译，不算额外 JIT。探针在 SELFTEST 构建中只观察，
不减少生产容量、不合成资源失败，也不改变两元素 wrapper ABI。

真实容量用例替代日常 `native-1-4` 的简单 PENDING E2BIG 注入；后者仍可通过
`--case native-1-4` 单独诊断。context/node 取消发生于 ticket 已分配之后，不能
被本例替代。三者均不证明发布后恢复、任意抢占/任务退出或 flags 恢复。
`virtual-ticket-refusal` 现在默认加入以下真实 gate 表压力，不再日常重复其旧
版本；直接调用时不设置 `KD_NATIVE_GATE_PRESSURE` 仍可隔离原 ticket 诊断。

#### Native 续跑窗口内的 gate 表压力

`KD_NATIVE_GATE_PRESSURE=1` 只允许组合 mode 8 / stage 4 / pending contention /
virtual resource 3。原七个角色和完整 PENDING/ticket/寄存器检查不变，另外需要
CPU 9/10/11 的三个压力角色、CPU 12 的控制脚本和 CPU 13-18 的六个 A2/C 角色。
准备时额外晋升 A2，走一次不获取 C 的 warmup，并等待第七份生成物和 A2 的
NORMAL 发布。随后停止 daemon；C 仍是数组最后一把尚未分配 gate 的锁。
高位 selector `0x40000000 | role` 仅用于这个测试：role 3 是 CPU 13 的 A2
holder，4/5 是 CPU 14/15 的候选者，6 是 CPU 16 的逻辑 waiter，7 是 CPU 17
的 trailer，8 是 CPU 18 的非目标 C holder；role 9 仅准备时 warmup 一次。

```text
真实 JIT 写入 -> ticket E2BIG -> 原 waiter 在 B 的 Linux 队列中等待
  B holder 已观察到该 waiter，保持 B；A combiner 保留 A 和 31 个额外锁
  -> 记录当前 gate 占用、source frames=1、原 A/B 物理 owner
  -> CPU 9 的目标线程顺序获取/解锁 1025 把不同测试锁，填满真实 gate 表
  -> CPU 10 的非目标 holder 获取最后一把无 gate 的原生 L
  -> CPU 11 的目标线程真实分配 gate 失败，在同一 Linux L 上排队
     holder 观察公有锁字的 pending/tail；两个角色按原生互斥完成写入
  -> join 三个冷入口角色，旧 native frame 仍存活
  -> CPU 18 的非目标 holder 再次持有最后一把无 gate 的 C
  -> CPU 13-17 建立 A2 的 holder、两个候选者、逻辑 waiter、trailer 队列
     两个候选者分别占用 pending bit 和 private head，实际有三个 MCS waiter
  -> A2 combiner 执行已发布 JIT，提交 before/value 前缀，调用 lock(C)
     ticket 仍有空位，但 gate 表满，真实返回 ENOMEM；没有发布 C 请求
  -> PENDING 包恢复 callee 和原 CALL SP，原 waiter 在 C 的 Linux 锁上等待
     不重放 A2 前缀；A2 仍归 combiner，旧 A/B 也仍被保留
  -> CPU 18 观察真实 pending/tail，控制器读取 source frames=2，再允许 C 解锁
  -> 原 waiter 取得 C，核对已提交前缀，完成一次 C/A2 后缀并自行解锁 C
     A2 unlock 交给真实 owner 并等待 ACK，join 六个 A2/C 角色
  -> drained 快照要求 gate 仍满、source frames 回到 1
  -> 控制脚本允许旧 B holder 解锁，原 waiter 完成后缀和 A 的最终 ACK
  -> 原候选者释放额外 ticket/pin，全部调用者排空，退休并卸载
```

准备阶段只通过现有 SELFTEST 参数控制新锁的 promotion，不填造 gate 条目。
`spin_selftest_gate_count` 只在 map guard 下读实际占用；`kd_gate refusal` 标识
真实查找失败的 task/CPU/原锁。三个冷入口角色使用相同的已定位 ELF CALL，不能
把注册或其原生写入计为 JIT。A2 的外层入口和内层 CALL 返回地址另从实际 E8
指令及 ELF relocation 定位；`PENDING_LOCK_NATIVE error=-12` 必须匹配该入口、
callee、原 SP 和已暂时推进的 return/SP+8，不能以普通 observer CALL miss 替代。
新增请求的 JIT witness 必须对应 A2，不能借用旧 A 的 witness。逐锁记录检查 membership、
写入次数和值、公有/私有锁字与 pin 配平；最终全数组检查不能只看循环总次数。

`gate-pool.json` 保留模块 SHA256、真实数组/入口和 prepare/held/filled/progress/drained
快照，frame 数依次为 0/1/1/2/1。每次快照均重查 A2 的 NORMAL/code 元数据和
三份生成文件哈希；这不是不可变代码版本保证。最后两个快照分别位于 C holder
的受控等待期间、六角色退出之后，旧 frame 始终仍存活。
`gate-protocol.log` / `gate-result.json` / `gate-role-status.tsv` 进入统一归档。
B/C holder 的有界等待不交接 owner；控制器出错仍释放测试等待条件、join
已有角色并保留失败，不能因此生成 PASS。`native_gate_progress_release` 仅释放 C
测试 holder，`native_gate_release` 最后释放旧 B；不得在仍持锁时强制卸载。

旧 gate 压力阶段只检查 **未开始** 原生回退；新增 A2 检查 **已经执行 JIT** 后的
PENDING gate 失败。两者不能互相替代，也不能证明任意资源组合、硬件 flags、
访问时检查或任务退出。原逐锁数组仍有 1025+2 次更新；A2 使用独立 before/inner/
after/value 记录，必须为 2/1/2 且满足精确值递推。整个会话恰好两个 native
begin/complete 和两个最终 A ACK，按 task/entry 分别关联，不只检查总数。

修改此扩展运行 `test_spin_gate.py` 和 `test_spin_outer_progress.py`，再运行
`virtual-ticket-refusal`、共享驱动的 `virtual-node-refusal`，不加新 case 或基础
smoke。outer fixture 用真实 map/ticket/nested producer 和 PENDING helper 对比
完整软件包、frame/node/context/shadow；CPU/原锁原语是替代实现，实际 JIT 和
Linux 排队由 live 用例验证。修改 entry API 或回归选择器时，才追加相应单元。
在已确认 recovery 的 guest 中执行这组增量：

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_spin_gate.py test_spin_outer_progress.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case virtual-ticket-refusal --case virtual-node-refusal
```

初版与后续验收分别记录在 [冷入口压力](../VALIDATION.md#spin-gate-pressure) 和
[已执行前缀的 gate 失败](../VALIDATION.md#progressed-spin-gate-refusal)。

修改共享 SELFTEST 加载/清理逻辑后，还应回归原有 CPU-local shadow 容量用例。
它在 CALL advance 和虚拟 ticket 申请之前拒绝，不等同于上述两个出口：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_SHADOW_CAPACITY=1 \
  bash tests/live/test_10_native_resume.sh 1 4
```

### 6.8 物理 Frame 链与容量检查

当前 spin 物理 frame 使用执行者 task 内核栈。观察器从实际 task 栈边界计算
RSP 采样余量，日志标记 `stack_kind=1`；不向活栈填色，也不在任务退出后读取
该栈，因此输出 `written_left=null`。历史 8KB shadow 栈日志仍由旧 watermark
分支严格校验；两种指标不能混用。最新两层定向结果见
[spin 栈验证](../../tests/README.md#spin-stackless-validation)，旧八层结果不代表
删除独立栈后已重跑八层，也不能用一次采样证明任意栈深度或异常安全。

八层物理 frame 用例中的每个新 frame 都从 CPU-local 锁记录栈继承此前记录，
不是每层只有自己的一个记录。第八层的 `jit_lock_depth=8`、local depth=8；
它调用第九把锁时，先触发逻辑记录容量检查，尚未到达后面的 local-shadow
容量检查。native continuation 只向本 frame 的 owner 借用自己的外锁，
因此日志中的 `kd_native begin: held=1` 不能反推拒绝时只有一个锁记录。

```text
真实请求逐层入队 -> CPU 0 形成八层 combiner/frame，执行八个 JIT body
第八层准备第九把锁 CALL -> 继承锁记录已满 -> E2BIG / PENDING
  -> 当前 GPR、RIP/RSP、CALL 返回字、combiner 和全部物理 owner 保留
  -> 第九把锁仍未获得，也未建立当前执行者的 acquisition ticket
  -> 原 waiter 从该锁 CALL 续跑，完成剩余临界区并取得外锁 owner ACK
  -> 其余 frame 逐层返回，验证全部精确记录并排空
```

`spin_selftest_trace_frames=1` 复用现有 CALL 前后观察点，新增 drain 后输出的
`kd_frame held refusal:`。它逐字节比较 `pt_regs`、CALL 返回字和 frame；唯一
允许的 frame 变化是 `control_call` 成为原 CALL 的 PENDING 包。同时检查继承
链上的八个物理锁/私有 combiner 字节与真实 owner、combiner 状态、CPU/node
计数和抢占/IRQ 状态。快照使用静态存储，深层路径不分配、不打印、不填锁或
修改执行状态；未到八层时不得出现这条证据。它不是完整 RFLAGS 语义证明。

修改该观察器时，先选基础和相关单元；仅涉及日志判定时无须 live。需要验证
深层继承锁记录拒绝时，再显式选择以下两项八层用例；它们不是日常必跑清单：

```sh
make -C tests/unit run TESTS= PY_TESTS='test_regression.py test_spin_frame_protocol.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case node-physical-8-0 --case node-physical-8-1
```

两项分别构建 NUMA-aware 关闭/开启的 SELFTEST 模块，均实际执行 spin JIT，
`mutex_jit=0`，不涉及 mutex JIT 验收。独立 `shadow-capacity` 必须保留：它取得
七把测试私有原生锁并登记到 local shadow，使当前逻辑深度 1、local depth 8，
专门到达后面的 local-shadow 分支；不能将这种测试管理的占用写成自然物理链。
frame-push 容量探针、单 frame 三锁 mode 6、寄存器/RCU 和注入取消出口也不是
该用例的重复项。真实八层记录耗尽通过不证明所有资源或任意深度/IRQ 安全。

#### Frame 回收门禁

`kd_exec_frame_pop()` 除物理 LIFO、context 和 remote 引用外，还检查 native
请求及解锁路由。ERROR/COMPLETE 只是状态，不能单独授权回收：

```text
frame_push -> 初始化空 native_link，保留 source/provider 引用
  -> native_begin 挂接仍持锁的 frame，原 waiter 从当前 callee 续跑
  -> waiter 发布解锁请求 -> 原 owner 执行、清空请求，最终移除 native 路由
  -> owner 发布 request.done ACK，完成自身 frame，再调用 pop
     -> 仍有 remote/native 引用：EBUSY，输出包/存储/引用不变
     -> 已满足原有终态与 LIFO 条件：按需复制输出包、退休有效槽、释放 frame 引用
```

waiter 可能在 owner pop 后才输出 ACK 日志；要求的是 owner 的发布顺序，不是
两个 CPU 的日志时间顺序。门禁自身不发送 ACK、不摘除路由、不解锁，也不提供
失败重放或一般任务退出恢复；调用方仍必须完成原有 native 等待协议。

现有 `test_exec_capacity.py` 在 ERROR/COMPLETE frame 上分别保留 native 请求、
路由和两者，核对完整 context、输出 `pt_regs`、请求字及会话引用都不改变。
覆盖两个后端和现有多层/双 CPU 替代环境；移除任一拒绝条件须触发断言，而非
把编译失败、崩溃或超时当成检测。链表、CPU 和引用仍是替代原语，构造的坏终态
不是已观测到的 live UAF；实际 ACK/排空由原有复杂 native/remote 用例验证。
共享 allocator 的另一生产消费者是 spin combiner 单元，定向运行两项：

```sh
# Guest only; no extra baseline or new test entry.
make -C tests/unit run TESTS= \
  PY_TESTS='test_exec_capacity.py test_spin_outer_progress.py'
```

修改共同回收门禁时，live 选择应包含普通 JIT 完成、两后端 native/GPR、双 frame
owner ACK、无锁 remote relay 和深层物理 frame；不要仅以一个 mode 的成功外推。
它不改变两元素 args、frame 的生命周期约束、guest 内核或已延期的访问时检查。
本次八项实际选择、带超时的执行命令、旧代码负例和修复版证据分别保存在
[回收门禁验收](../VALIDATION.md#native-frame-retirement)，没有新增日常 case。

### 6.9 无锁祖先与 Waiter 退出

`remote-late-3` 复用四个真实执行者的 mode-8 跨 NUMA 链，在原有逆序解锁、
重命名和 native observer 检查中加入 waiter TID 退出边界，不另增日常用例。
`KD_DEEP_WAITER_EXIT=1` 只允许 depth=4、stage=3，且 owner/reverse/rename/cross
均开启；不能与 deferred/readmission/refusal/node trace 组合。直接脚本默认 0，
统一选择器仅为 `remote-late-3` 开启它，stage 2/4 不受影响。

```text
准备并确认五个 entry 已发布 -> 停 daemon -> 启动原有十八个角色
  -> 原 waiter 的请求在 A/B/C/D 四个真实 owner 上执行 JIT
  -> JIT 经六次远端通知，按 C/B/A 逆序释放三把祖先锁；D 仍保留
  -> 普通 CALL miss 逐层传回同一当前寄存器包
  -> root native_begin：waiter 尚未唤醒；捕获其 PID 身份并记录 arm
  -> 原 waiter native 续跑、完成记录并取得 D 的最后一次 ACK
     子 frame 正常完成；root 已无锁/解锁请求，但暂不完成自己的 frame
  -> waiter 从 ioctl 返回并正常结束线程，原 PIDTYPE_PID 脱离任务
  -> root 观察 detached=1，核对完整 frame/寄存器包、CPU、抢占和 IRQ 状态
  -> 释放 PID 身份引用，再用缓存 PID 完成 root frame；全部角色退出并排空
```

观察器仅在 `KDLOCK_SELFTEST=1` 构建中存在。脚本在翻译准备后，才将实际 A 地址
写入 `spin_selftest_exit_lock`；仅匹配一次真实的零剩余锁 root，不改 frame、
队列、锁容量或 ACK。快照允许的唯一变化是子 frame 发布 remote DONE。
等待上限五秒，超时也释放测试阻挡，但 `detached=0`/`valid=0` 必须判失败。
脚本排空卸载后恢复 SELFTEST=0、NUMA=0 默认构建，不替换加载中的镜像。

使用 `get_task_pid(..., PIDTYPE_PID)` 保留的是 PID 身份，不是 `task_struct`
引用；每次查询单独持 RCU 读锁，不通过 PID 数字重新查找，也不解引用已退出
waiter 的 task 或栈。PID 脱离不代表 task 内存已完成 RCU 回收。这不是任意退出、
临界区内主动退出或取消未完成代理请求的证明，不能替代独立 RCU/信号用例。

oracle 要求 `arm < 最后 ACK < 完整请求记录 < detached release < root complete`，
并逐项匹配 task、实际 owner、CPU、锁、entry 和续点。原有四个 returned body、
四个 native frame、六次远端通知、一次 owner ACK 及精确副作用检查均保留；
五个生成物不等于五个被执行的镜像。执行流改动只选相关复杂路径：

```sh
make -C tests/unit run TESTS= PY_TESTS='test_regression.py test_remote_depth_protocol.py test_remote_outer.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case remote-late-3 --case remote-late-2
```

两项均加载 `mutex_jit=1`，但这里实际执行的是 spin JIT，不是 mutex 后端验收。
第二项保留四个真实 owner ACK，用于检查仍持锁祖先不被延迟观察器影响；不是
基础 smoke。证据包含 arm/release、参数回读、十八个角色日志、发布状态、
SELFTEST 镜像和默认恢复构建；本次结果只维护在 [VALIDATION](../VALIDATION.md)。

### 6.10 提前释放 A 的原生依赖

`native-spin-outer-dependency` / `native-mutex-outer-dependency` 将已有
`test_10` 的 OOO=3、dependency=2 分支纳入对应 native 范围，不增加脚本。
两项均加载 `mutex_jit=1`；前者 mode 1 执行 spin JIT，后者 mode 4 执行
mutex JIT。它们检查 A 已释放、B 仍被代理持有时的真实容量退出及原生参与者
依赖，不是普通 held-B CALL miss、全 JIT 非 LIFO 解锁或 RCU 构造探针的重复项。

```text
非目标线程持有 C（第七把 child），等待已发布的 JIT 前缀
  -> combiner 的 JIT 取得 A/B 和六把 child，形成八条锁记录
  -> JIT 写入前缀并提前释放原 A；B 和六把 child 仍由原 owner 持有
  -> C CALL 因逻辑记录满返回 E2BIG，A 的已释放记录不会被当作空槽
  -> 原 waiter 从当前 PENDING C CALL 续跑，不重放 JIT 前缀
非目标 C owner 取得已释放的 A，核对 B 仍由另一 executor 持有
  -> 完成 A 的原生工作并释放 A/C，使 waiter 能够取得 C
  -> waiter 自行解 C，经六次 child 通知和最终 B ACK 完成后缀
  -> 原队列 owner 完成自身请求；所有角色、锁记录和引用排空
```

容量保持生产值，没有 `jit_fail_pending_lock` 注入；C owner 使用真实 Linux
锁。oracle 核对 A release、PENDING 包、原生 owner/comm、七把 child、七次 ACK
顺序及每条副作用记录，公共驱动另要求匹配生成物的 returned body witness。
C owner 的进展不能用“整个测试最终返回”替代；这里不声称 C 必然观察到了
Linux wait_list，也不证明任意 ABBA 死锁可恢复或其他退出阶段均正确。

生产 early-A/通知逻辑改动时选择这两个复杂入口；只改选择器仍只跑选择器单元
和预览，不因新增名字重复执行旧负载：

```sh
make -C tests/unit run TESTS= PY_TESTS=test_regression.py
bash tests/run_all.sh --suite spin-native --suite mutex-native --dry-run
# Guest only, when the early-A protocol itself needs live acceptance:
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case native-spin-outer-dependency --case native-mutex-outer-dependency
```

普通 stage-3 的两个 `native-1-3` / `native-4-3` 由同后端、同阶段的寄存器
用例覆盖：仍运行同一业务路径、native probe 和 B->A 后缀，额外检查原始 GPR
与 CALL 栈。仅将这两个普通成功检查移出套件，显式点选仍运行；不把它们的
替代关系扩展到本节的提前 A 释放或其他 OOO 阶段。

两个依赖分支已用当前栈分析/执行器重新做 live 验收，见
[early-outer continuation](../VALIDATION.md#early-outer-continuation)；选择器单元与
此前旧版的执行结果仍按各自来源记录，不拼接成完整矩阵。

### 6.11 Spin 获取后的受检续跑

`native-spin-acquired` 复用 `test_10` 的 mode 1 stage 3 嵌套临界区。
它与普通 CALL miss、PENDING 资源拒绝是不同退出边界，不能因为使用同一
负载就合并掉检查。统一入口设置 `KD_NATIVE_SPIN_ACQUIRED=2`，启用测试模块的
`native_acquired_queue=1`，用真实 B 私有队列替代旧 FAST 日常版本；不增加用例数。
该参数的 1 仍可直接调用脚本做 FAST 诊断，0 为关闭。非零值只允许该 mode/stage，
不能组合寄存器、OOO、信号、资源或栈变化变体；非法组合在构建/加载前拒绝。
排队版本要求 CPU **0、1、2、3、4、6、8** 可用，七个真实 hook 调用者分别固定
到这些 CPU；不修改节点、私有锁字、容量或生产返回值来安排测试结果。

```text
准备/发布 JIT -> 停止 daemon -> 开启一次 spin_jit_fail_after_nested_lock
  -> CPU 1 持有 B；CPU 3 持有 A，4/6 排在 A 上
  -> 原 waiter (CPU 0) 排入 A，CPU 8 随后排入；A holder 才释放
  -> A combiner 执行原 waiter 的 JIT 前缀，提交 prefix++
  -> B lock CALL 已前移 RIP/RSP；虚拟 B 节点先入队，CPU 2 后继再排入
  -> B holder 只读确认两名 private waiter、prefix=1、suffix=0，然后释放 B
  -> A combiner 从 B 队首取得原锁，成为本地 QUEUE_OWNER，发布 shadow/锁记录
  -> 获取后注入 EIO，phase 仍为 ACQUIRED
  -> 核对本地记录、真实 owner、CALL token 与 post-CALL 包
     -> 有效：标记 SPIN_NATIVE，原 waiter 从 CALL 后继完成剩余临界区
        -> 检查 A/B owner 仍为 combiner，suffix++，完成原有复杂 B 状态计算
        -> B unlock 通知真实 owner 并等待 ACK；CPU 2 此后才能取得 B
        -> A unlock 最终 ACK -> completed++ -> 七个调用者退出并排空
     -> 无效：保留错误与当前状态，不重放入口或再次获取 B
```

仅 Linux 原锁 B 忙不足以覆盖该分支：私有队列为空时仍可走 FAST，再等原锁。
这里必须同时看到真实两节点排队、`kind=2` 和后继自己的 owner。等待屏障位于
JIT 之外或已退出后的原生后缀，有界超时会报错并让 holder 继续释放；超时不能
算通过。前缀计数器用于检测入口重放，不重复复制 B 的完整状态计算，避免单为
观察器增加一份相同的分析负担；原有复杂状态机和寄存器探针仍保留。

`finish_acquired_spin_call()` 只接受本地 spin 的 `-EIO`、合法可借用 frame、
无 pending remote/request、顶层未释放的 FAST/QUEUE_OWNER 锁记录且 node 为空。
锁地址必须等于 RDI；private gate 必须仍处于持有状态且 owner 是当前执行者。
原始目标必须是 `_raw_spin_lock`，RIP/RSP 必须等于返回地址/CALL RSP+8，
原 waiter 栈内的返回地址字须经 nofault 读取核对。所有检查完成才发布新 tag；
GPR 和内存均不回退，原锁不转移 owner。native 注册再次校验 tag/backend 和
post-CALL 包；一般 ACQUIRED 状态仍被拒绝。

该 live 用例要求单次注入已消费、匹配 entry/A 的返回后 body witness、唯一
`SPIN_ACQUIRED_NATIVE` 与 native begin 的 RIP/RSP、仍持有 A/B 的记录、B/A
两次有序 owner ACK，以及完整业务状态/逐请求记录。排队版另核对
`prepared/prefix/suffix/completed/queued/trailer` 均为 1、零失败、七个调用者成功
退出、唯一 native frame 和后继获取 B；只调用一次 CALL 后观察器，不能返回本次
JIT。不能只用翻译文件、warning 或最终计数作为通过依据。

```sh
# Guest only: workload/oracle/selection changes, without repeating basics.
make -C tests/unit run TESTS= \
  PY_TESTS='test_native_after_outer.py test_regression.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case native-spin-acquired --case native-spin-outer-dependency
```

若修改共享执行器/续跑包，才扩大到 `test_control_call`、
`test_spin_outer_progress.py`、`test_mutex_outer_progress.py` 及
`registers-8-3` / `registers-4-3`；不是每次观察器修改的前置步骤。
单元夹具核对完整 `pt_regs`/有界栈不变及坏包、owner、阶段等拒绝分支，锁原语
仍是替身。live 对应获取后注入边界，不是硬件异常恢复；它不在新出口采集完整
硬件 GPR/flags，独立的寄存器用例仍保留。远端已发布操作、任意 EIO、任意栈
修改或其他指令失败不获准恢复；不新增 guest hook、owner handoff 或 wrapper 参数。
当前排队验收和此前 FAST/寄存器证据分开记录在
[VALIDATION](../VALIDATION.md#queued-spin-acquisition)，不拼接成新完整矩阵。

### 6.14 两个独立 Root 共享 B Combiner

`mode-8` 有三个独立模块会话：原有复杂 CFG/内层竞争、
`test_20_remote_outer.sh multi` 的双根纯 JIT、`multi quota` 的混合 native/JIT。
测试模块只读开关 `spin_multi_roots=1` 选择
`spin_multi_workload.c`，不创建测试 frame/node，也不修改原锁 owner。原有远端
深链跟踪一个 logical waiter；本阶段检查两个独立 A 请求同时等待同一 B 队列。

| 队列 | role / 固定 CPU | 分工 |
| --- | --- | --- |
| A0 | 0、1、2/3、4 | root、holder、pending/head 两个直接竞争者、尾随者 |
| A1 | 5、6、7/8、9 | 第二条独立 root，其他角色同 A0 |
| B | 10、11/12、13 | holder、pending/head 两个直接竞争者、尾随者 |

需要 CPU 0-13 均在线且在允许集合中；采集实际拓扑，不按 CPU 数字推断 NUMA。
pending-bit 参与者不算 MCS waiter。两个直接竞争者谁先到可变，oracle 接受
各队列合法 head，但两个 remote child 必须使用同一个 B executor。

纯 JIT 双根阶段的执行顺序：

```text
第一阶段通过 -> 保存其 dmesg 与全部生成物 -> 退休/卸载后的新模块会话
  -> 分别 promotion 三把锁 -> 无竞争注册两条 root -> 三个入口发布 NORMAL
  -> 停止 daemon/翻译者，保持代码不变 -> 启动 14 个固定 CPU 角色
  -> 两个 A holder 等各自 root 和尾随者入队，再释放原锁
  -> 各 A combiner 执行对应 root 的 JIT 前缀，再向 B 发布 virtual request
  -> B holder 观察两条前缀已执行、后缀未执行及不同 A owner，然后释放
  -> 同一个 B combiner 依次运行两条 child JIT
  -> 各 A combiner 恢复对应 JIT 后缀 -> 所有原调用者 unlock 后返回
  -> join、退休/卸载 -> 核对状态、身份、发布和返回后 body witness
```

每条 root 有独立 token/value、before/after 计数；A0/A1/B 复用复杂状态 oracle。
含准备阶段在内，三个状态分别为 12007 / 12007 / 12009 次转换，总计 36023；
两条 root 各执行两次，其中一次无竞争注册、一次实际代理。B 下记录的共享序号
必须为 12006 和 12007。`remote_outer_protocol.py --multi` 关联两个逻辑 task、
不同 A owner、共享 B owner/CPU、同一已发布 entry 和四个返回后 body witness；
14 个调用者成功、原 task 身份不变且 IRQ/preempt 干净，native 计数全部零。
不能只凭翻译成功或最终总计数接受，也不能将 native 回退作为本阶段通过。

#### 混合完成、Waiter 退出与 B 后继

`multi quota` 额外设置只读测试参数 `spin_multi_quota=1`。A1 holder 在释放前
等待 B 队列已有 A0 virtual request，以真实排队保证 root 0 在前。两个 root
仍必须已提交 A 前缀且未执行 A 后缀，B holder 才释放。此阶段单独构建 SELFTEST
provider，设置只读 `spin_selftest_exit_after_ack=1`；准备完成后，根据已加载
`multi_locks` 的地址和 ELF 数组大小，把 `spin_selftest_exit_lock` 绑定到 B。

```text
B combiner 执行 root 0 的 child JIT、复杂 B 更新
  -> 前 16 次时钟服务返回 JIT，第 17 次触发现有 CALL_LIMIT_NATIVE
  -> 保留同一 callee/CALL RSP，B frame 和 A0 relay 注册 native 借用
  -> B native_begin 在唤醒原 waiter 前取得其 PID 身份引用，不增持 task 引用
  -> 原 waiter 执行第 17 次服务、剩余原生后缀；不重跑入口或返回本次 JIT
  -> 原生观察器在有界区间检查 B owner 未变、root 1 的 B 数据尚未更新
  -> B unlock 交回真实 owner；清除 B 的 parent/路由并发布 ACK
  -> B 在已校验的 frame pop 前暂停；A0 owner 独立完成最终 unlock/ACK
  -> 原 waiter 正常返回 ioctl 并退出，RCU 读段内观察其 TID 已脱离
  -> 旧 B frame/寄存器包及 CPU/preempt/IRQ 保持不变，释放 PID 引用并正常 pop
  -> 同一个 B combiner 才执行 root 1 的 child JIT；root 1 正常完成
  -> 两条 root 原调用者返回；确认原三个注册的 entry/TGID/code/status 未变
```

这是 SELFTEST 强制的单次执行顺序，不是新增的生产全局退出屏障。生产 B 只需
完成自己的 native 协议；测试将等待放在 `native_wait()` 已发布 ACK 后的 pop
边界，不能放在仍欠 B ACK 的 `native_finish()` 中。旧无锁 root 观察器仍使用
另一条 finish 路径，见 [6.9](spin_protocols.md#69-无锁祖先与-waiter-退出)。两个观察器共用 PID/RCU
轮询与完整 frame 比较；超时最多 5 秒后解除测试暂停，但 oracle 必须判失败。
观察器接受 IRQ-on/off 两种初始状态，arm 时保存 CPU、preempt 和 IRQ，等待期间
要求三者不变；禁止抢占仍是前提。IRQ-off 修正前的失败与修正后的完整 mode-8
重跑见 [frame 验证](../../tests/README.md#frame-fast-validation)。
这期间不改 owner/队列、不增加 task ref，实际 source frame lease 一直保留到 pop。
TID 脱离不等于 task 内存已完成 RCU 回收；退出后只使用缓存 PID 和不解引用的指针。

此阶段仍为四条返回后 body witness 和 36023 次复杂状态转换，但必须恰好有
两个 native frame、两次 complete 和 B/A0 两个 ACK，只属于 root 0。
hostcall 为 17 exits / 16 executed / 16 resumed / 1 limit，rejected/failed 为零。
临界区自己的时钟计数为 34：无竞争注册 17 次、竞争执行 17 次，其中最后一次
在原 waiter 上运行。两次 native 观察均须 owner、task/CPU 和未执行的后继状态
一致。此例 waiter 只有一个 root origin pin，native 时 `preempt_count=1`、
IRQ 开启，最终 ACK 后恢复为 0；借用两把锁不等于增加两次 waiter 抢占固定。
这不重建任意原生上下文数值，完整约定见 [ABI](../JIT_REGISTER_ABI.md#11-返回原-waiter)。

`remote_outer_protocol.py --multi --quota` 同时核对生成汇编中的时钟服务目标、
CALL 返回标签、两帧保存的相同 RIP/RSP、原 owner 与后继 JIT 的顺序及前后发布。
`kd_child_exit arm/release` 必须匹配首个 waiter、B owner/CPU、entry/callee/SP，
要求最终 A0 ACK、role 0 返回、`detached=packet=context=valid=1` 及第二 child
开始的顺序；单有 `kd_multi done` 不能证明 TID 已退出。
不能用普通 CALL miss 替代额度出口：前者会将共享 entry 标记为待翻译，可能
使后继不再由 B combiner 执行 JIT。daemon 在负载前已经停止，这不是并发重编译
隔离，也没有引入新指令退出或 flags 保存机制。

统一 runner 收集三个 `Evidence:` 目录。各阶段的 `protocol.log` 和内嵌
`artifacts.tar.gz` 在下一阶段清理工作区前保存；case 最终 `dmesg.log` 只含
混合阶段，不能据此丢弃或重复计算前两个阶段的 JIT 证据。
第三阶段额外保留 `exit-gate.json`、SELFTEST 模块/构建命令和默认构建恢复日志。
只有调用者已退出且模块排空时才恢复默认构建；失败时不强行卸载存活的 frame。

```sh
# Guest only; mode-8 includes all three phases, do not repeat "multi".
make -C tests/unit run TESTS= PY_TESTS='test_exec_capacity.py test_remote_outer_protocol.py test_remote_depth_protocol.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case mode-8 --case remote-late-3
```

这是有界多请求作用域测试，不是任意调度、锁对象生命周期或并发版本证明。
daemon 在共享 entry 的负载前已停止；没有访问时 guard、新原指令出口或 flags
保护。上面的三单元/两 live 是退出观察器改动范围；frame 单元直接提取观察器和
实际 pop，只替代 PID/RCU/time 原语，覆盖已退出、正常脱离、超时、包/上下文变化
和 ACK 前不可暂停等条件，不替代真实 TID 退出。只改 oracle 时运行对应单元即可；
修改共享 workload 时再选择 `registers-8-3`；修改服务策略时再运行
`test_jit_entry_scope.py` 并选择 `mode-2`。选择/证据采集
改动才需要 `test_regression.py`，不新增日常 case 或重复基础矩阵。
