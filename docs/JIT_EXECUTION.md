# 当前 JIT 执行流

当前 KD spin API 按普通 `raw_spin_lock` 语义：获取/解锁配对抢占，保持 IRQ/BH 状态，
代理慢路径和嵌套队列不再保存 IRQ flags 或整段关 IRQ。最终完成先退休 ticket 元数据，
读完并回收 continuation 后才解除原入口 pin；普通重试和有锁 native 续跑保留 pin。
需要irqsave/bh语义的调用者须在外层显式处理。

本页描述显式 KD spin API 及保留的执行引擎。全局 spin 分发已删除，mutex hook
安装仍停用；普通 Linux 锁调用不会因加载模块自动代理。运行步骤见
[PROJECT_GUIDE](PROJECT_GUIDE.md)，验证入口见 [tests](../tests/README.md)。

## 1. 准入范围

目标为 x86_64，要求匹配 kdclobber2 接口。KD、Linux、TCLock 对象使用各自协议。
翻译器保留现有 GS/逻辑 task、静态 per-CPU 范围、上下文敏感操作及 CALL 筛选；
细节见 [admission](design/admission.md)。访问时 guard 和不可变 JIT 版本仍未实现。
热度不等于安全准入，也不代表入口已经发布或正文已经执行。

## 2. 执行流

1. 调用者拥有 `kd_spinlock_t` 对象，并用 `kd_spin_prepare` 登记锁后续点及 ABI。
   daemon 经设备取得登记条目，读取内核正文、翻译、组装、上传并发布 NORMAL。
   直接 benchmark 在单 CPU 预热前完成准备，测量时停止 daemon。
2. `KD_SPIN_DIRECT_LOCK(lock, cookie, continuation)` 先pin，再用C `if`读取已有
   每CPU `rate_hot`，observe/adaptive共用同一默认调用壳。cookie引用
   `kd_spin_direct_cookie`，只表示当前CPU热度，不记录路径或深度。
   冷分支普通C调用完整原生CAS/pending/MCS：增加nondelegated在途计数，CAS失败值
   直接进入慢路径，不重复初始CAS；仍在实际MCS发布处累计CPU热度样本，获取低字节为5。
   热分支用 `KD_SPIN_DIRECT_CALL` 调用pinned clobber入口，命名continuation仅在
   该CALL之后。宽clobber只声明在获取热分支，保存由编译器安排，可能部分位于if前；
   不手写push/pop。provider复用已有pin并检查 `spin_delegate`，宏不读取策略开关。
   当前workload外层使用配对接口，nested/early内层使用普通clobber宏。
   不再提供on/off编译壳或队列深度采样选择；解锁流程见下方独立说明。
3. 保留的 clobber v1 调用保存 pre-CALL RSP、post-CALL RIP 和 caller RBP，编译器保存
   活跃 caller-clobbered 值。`kd_spin_lock_abi` 首先关闭抢占，代理开启时合并记录/
   判断热度并筛选上下文，再尝试 fast/pending；统计和原生回退复用已有 pin。
   关闭代理时公共入口跳过统计，直接走完整原生获取。
4. 热入口快速路径获取 KD 字并保留 pinned fast owner，不准备栈上 request。根 CAS
   失败后进入独立 `kd_spin_lock_contended()`，才创建 24 B request；物理嵌套也
   在该 helper 保留先借 ticket 再 CAS 的顺序。竞争路径使用同一个字的
   pending/tail 排队，普通根仅在 queue 分支占 ticket，再检查翻译就绪。拒绝走
   完整 KD 原生 fast/pending/MCS，已有 ticket 保留，节点不带 continuation/frame；发布后的拒绝或续跑仍须
   完成既有 continuation 生命周期。只有真正节点耗尽才轮询锁字，不回退到 Linux
   锁操作。对象大小、分配位置及与 TCLock 的数据流对照见
   [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)。
5. 每CPU预分配20 KiB：低12 KiB容纳最多12条continuation，高8 KiB为waiter等待栈。
   continuation栈按CPU在低区内选择64字节对齐偏移，保持全部记录及等待栈不重叠；
   锁路径不计算偏移或新增分配，释放从等待栈顶找回原始基址。布局见 [frames](design/frames.md#911-reuse-before-copy-contract)。
   记录按栈顶占用，退休后只收缩连续已退休的栈顶。
   节点直接指向 continuation/frame，节点复用不会销毁现场。
   等待栈、PAUSE 轮询和 caller-clobber ABI 保留。combiner 绑定逻辑 waiter，
   通过 wrapper 和生成代码执行正文，原 waiter/combiner 共用寄存器包。
   简单 spin 根请求的 batch 准备在原有发布、镜像、ABI、packet 及 pristine-root 检查通过后，
   按 legacy/clobber ABI 一次写入最终调用元数据，不再先填 legacy 值再由通用 helper 覆盖。
   clobber 选择对应正文偏移、解锁入口及 COMPLETE 许可；许可只在已有检查证明
   spin_simple、无 parent、depth=0、非 mutex 时成立。legacy 仍不授予最小完成许可；
   mutex/复杂路径继续使用通用 helper，计时、发布及 frame/ACK 退休顺序不变。
6. 嵌套控制 CALL 维护锁记录和独立所有权。提前释放、乱序解锁、远端借用 ACK
   与重新获取不能重复释放 KD 字；ticket 元数据退休与唯一 release store 分开。
7. 正常 COMPLETE 回交 IP/SP/BP；中途 FULL 物化完整逻辑 GPR。已执行的正文
   不重跑，只有已支持的 CALL/PENDING 边界可受检续跑。普通完成必须先 pop 子 frame 再发布完成。
   NATIVE_READY 与最终退休分开：所有 native 执行者（含无锁 relay）先借用根
   ticket，清理/pop 后解除借用；最终解锁等待借用清空，才回收现场及解除抢占。
   无剩余锁的续跑在恢复前等退休；恢复汇编读完全部现场后才回收根记录。

具体布局与指令约定见 [ABI](JIT_REGISTER_ABI.md)，队列/所有权见
[locking](design/locking.md)，frame 和受检续跑见 [frames](design/frames.md)。
mutex保留原mutex、调度gate、task记录与native owner/ACK协议，
不使用spin的锁字或continuation排队协议。

### 2.1 热度与角色

spin/mutex 每 CPU 独立 256 桶、256 条预分配记录，哈希冲突用完整地址和槽索引
链表区分。没有候选/分数/淘汰，命中只给该锁 count 加一；满表不覆盖已有记录。
初始化建立 CPU 时间；spin CPU 每累计 8 次合格 MCS 发布读取一次时钟，
整批耗时严格小于 400 万 TSC ticks 才判热。mutex CPU 保持每 1024 次入口调用检查，
整批耗时严格小于 400 亿 TSC ticks 才判热；两种 CPU 窗口独立。
批间沿用缓存热值，首批从初始化计时。入口仍按缓存 CPU 热值决定是否查锁表。
队尾发布采样覆盖冷/热 CPU 的原生、代理和虚拟嵌套节点；fast/pending 不计数。
每次实际入队只计数一次，每 8 次发布才采时，不遍历后继链、不在队头补采样。
已删除队列门槛参数与策略开关。
2/3线程只要频繁实际入队，也能更新 CPU 热值；不再按线程数保证冷态。
spin/mutex 单锁 count 大于 32（第 33 次）才检查 25 亿 TSC 窗口并更新 hot/时间、清零计数。
单锁仍统计入口调用。mutex 同次到期共享采时，spin CPU/锁分别采时。
CPU 持续热保留单锁批次，冷却/重新变热清零计数/热值但保留映射。
MCS 更新只影响后续入口；没有入队时 CPU 缓存热值保留，不新增逐次时间检查。
adaptive要求CPU/锁缓存热值同时成立，未收录且表满的锁走原生；observe在CPU热后
固定准入。CPU曾变热后即使转为单线程，也要等后续MCS采样才能降温；没有后续MCS
时可能一直缓存hot，2/3线程高频MCS也可能维持hot。当前没有每次入口读时钟或独立过期标志。
query 不计数/采时/插入；有效地址及表生命周期由调用者保证，关闭代理时不记录。
虚拟嵌套先按热值分流；热路径占独立 ticket 后 CAS/排队，冷路径走原生 bridge。
已发布的虚拟等待继续服务父frame的远端ACK。热度变化只影响后续获取，不能取消已发布请求。
统计复用调用者已有的抢占保护；仅尚未关闭抢占的独立调用临时 pin 并在返回前
解除。热表已删除本地 busy 及其编译器屏障，只在 task context 访问；中断上下文
跳过统计、query 返回冷，observe 的 record 仍固定允许。允许丢样，但不允许重入
破坏哈希索引链。spin 复用已有 pin，mutex 不跨睡眠持有统计 pin。

OWNER 保存在稳定 fast owner/ticket 状态中，WAITER/COMBINER/DONE 位于 frame。
角色和所有权不依赖热表是否保留该地址或锁的热值。SELFTEST 可输出按锁地址关联的角色，
普通构建不逐请求打印。最终统计仅在 provider 排空后输出，不能倒推全程状态。

### 2.2 统一解锁

`KD_SPIN_DIRECT_UNLOCK` 无条件通过broad-clobber调用 `kd_spin_unlock_clobber_v1`，
冷/热获取均传lock及SP/IP/BP，由编译器处理活跃寄存器；调用端和JIT正文没有冷热解锁分支。
provider发现低字节5时只release该字节、减少nondelegated计数并解除pin，保留pending/tail；
其他状态进入原解锁核心，保留owner、ticket、native借用及最终退休检查。
解锁不读cookie或CPU热值。旧冷专用导出只用于兼容，当前配对宏不再调用它。

## 3. 验证选择与判定

[tests](../tests/README.md)是当前测试选择的唯一入口。旧全局 hook 场景及对应的
运行命令已删除，其历史通过不构成当前接受标准。保留的日志 oracle 只验证证据
字段关系，生产 C fixture 只覆盖替代原语下的状态转移，均不能替代真实 JIT。

当前直接运行器验证发布条目、冻结镜像、真实正文、业务数据、IRQ/preempt、队列
与退休。`nested` 检查 A→B→释放 B→释放 A；`early` 检查持 B 提前释放 A。
这两项本地双锁证据不能推广为所有远端 native/JIT 组合已验证。

SELFTEST 的热表满容量后真实 owner 保留、mutex CPU 迁移和 entry ACK 是独立 JIT=0 证据。
模块加载/卸载检查也不执行 JIT。性能有效、实际 JIT、原生/拒绝及失败记录分开报告，
没有正文的竞争 observe 场次不得算通过。环境、快照和卸载约束见
[AGENTS](AGENTS.md)。
