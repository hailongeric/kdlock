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
   直接 benchmark 在全部测量 worker 预热前完成准备，测量时停止 daemon。
2. `KD_SPIN_DIRECT_LOCK(lock, cookie, continuation)` 先pin，再用C `if`直接读取
   静态per-CPU unsigned-int热值，不再经过指针访问动态锁表；热值只有一份。
   当前只保留自适应准入。cookie引用
   `kd_spin_direct_cookie`，只表示当前CPU热度，不记录路径或深度。
   冷分支内联首次CAS和既有计数，CAS失败值交给普通C helper完成pending/MCS，
   不重复初始CAS；nondelegated在途计数覆盖获取和持锁，实际MCS发布继续累计CPU热度样本，获取低字节为5。
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
   batch镜像的七字节tag使用两个重叠unaligned32加载逐请求核对，不缓存发布状态或多读第八字节。
   计时关闭时复用已有零timestamp跳过queue timing helper，开启时仍保留原端点顺序。
   完成先验证出口，再以`wrapper_start`旁路关闭计时的全局检查；开启时按wrapper、dispatch顺序记录。
   拒绝出口留给通用分发，完成分类及JIT正文witness不变。
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

当前自适应竞争判断使用同一512次MCS采样边界上的计数差值，
接受近似统计，不为IRQ交错维护精确批次。没有连续低窗口确认、冷却期或独立频率热值；
原生队头另作下述捕获队尾前缀检查，所有权与准入统计分离。

spin/mutex每CPU独立256桶、256条预分配记录，以完整地址和槽索引链表区分冲突，
不打分或淘汰；满表时未知锁保持原生。spin热值移到静态per-CPU标量，mutex热值
保留在动态per-CPU对象；两张表不再各自含rate_hot。每表6680字节，每CPU分配仍为13376字节。
获取/MCS计数之外，spin以16字节保存上次获取及MCS两个快照，以4字节保存唯一热值；
不再维护独立的已接受采样计数。这里的“精确”指锁身份，不表示热度统计无误差。

物理获取尝试在其执行CPU上计数，包含公共入口、配对冷原生入口、嵌套原生bridge、
虚拟嵌套及outer重新获取；同一次获取的CAS重试或原生回退不另计。
配对冷原生入口在首次CAS后、竞争路径前增加计数。fast/pending成功计入分母但不发布MCS。
启用`spin_delegate`时，每次队尾发布复用已有per-CPU MCS计数；该原始计数不按队列深度筛选或在队头补计。
节点耗尽后的锁字轮询也不发布MCS。计数封装在头文件内联；共享热表访问强制内联到各入口，
已pin的spin入口直接省去运行时抢占检查，通用观察和mutex入口保留原有pin处理。

MCS路径先增加计数，再读取它并检查低9位；通常每512次发布调用一次受busy guard保护的采样器。
IRQ可使边界延后或重复，不用XADD返回值或额外状态修正。采样器读取两个原始总数的无符号差值，
MCS差值为0时直接沿用缓存热值；否则先判断
`mcs_delta * 100 >= entry_delta * spin_contention_pct`，再读取一次TSC检查CPU频率。
装载参数`spin_contention_pct`只读，默认100、范围0–100；0仅绕过比例比较。
首次MCS快照为0时只建立比例起点，允许CPU频率门槛先工作，不把先前无竞争预热计入首个比例判断。
这是近似的跨锁CPU统计；计数回绕到零也可能重新建立起点，不承诺IRQ下精确窗口。

CPU窗口严格小于400亿（`40000000000`）TSC ticks，从上次采样时间起算，首批从初始化计时。
每次有效采样更新两个快照、时间和合并后的CPU热值；低比例直接关闭，高比例与频率均达标即可重新开放。
busy重入跳过本次比较且不推进快照，后续差值自然包含被跳过的事件，没有独立补记流。
频率与比例使用同一采样节奏；普通获取只增加计数，不额外读时钟。
mutex不使用比例，继续每1024次入口记录检查同一CPU时间窗口。

`mcs_entry_ratio512_head6`另在原生MCS队头接棒后、轮询或获取物理锁字前进行近似准入否决。
先检查已有MCS计数的低9位；仅在512边界、delegation启用且CPU已热时继续。
一次读取完整锁字，要求locked字节及tail均非零；随后最多以acquire读取六条已发布的后继链接，
只统计这次捕获的tail以内（含tail）的队列前缀，到达捕获tail后不再读取其next。
没有六个已链接后继、缺少tail、locked为零（包括只有pending）或遇到尚未发布的链接均保守关闭CPU热值，
不等待补链，也不修改计数、快照、时间、单锁记录或已发布请求。后续MCS采样仍按原规则重试准入。

当前原生队头阻止后继前进和复用，前任在交接前完成NUMA拼接；捕获tail界定的前缀在检查期间保持存活。
原持有者在读取锁字后释放并重新排队，只能出现在捕获tail之后，不能被重复计为持有者与后继，
因此不要求遍历结束时锁字仍为held。原生/IRQ标记节点也计入前缀，不读取其execution/frame。
这是当前队列请求的观察，不是通用线程数判断；嵌套、IRQ及发布间隙都可能影响观察，
较多worker也不保证满足准入。委托队头不执行此否决，当前原生获取、交接与所有权检查保持不变。

CPU热才查锁表。spin单锁计数达到512（`>=512`）时检查严格小于12.5亿
（`1250000000`）TSC ticks的窗口；mutex保持第1025次及严格小于25亿（`2500000000`）。
到期更新hot/时间并清零计数。mutex可复用同次CPU采样时间，spin的CPU与单锁分别采时。
每次CPU采样仅在采样前后均为热时保留单锁批次；降温、仍冷或重新变热均清零单锁计数/热值，保留地址映射。
原生队头否决本身只清CPU热值；下次采样重新开放时按同一规则重置单锁批次。
没有比例冷却期、连续低窗口确认或近期热度保留。hot是缓存值，不是逐入口过期保证；
如果转为fast/pending-only且没有后续MCS，CPU热值可能一直缓存。

当前仅保留adaptive，要求CPU和单锁缓存热值同时成立；`hotlock_mode`装载参数及CLI已移除。
`spin_contention_pct=0`不绕过原生队头前缀检查、CPU频率、单锁热度或上下文/JIT安全检查，也不保证产生实际JIT。
冷CPU走原生。query不计数、采时或插入。
`spin_delegate=0`仍累计获取次数，但关闭热表记录及MCS采样。
统计复用已有preempt pin；尚未pin的独立调用仅在本次访问期间pin，mutex不跨睡眠持有它。
本地busy guard仍保护插入和热表重置，使用普通CPU本地读写及编译器屏障。
访问已pin且不睡眠，IRQ会在被中断者恢复前完成，不需要原子的读改写；重入记录可丢弃并返回冷。
有效地址和表生命周期由调用者保证；近似统计只影响未来准入，不承担所有权或排空计数。

虚拟嵌套按热值分流：热路径取得独立ticket后CAS/排队，冷路径走原生bridge。
已发布请求继续服务父frame的远端ACK，不能因热度变化取消。
OWNER保存在稳定fast owner/ticket中，WAITER/COMBINER/DONE位于frame；角色不依赖热表。
SELFTEST可按锁地址输出角色，普通构建不逐请求打印。

`hotlock_stats=1`只在provider排空卸载时输出近似累计`entries`、`mcs`及最终CPU热值、门槛和窗口；
已移除`sampled_mcs`、`cooldowns`。计数包含预热和后续所有阶段，不是benchmark测量边界计数，
也不能从最终CPU/单锁热值及未满批次count倒推全程状态。

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
没有正文的JIT正例不得算通过；功能检查可用比例门槛0，但仍须取得实际正文及上下文/排空证据。
移除observe后的功能结果以新的冻结运行记录为准，历史通过不替代重跑。环境、快照和卸载约束见
[AGENTS](AGENTS.md)。
