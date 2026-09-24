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
   关闭代理时公共入口仍累计物理获取次数，但跳过热表及 MCS 采样，直接走完整原生获取。
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
比例状态使用独立的 48 字节静态 per-CPU 对象；spin/mutex 动态精确锁表保持原有字段偏移、
大小和步长，普通锁查询不访问比例状态。
初始化建立 CPU 时间。启用 `spin_delegate` 时，spin 每次实际 MCS 发布以内联 GS XADD
增加原始发布计数，获取分母使用 GS INC；已拒绝的字节相位方案不在当前实现中。
返回计数到达 128 的整数倍时才调用受 busy guard 保护的采样器；成功进入的完整批次
读取一次时钟，并为比例分子增加 128。mutex 每累计 1024 次入口记录读取一次时钟。
整批耗时均须严格小于 400 亿（`40000000000`）TSC ticks；批间沿用缓存 CPU 热值，
首批从初始化计时。本轮起点的每 32 次 MCS 采时属于旧配置。
队尾发布覆盖冷/热 CPU 的原生、代理和虚拟嵌套节点，每次实际入队只计一次；
不按队列深度筛选，不遍历后继链、不在队头补采样。fast/pending 成功和节点耗尽
后的锁字轮询不发布 MCS。

adaptive 的 spin CPU 准入还要求窗口内纳入策略的 MCS 发布数占物理获取尝试数的比例不低于
只读装载参数 `spin_contention_pct`（默认 100，范围 0–100；0 只绕过比例及其冷却门槛）。
分母在执行该获取的物理 CPU 上累计，包含公共入口、配对冷原生入口、嵌套原生
bridge、虚拟嵌套获取及 outer 重新获取；同一次获取的内部 CAS 重试或原生回退不重复计数。
配对冷原生入口在首次 CAS 后、进入竞争路径前增加计数，不改变同一次获取的计数边界。
fast/pending 成功也进入分母。比例窗口独立累计 4 个成功采样的 128 次发布批次，
共 512 次策略发布；无重入丢批时与实际发布次数相同。每个完整比例窗口用无符号
获取计数差值判断比例，普通入口
只增加 per-CPU 计数，不额外读取时钟。这个比例反映实际入队机会，不是失败 CAS 比例
或委托批长度，也不按线程数直接选择策略。
这是跨锁身份的 CPU 级统计；同一 CPU 上其他锁的 fast 获取、无竞争嵌套锁或 outer
重新获取都可能拉低比例，从而暂时关闭该 CPU 上竞争锁的代理。它不是逐锁收益模型。

初始比例状态先允许 CPU 频率门槛工作：首个成功采样的 128 次 MCS 批次达标后即可积累单锁热度，
不额外等待首个 512 次策略发布的比例窗口。CPU 热值仍从冷态开始，没有 MCS 或首个频率批次
未达标时不会因此开放准入。包括初始乐观状态在内，比例准入均须连续两个完整窗口不达标才关闭；孤立的低比例窗口保留
准入及单锁热度，任意达标窗口清零连续低窗口计数。原生排队本身可能提高比例，
为避免关闭后立即重新开放，确认关闭后进入冷却：后续 8 个完整比例窗口
（4096 次纳入策略的 MCS 发布）保持原生，同时继续采样。
低比例窗口不会重启冷却；第 8 个后续窗口结束时若比例达标，才允许后续入口重新尝试
CPU/单锁热度准入，否则保持原生并等待之后的高比例窗口，不必先累积两个高窗口。
冷态仍依靠原生 MCS 推进采样；
重入丢批时实际发布次数可超过 4096；它不是时间上限，也不保证冷却结束时已有单锁完成预热。
mutex 不使用该比例。`spin_delegate=0` 仍累计获取次数，但关闭热表记录及 MCS 采样。

CPU 热才查锁表。当前工作候选的 spin 单锁 count 大于 512（第 513 次入口记录）时，
检查严格小于 12.5 亿（`1250000000`）TSC ticks 的窗口；mutex 保持大于 1024
（第 1025 次记录）及严格小于 25 亿（`2500000000`）的窗口。到期更新 hot/时间并清零计数。
spin 同时减半批次数和时间界限，以缩短预热并大致保持频率门槛；该候选性能验收仍待完成。
mutex 同次到期共享采时，spin CPU/锁分别采时。
CPU 频率持续热时保留单锁批次；比例单独关闭只暂停 count/hot/begin，查询仍受关闭的准入门槛限制。
比例重新开放时复用本次 CPU 采样时间，保留未满 spin 单锁窗口的近期状态，过期或时间倒退的状态清零重计；
真实 CPU 频率降温/重新变热仍清零所有单锁计数/热值并保留映射。
重开后的 hot 是缓存值，可随后超过单锁时间窗口，直到当前单锁批次累计第 513 次记录再次检查；查询不计时或计数，
这不是逐入口过期保证。频率反复冷热切换仍可能使单锁无法完成预热，即使生命周期总比例高于门槛。
MCS 更新只影响后续入口；时间降温等下一个成功采样的 128 次 MCS 批次，
比例降温包括初始状态在内均须等两个连续低窗口。
转为 fast/pending-only 后若没有后续 MCS，先前 hot 可能一直缓存；当前没有逐次时间
检查或独立过期标志。

adaptive 要求 CPU/锁缓存热值同时成立，未收录且表满的锁走原生。
observe 绕过比例及冷却门槛，record 固定准入；默认配对调用壳仍先检查 CPU 频率门槛，
冷 CPU 走原生，不能把 observe 理解为所有配对入口立即代理。
query 不计数/采时/插入；有效地址及表生命周期由调用者保证。
虚拟嵌套先按热值分流；热路径占独立 ticket 后 CAS/排队，冷路径走原生 bridge。
已发布的虚拟等待继续服务父frame的远端ACK。热度变化只影响后续获取，不能取消已发布请求。
统计复用调用者已有的抢占保护；仅尚未关闭抢占的独立调用临时 pin 并在返回前
解除。每 CPU/type 的 busy guard 拒绝重入热表，释放前保留编译器屏障；中断调用
也复用该保护，不一律丢弃。重入可丢失热表记录或整个 128 次 MCS 策略批次，不重试或补记；
原始发布计数仍保留该批次，获取分母也不扣除，因此比例判断更保守。observe 的 record 仍固定允许。
获取及原始发布计数使用 per-CPU 指令，避免被中断的增量覆盖；批次边界由增量指令返回值决定，
不受随后 IRQ 发布改变计数的影响。spin 复用已有 pin，mutex
不跨睡眠持有统计 pin。

OWNER 保存在稳定 fast owner/ticket 状态中，WAITER/COMBINER/DONE 位于 frame。
角色和所有权不依赖热表是否保留该地址或锁的热值。SELFTEST 可输出按锁地址关联的角色，
普通构建不逐请求打印。`hotlock_stats=1` 仅在 provider 排空卸载时输出最终统计：
ratio 行的 entries 是物理获取尝试累计；mcs 是原始发布累计，包含重入丢批和未满批次尾部；
sampled_mcs 只累计成功进入采样器的完整 128 次批次。这些都是初始化以来的累计，包含预热和所有随后阶段；
不是 benchmark 测量边界计数，也不是最后一次准入批次比例。window 为比例窗口大小，
cooldowns 为生命周期内两个连续低窗口确认关闭准入、启动冷却的累计次数；observe 也计算该值，
但不实际应用比例/冷却门槛。cpu_hot/lock_hot 为最终缓存值，
单锁 count 为未完成批次计数；这些值不能倒推全程状态。

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
