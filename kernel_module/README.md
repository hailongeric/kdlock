# 内核 provider 代码地图

当前 KD spin API 按普通 `raw_spin_lock` 语义：获取/解锁配对抢占，保持 IRQ/BH 状态，
代理慢路径和嵌套队列不再保存 IRQ flags 或整段关 IRQ。最终完成先退休 ticket 元数据，
读完并回收 continuation 后才解除原入口 pin；普通重试和有锁 native 续跑保留 pin。
需要irqsave/irq/bh语义时使用[显式变体](../include/README.md#显式-irqbh-spin-接口)，
它们共用KD原生pending/MCS路径，在原CPU执行，不参与远端代理。

spin 入口检查热度/上下文并按批采样时钟；`nondelegated.inc` 提供完整原生 fast/pending/MCS，虚拟排队继续服务父 ACK。顶层 pending 免 ticket；ticket 使用单个原子控制字，continuation 保留独立退休协议。详见 [当前锁协议](../docs/design/locking.md)。

当前 spin 统一分发已删除；`kd_main.c` 保留停用的 mutex hook 安装和撤销入口。直接入口位于 `spin/direct.inc`，由`kd_spinlock.c`组合编译，
调用者使用 `include/kd_spin_direct.h` 的 clobber-v1 现场约定，并在计时前调用
`kd_spin_prepare` 登记入口。公开 unlock 处理单锁字快速 owner、ticket 和 native ACK；
内部 shadow/frame 解锁保留为 `kd_spin_unlock_protocol`。保留的 mutex hook 路由当前未安装。
KD 锁字、稳定持锁记录、逻辑 frame 和来源 pin 各自承担不同职责。

默认构建要求 `kdclobber2` 的 `KD_SPIN_CLOBBER_V1` 和 `KD_MUTEX_CLOBBER_V1` 接口；缺失时编译直接报错，
不再自动降为旧内核 hook。普通 spin/mutex 使用各自 clobber 身份；同一内核上的旧 ABI 调用者
仍通过兼容 dispatcher 执行，嵌套和原生续跑需要的 FULL 状态也继续保留。
外层mutex调用者使用`kd_mutex_direct.h`的`KD_MUTEX_OUTER_LOCK/UNLOCK`：原生成功在
调用者内完成owner CAS，配对解锁调用原始Linux函数；竞争入口
`kd_mutex_outer_contended_clobber_v1`进入`lock/mutex_calls.inc`的已有准入路径，
在KD引用/gate之前的原生回退返回精确owner；进入队列后返回零。旧void contended接口保留。
记录失败前不重复CAS；准入后且owner/gate/tail观察为空时可在task引用前重试一次，不重复入口计数。
已有`KD_MUTEX_DIRECT_LOCK/UNLOCK`继续用于嵌套控制和兼容入口；
获取局部cookie及FULL/ACK约束见[锁协议](../docs/design/locking.md#mutex-outer-direct)。
普通 mutex 的 MINIMAL/COMPLETE 借用 node 寄存器包，正常完成仅恢复 IP/SP/BP；
首次 FULL 出口为 owner ACK 的独立生命周期取得 frame 自有包。
实现约束见 [ABI 文档](../docs/JIT_REGISTER_ABI.md#mutex-clobber-assessment)。
mutex node 同时删除无消费者的 socket/IRQ 字段和合并通知别名，重新排列为
256 字节、64 字节对齐；next 与 completed/locked 分行，避免缩减字段后
引入相邻 node 共行。生产构建对大小、对齐和通知偏移做静态检查。

`kd_spin_runtime.c`按`kd_exec.c → exe.c → kd_spinlock.c → kd_mutex.c`顺序组合编译，
让两个combiner看到各自普通batch helper的实现；mutex的push/prepare/complete/retire
同样使用GNU always-inline并保留外部定义。源文件仍按下表职责阅读，不再分别链接这四个对象。
mutex私有队列helper使用独立名称；栈切换/恢复继续保留noipa/noinline边界。
结构布局、发布检查、frame/owner/最终ACK、wrapper clobber及节点唤醒顺序保持不变，
FULL/native仍进入原通用分发与退休路径。
普通clobber unlock的native字节路径保持leaf：局部允许尾调用，其他owner转交
`kd_spin_unlock`；最后一个preempt pin需要调度时，使用`static_call_mod(preempt_schedule)`
尾转到内核导出的trampoline，随dynamic preemption配置更新，保留return thunk。
模块不引用内核未导出的static-call key。释放锁字、native计数和preempt decrement/test顺序不变。

| 源码入口 | 保留职责 |
| --- | --- |
| [kd_spin_runtime.c](kd_spin_runtime.c) | spin、mutex与共享执行层的实际编译入口，使普通batch helper可跨源文件内联 |
| [kd_main.c](kd_main.c) | 模块初始化、hook 安装/撤销、目标选择 |
| [kd_lock.c](kd_lock.c) | hook 路由、原生快路径、mutex shadow 查询 |
| [kd_spinlock.c](kd_spinlock.c) | 按协议顺序组合 spin 私有实现；公共调用、恢复和解锁分别在下表的独立组件中 |
| [kd_mutex.c](kd_mutex.c) | mutex 公共入口、栈切换与 owner 返回 |
| [exe.c](exe.c) | wrapper 返回包的高层执行循环 |
| [kd_exec.c](kd_exec.c) | frame 栈、上下文验证和状态事件 |
| [sys.c](sys.c) | `/dev/kd_dev` 的读取、上传、状态与 retire ioctl |
| [kd_source.c](kd_source.c) | 来源状态和 module/frame/writer pins |
| [kd_hotlock.c](kd_hotlock.c) | 每 CPU 分类型精确地址计数、批量频率检查与 spin MCS/获取次数比例准入；入口注册由 `kd_lock.c` 调用执行注册表 |
| [kd_spin_entry.c](kd_spin_entry.c) | 按 ticket 生命周期组合状态/校验、origin、native 借用和诊断组件 |
| [kd_mutex_tasks.c](kd_mutex_tasks.c) | mutex 在途任务/持锁记录，名称变化后的 owner 路由 |

不代理的 KD 请求同样使用 fast/pending/MCS 队列：复用每 CPU 四个节点，在本地
通知字段等待，不分配 request/frame，不切换栈。不可代理节点终止当前 combiner
批次，再由原调用者执行。`spin_delegate=0` 为显式不代理对照，默认仍为 1。

旧统一 spin 分发及 `spin_native_cache` 已删除；显式直接 API 保留现有
快速所有权、ticket、frame 和 ACK 路径。mutex 的目标进程选择仍保留。

`spin_prefetch=0/1/2` 是只读装载参数，分别关闭后继请求预取、保留 combiner
查询地址的旧策略、使用发布前准备的地址提示（默认）。它不关闭其他既有队列
返回处的栈预取。默认producer模式的MINIMAL包只需BP与IP两次hint，IP/SP已共用一行，
覆盖准入读取及COMPLETE写回；借用包始终走FULL策略。新提示只用于缓存预热，不替代寄存器包、准入或 owner/ACK；
节点为 128 字节，next 与通知字分行，continuation 继续独立存活。
四节点per-CPU数组显式按128字节对齐，节点类型大小及通知偏移64/65保持；生产断言与存储fixture约束数组对齐。
匹配ELF每CPU只增加64字节填充，独立性能及地址推断边界见[节点数组报告](../bench/tclock_compare/results/HISTORY.md#20260924-node-array-alignment)。
约束见 [DESIGN](../docs/design/frames.md#911-reuse-before-copy-contract)。

热锁使用每CPU/type256桶、256条精确地址记录，无候选分数或淘汰，锁路径不分配。
spin比例判断复用per-CPU获取/MCS计数：MCS达到1024时比较`(spin_entries >> 10) < 2`，
清零两计数后再采时；删除16字节历史快照、差值、百分比乘法和首次免比较逻辑。
只读参数`spin_entry_ratio_limit`默认2，支持0或不小于2的二次幂；0仅绕过比例。
首批包含先前无竞争获取，可能保持冷，下批自然恢复。busy跳过不清计数，下一次MCS重试。
统计允许IRQ误差；卸载打印未完成批次的剩余计数，不再表示累计获取/MCS总数。
当前仅保留adaptive，移除`hotlock_mode`参数；CPU频率、单锁热度和安全检查仍须满足。
移除两低确认、冷却、独立频率状态、已接受采样流和近期热度保留，小型pinned封装内联。
spin单锁仍独立在512次检查12.5亿TSC窗口，不随CPU的1024次MCS采样改变；
mutex保持第1025次/25亿，CPU窗口保持400亿。
动态表布局、busy guard、owner/ticket/frame与排空协议保持；解锁不查热表。
完整规则及卸载统计见[热度与角色](../docs/JIT_EXECUTION.md#21-热度与角色)。
SELFTEST的`hotlock_lifetime_selftest=1`验证表满不覆盖真实持锁记录及mutex等待迁移；
`hotlock_role_trace=1`输出角色，正常运行关闭。

顶层 fast/pending 自执行共用 fast owner，只有进入 MCS 分支才 reserve ticket；
嵌套调用仍先 reserve。队首正常返回已 claim/reclaim，入口不再重复确认；
ticket 的占用位图和身份元数据仅由原 CPU 的 pinned task 修改，代际/阶段/kind/native借用数
合为一个64位原子控制字。远端 get/put 只对该字做完整代际 CAS，最终等待只读轮询；
不再获取私有 ticket spinlock。API、物理释放和原入口 pin 语义保持；明确的有限资源上限
及退休顺序见 [ticket协议](../docs/design/locking.md#42-acquisition-tickets-and-node-lifetime)，
本轮证据见 [全链路报告](../bench/tclock_compare/results/20260927-flow.md)。

普通请求的诊断引用由入队保存、退出复用，批次也只解析一次诊断 slot；
32个共享诊断槽按128字节对齐、128字节步长排列，只保留身份及禁用状态。
旧共享waiter字段及其初始化已删除，数组从8KiB缩为4KiB；禁用标志原子语义不变。
waiter发布/退出位置保持，以既有动态per-CPU诊断区的两个单调总数记录；每槽80→96字节，
每CPU增加512字节。live有符号聚合是近似观察，允许过期或暂时负值；独立排空后的最终
余额仍精确，非零记为invariant failure。即时原子下溢信号不再保留；owner/ACK、退休、
真正排空及mutex计数不变。完整契约见[诊断身份生命周期](../docs/design/locking.md#spin-diagnostic-identity-lifetime)，
独立30场结果及1/2线程限制见[峰值调查](../bench/tclock_compare/results/20260924-warmed-peak.md#per-cpu-waiter观察保留)。
continuation 按 64 字节对齐，
普通准入元数据位于前两条缓存行。普通批次只在最终准入处检查 readiness，
正常完成合并终态验证和解绑；复杂处理仍使用原协议。

当前对象偏移、简单c1访问范围与预取覆盖集中维护在
[执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md)。紧凑continuation前缀把MINIMAL
所需的五行合为四行，记录步长仍为704字节；这是地址几何，不是PMU缓存缺失次数。
只读配置和JIT镜像可在预热后共享缓存，不能直接当成远端DRAM访问。
`spin_prefetch=0/1/2`可用于同一镜像的受控诊断，结果须独立冻结参数并保留实际JIT和排空检查。

spin 初始化按 possible CPU 一次预分配20 KiB，NUMA-on时请求该CPU节点的内存；低端 12 KiB 放最多 12 条
704 字节 continuation，高端 8 KiB 为物理 waiter 等待栈。节点直接指向记录；
只有所属 CPU 分配/收缩 top，远端执行者 pop 后仅发布退休。父子共享根寄存器包，
不维护 request users/packet_owner。普通完成先 pop 再通知；native 包括无锁 relay
在唤醒前借用根 ticket，清理/pop 后解除，原线程最后解锁等待所有执行者退休。
最终恢复汇编读完现场后才回收根记录。完整对象表与数据流见
[EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。

## 私有实现组件

下表按所属源码入口和原声明顺序列出组件；文件头说明用途和依赖。
`spin/execute.inc` 内的 `execute_cs` 处理复杂委托出口，
`spin/combiner.inc` 的 `run_combiner` 组织批次；
`kd_spin_batch_run` 在同一个 C 帧中处理新、旧及混合 ABI，编译器保护跨 wrapper
活跃值。调用边界见 [kd_jit_batch.h](../include/kd_jit_batch.h)；旧汇编外壳仅留在
[兼容测试夹具](../tests/unit/spin/legacy_batch.S)，不参与生产构建。
`kd_spin_batch_can_continue`在已有批次的后继链接暂空时最多PAUSE/重读8次，
给已完成waiter回队的短窗口；已链接、native边界或达到正文上限时不等待。
NUMA-on且已有暂存的远端节点时，空链接直接交接，不再等待本地waiter回队；
只在该边界读取已有per-CPU队头，不新增共享计数。
不新增时钟或共享状态，保留原有NUMA扫描及队列唤醒顺序。
新 ABI 的普通 root 正常路径只捕获/回写/恢复 RIP/RSP/RBP，中途出口在进入 C
前物化完整逻辑 GPR；旧 ABI 与 FULL 续跑保留完整恢复规则。
`spin/slowpath.inc` 管理队首等待与恢复，`spin/wait.inc` 保持 IRQ 状态，先切到
每 CPU 20 KiB 区域高端的 8 KiB shadow 等待栈，再发布普通 waiter 并轮询。
spin combiner 和虚拟 waiter 的 owner/ACK 服务使用执行者 task 内核栈；
`kd_spin_cpu_state` 保存 CPU 锁账本、节点预留深度和等待栈指针；
嵌套 JIT 的 requester/depth 内嵌于稳定 continuation。旧 wrapper RSP 暂存已删除。
`execution/native.inc` 保留 physical owner，最终 unlock 由该 owner 服务并 ACK，
原线程还须等待所有 native 执行者清理/pop 后解除借用。

| 所属入口 | 组件 | 职责 |
| --- | --- | --- |
| `kd_spinlock.c` | [spin/state.inc](spin/state.inc) | Original-lock identity, per-CPU nodes, shadow state and observer declarations. |
| `kd_spinlock.c` | [spin/shadow.inc](spin/shadow.inc) | Nested lock-vector push/pop, saved combiner state and invariant checks. |
| `kd_spinlock.c` | [spin/diagnostics.inc](spin/diagnostics.inc) | Per-lock diagnostic counters, waiter observations and JIT-disable latch. |
| `kd_spinlock.c` | [spin/queue.inc](spin/queue.inc) | Tail encoding, node publication and optional NUMA successor selection. |
| `kd_spinlock.c` | [spin/nondelegated.inc](spin/nondelegated.inc) | 共用锁字和节点的原生 pending/MCS 获取，不申请 JIT 执行状态。 |
| `kd_spinlock.c` | [spin/request.inc](spin/request.inc) | CPU-local continuation top reservation and contiguous retired-top collapse; remote retirement never changes the owning CPU top. |
| `kd_spinlock.c` | [spin/prefetch.inc](spin/prefetch.inc) | Producer-prepared queue hints and off/consumer/prepared successor-prefetch policies. |
| `kd_spinlock.c` | [spin/combiner.inc](spin/combiner.inc) | 批内查找、outer release、统一 clobber 批次及队列交接。 |
| `kd_spinlock.c` | [spin/execute.inc](spin/execute.inc) | 复杂出口的 frame 绑定、dispatcher 调用、native/remote 处理；在 combiner 的原声明位置包含。 |
| `kd_spinlock.c` | [spin/wait.inc](spin/wait.inc) | 保持IRQ状态的物理shadow栈切换、发布/轮询；队首RSP恢复或completed/native包恢复。 |
| `kd_spinlock.c` | [spin/slowpath.inc](spin/slowpath.inc) | Queue-head waiting, nested combiner restoration and native node admission. |
| `kd_spinlock.c` | [spin/lifecycle.inc](spin/lifecycle.inc) | Per-CPU allocation, partial-init rollback and drained shutdown reporting. |
| `kd_spinlock.c` | [spin/nested.inc](spin/nested.inc) | Virtual nested waiters, remote completion and out-of-order unlock results. |
| `kd_spinlock.c` | [spin/restore.inc](spin/restore.inc) | 寄存器包恢复、continuation退休及waiter返回；保持汇编栈切换与pin释放顺序。 |
| `kd_spinlock.c` | [spin/entry.inc](spin/entry.inc) | pinned获取、热度/上下文准入、原生回退与ticket所有权。 |
| `kd_spinlock.c` | [spin/direct.inc](spin/direct.inc) | 公开lock ABI调用壳、原生byte-5入口及循环外的source准备。 |
| `kd_spinlock.c` | [spin/unlock.inc](spin/unlock.inc) | 按获取来源路由解锁、物理释放和native ACK；不依赖当前热度。 |
| `kd_spin_entry.c` | [spin/ticket_state.inc](spin/ticket_state.inc) | 私有per-CPU池、代际/阶段/借用计数字及共用校验/CAS。 |
| `kd_spin_entry.c` | [spin/ticket_origin.inc](spin/ticket_origin.inc) | 原CPU查找、预留、物理所有权转换及最终释放。 |
| `kd_spin_entry.c` | [spin/ticket_borrow.inc](spin/ticket_borrow.inc) | 远端native借用、唤醒阶段转换与原调用者排空等待。 |
| `kd_spin_entry.c` | [spin/ticket_diagnostics.inc](spin/ticket_diagnostics.inc) | 只读的排空检查和owner诊断；不授予所有权。 |
| `exe.c` | [execution/hostcalls.inc](execution/hostcalls.inc) | Allowlisted native services and bounded mutex CALL stack observations. |
| `exe.c` | [execution/timing.inc](execution/timing.inc) | Optional inclusive boundary timing; disabled runs take no clock samples. |
| `exe.c` | [execution/registry_lifecycle.inc](execution/registry_lifecycle.inc) | 有界代码池与条目查找；execute_cs 传递就绪条目，dispatcher 不再查表，但重新核对发布状态和 source 准入。 |
| `exe.c` | [execution/wrapper_entry.inc](execution/wrapper_entry.inc) | wrapper 范围/镜像/ABI 核对、正文证据及批次准入；不读取 MINIMAL 未捕获的 GPR。 |
| `exe.c` | [execution/control_calls.inc](execution/control_calls.inc) | Known spin/mutex CALL handling, continuation advancement and stack checks. |
| `exe.c` | [execution/registry_publish.inc](execution/registry_publish.inc) | 已发布、同身份/后端且 source OPEN 的重复注册只读返回；新注册、冲突和退休保留串行化。注册不等于 JIT 就绪或正文执行。 |
| `kd_exec.c` | [execution/frame_lifecycle.inc](execution/frame_lifecycle.inc) | frame prepare/bind/push/pop、普通完成及退休，保留有效范围和最后使用者约束。 |
| `kd_exec.c` | [execution/remote.inc](execution/remote.inc) | Remote owner messages and ACKs; spin completion detaches and pops before publishing parent DONE. |
| `kd_exec.c` | [execution/native.inc](execution/native.inc) | NATIVE_READY routing, physical-owner ACKs and final spin root-ticket retirement wait. |
| `kd_exec.c` | [execution/lock_ledger.inc](execution/lock_ledger.inc) | Frame lock-vector mutations and completion predicates; this never acquires L. |
| `kd_mutex.c` | [mutex/queue.inc](mutex/queue.inc) | Per-CPU slot reservation, native mutex acquisition and private tail helpers. |
| `kd_mutex.c` | [mutex/combiner.inc](mutex/combiner.inc) | Delegated mutex bodies, detached outer batches and successor publication. |
| `kd_mutex.c` | [mutex/waiter.inc](mutex/waiter.inc) | Queue waiting and nested native acquisition; preserve owner/ACK semantics. |
| `kd_mutex.c` | [mutex/clobber.inc](mutex/clobber.inc) | 发布前切栈，完成后放弃旧 C 帧，按 COMPLETE/FULL 恢复。 |
| `kd_mutex.c` | [mutex/lifecycle.inc](mutex/lifecycle.inc) | Gate initialization, per-CPU stack allocation, rollback and drained teardown. |
| `kd_lock.c` | [lock/mutex_calls.inc](lock/mutex_calls.inc) | Mutex direct/contended entries, ownership routing and nested CALL cleanup against real owners. |
| `kd_lock.c` | [lock/spin_calls.inc](lock/spin_calls.inc) | Nested spin CALL routing, private tickets, out-of-order release and cleanup. |

## 编译边界

`.inc` 是仅由所属 `.c` 包含的私有 C 实现，不单独生成 `.o`。保留一个编译
单元以维持 static 状态、声明顺序、内联决策、GCC 属性和栈切换汇编标签，
不增加跨对象调用或公开内部符号。Kbuild 自动跟踪 include 依赖；不要把
`.inc` 加入 `kdlock_km-objs`。跨单元接口见 [include/README.md](../include/README.md)。

自测观察仍在 `tests/kernel/`，benchmark 观察仍在 `bench/spin_cacheline/provider/`，
不会混入普通 provider。源码冻结和 provider 副本必须包含 `.inc`。
构建与实际验证只在 recovery guest 执行，入口见 [tests/README.md](../tests/README.md)。

## NUMA与代理上限

默认`KDLOCK_NUMA=1`、`KDLOCK_SPIN_BATCH=1024`；构建时可显式关闭NUMA或选择1–1024上限。
每batch最多代理1024个正文，独立NUMA扫描预算同样初始化为1024，两者分别消耗；
限制工作量，不保证任意调度下的等待时间。延期远端链在最终交接前拼回，
不跨native节点、拒绝回滚或嵌套边界。
直接后继在本节点时直接返回，避免提前读取后继的后继。扫描预算使用原batch填充。
连续远端节点只在首个节点接入延期链，其余复用已有next，只更新CPU-local tail；
不为相同链接反复取得远端cacheline的写权限。
NUMA构建通过`vzalloc_node(..., cpu_to_node(cpu))`为continuation/等待栈请求CPU本地内存，允许分配回退。
批次只缓存注册条目指针，复用该条目RIP而不重复保存key；就绪/代码发布仍逐请求核验。
七字节batch镜像tag以两个重叠的unaligned32加载精确核对，不读取第八字节；
关闭计时时复用已有零timestamp跳过queue timing调用，不新增热路径状态。
普通clobber COMPLETE保留最小IP/SP/BP及witness，去掉只供legacy出口使用的Stack_BATCH初始化；
FULL/native退出和最终现场恢复顺序不变。测量及限制见[后续NUMA比较](../bench/tclock_compare/results/20260926-numa-followup.md)。
