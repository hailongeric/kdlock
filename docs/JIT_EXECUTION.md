# JIT 范围、执行流与测试

适用范围：x86-64 内核临界区；mutex 代理必须显式启用 `mutex_jit=1`。
2026-09-08 用户确认：只审查本次实际可能执行的 JIT 范围，普通 CALL miss
交回原 waiter 后，从保存的退出状态原生完成剩余临界区，不再返回本次 JIT。
这取代此前“普通 CALL 后的 native 后缀也必须整段准入”的要求。

## 1. 准入范围

翻译器先解码，再由 `context_policy.jit_phase_blocks()` 选择 JIT 可达块，
随后做临界区锁深度边界检查和上下文检查。同一份块集合用于生成机器码及
入口分发表，不能只缩小检查范围却继续生成未检查的后缀。

| 边界 | 本次 JIT 后续范围 |
| --- | --- |
| 普通直接 CALL，callee 不在当前解码块中 | 保留 CALL 本身和退出桩，删除该 CALL 的返回边 |
| 同后端 lock/unlock 控制调用 | 保留可恢复的后继，仍检查嵌套临界区 |
| allowlist hostcall | callee 原生执行，返回后继续 JIT；后继仍需检查 |
| 已解码的普通 callee | 检查 callee 和返回后继，保留 CALL 入参及 RET 效果分析 |
| 间接 CALL | 保守保留后继；不能假设一定 miss，已学习目标也需检查 |
| 条件分支或其他 JIT 路径到达同一后缀 | 后缀仍在范围内，不能因另一条 CALL 边退出而删除 |

初始入口和已学习目标作为范围根；每次重新编译重新计算范围。可达的缺失
分支文本仍走有界补读，不能把未解码的跳转目的地当作安全空块。
普通 CALL 自身的目标和压入返回地址的内存写入也必须通过检查。

文本窗口已经覆盖目标地址，不代表该窗口的 CFG 已解码目标。新热路径可能
指向已有冷窗口中尚未解码的块；翻译器会补充该窗口的解码入口并重新检查。
这不增加独立的准入根，不让冷分支借用新的入口寄存器假设。补读和补充解码
入口共用 32 轮扩展上限；真正不可解码或预算耗尽仍拒绝，不跳过缺失块。

范围内发现 GS/current 访存、已识别的 per-CPU/调度/IRQ/RCU 符号或其他既有
拒绝条件时，整个候选拒绝并删除本次汇编/二进制产物，daemon 发布 native-only。
只存在于已排除后缀的 GS/current 操作不再导致该 JIT 前缀被拒绝，因为它们
由原 waiter 原生执行，不是交给 combiner 的 hostcall。
这不是任意指针、并发内存、所有指令或所有内核上下文的安全证明。

## 2. 执行流

```text
waiter 获取/请求 L，记录原临界区入口
  |
  +-- 无可用 JIT / 准入拒绝 --> waiter 原生执行
  |
  +-- combiner 持有原生 L --> 校验入口/逻辑子请求的执行范围
                              |
                         wrapper 装载 waiter 的 pt_regs
                              |
                         必要时检查入口地址区间
                              +-- 条件不满足 --> 尚未开始，走原生路径
                              |
                              v
                         执行翻译后的指令
                              |
                +-------------+------------------+
                |             |                  |
           lock/unlock     hostcall          普通 CALL miss
                |             |                  |
           锁协议处理      allowlist 服务     保存当前 GPR/RIP/RSP
                |             |              保留虚拟 CALL 返回地址
                +-------> 继续 JIT                |
                                                 v
                                         原 waiter 原生进入 callee
                                                 |
                                         原生返回并执行剩余临界区
                                                 |
                                         unlock 请求 / owner ACK
                                                 |
                                            本次代理结束
```

图中的控制 CALL 继续 JIT 是正常路径。局部 mutex 控制另有
[有界栈检查](#53-mutex-控制-call-的栈检查)：窗口不足时在 CALL 前交回 waiter，
窗口变化时在已完成 CALL 的后继交回 waiter；两者均不返回本次 JIT。

普通 CALL miss 的 `regs.ip` 指向原 callee，`regs.sp` 保留刚压入的源返回地址。
waiter 不是从临界区入口重跑，之前的写入和已完成的 B 不重放，也不做事务回滚。
native 续跑期间，combiner 保留已经获得的物理锁并按既有协议处理 unlock 通知；
等待这次 native 续跑完成，不恢复同批其他代理请求的执行。这是该 combiner
的暂停，不是全局暂停；其他 CPU 上独立锁队列的 combiner 仍可处理自己的请求。
mutex 的原生 owner 不交接给 waiter。不能让其他调用者趁 native 后缀未完成
进入这些仍持有的原锁。嵌套/远端路径的具体状态约束见
[DESIGN](DESIGN.md#96-bcd-comparison-and-continuation-scope)。

例如 `A: 写入 -> CALL F -> 后缀 -> unlock(A)`，F 尚未翻译时只执行 JIT 前缀；
F 和后缀都在 waiter 上执行。daemon 可以学习 F 并为未来调用重编译，但不会
把这次已转入 native 的执行重新拉回 JIT。若新版本可能执行 F 内部或返回后缀，
必须重新检查这些代码；之前前缀通过不等于新范围也通过。

两元素输入 ABI 不变：`args[0]=waiter GS base`、`args[1]=logical waiter task`。
这两个值不切换真实调度/IRQ/RCU 上下文。寄存器及输出含义见
[JIT_REGISTER_ABI.md](JIT_REGISTER_ABI.md)。非 CALL 故障续跑、flags 修复和
不可变代码版本仍是已记录的限制，本次不扩展。

## 3. 环境与操作

第一次手动操作先读 [代码地图与逐步运行](PROJECT_GUIDE.md#3-一步一步运行)：
其中有 VM/guest 检查、完整文件索引、单用例入口和拆开观察 mode 3 的流程。
本节及后续章节维护复杂用例的协议、参数和判定，不要求把所有命令顺序执行。

只在可恢复的 guest 中构建和运行，不能在宿主机加载模块。当前 guest SSH
端口为 2222，已有 Linux 6.1.159 hook/exports；本次不修改 guest 内核。
先确认恢复快照和空闲状态，完整流程见 [AGENTS.md](AGENTS.md)。
normal 模式共享源码无需复制；recovery 模式虽路径相同但使用 ext4，只同步
哈希不同的文件，不移动或整目录复制仓库。

以下首次环境验收命令在 guest 的 `/root/host_fs/kdlock` 执行。
开发后的日常增量使用[第 7 节](#7-分层与增量回归)，不重复执行本节全部命令：

```sh
cd /root/host_fs/kdlock
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
make -C tests/unit run
python3 tests/audit_context_spills.py
```

首次验收或需要全主模式确认时，在恢复快照确认后执行以下命令。
脚本负责编译、加载、检查、停止 daemon 和卸载：

```sh
export KDLOCK_RECOVERY_CONFIRMED=1
bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5
```

该入口无参数时只列出测试范围，不再默认运行全主模式。显式参数先全部校验，
相同 mode 按首次出现顺序只运行一次；遇到失败立即停止。检查每种模式时可
分别传入一个 mode，不能因为前面通过就假定后面执行过。
mode 3/4/5 脚本显式加载 `mutex_jit=1` 并检查实参。
daemon 的 `--mode flat/per-tgid` (`1/2` / `v1/v2` 为兼容别名) 只选择工作目录布局，不是 benchmark 的 mode。
daemon 必须在 kdlock 加载后启动，并在一次设备会话内完成读取、翻译和发布。
真实文本读取要求有效的设备引用；翻译子进程继承该引用，父进程退出后也可能
继续持有。真实读之前还会 pin 源码所属 LIVE 模块；停止并等待所有翻译者和
执行者退出后，须成功 `retire` 再卸载，不能将 `in use` 当作强卸载理由。
执行流及手工 CLI 的边界只维护在 [daemon 文档](../daemon/README.md#device-session)。
mode 1/4 的入口条件及 mode 8 的跨窗口解码已通过实际 JIT 检查；这不代表
所有远端或资源耗尽场景也通过，完整结果及未通过项见验证记录。

mode 3 的 `test_07` 在生成物出现后，还通过现有 `wait_ready()` 读取
`/dev/kd_dev`，等待对应 RIP/TGID 的 mutex 条目为 NORMAL，再运行竞争负载。
`jit.bin` 存在可能早于上传，最终 chunk 日志也早于 payload 拷贝，不能只查
一次日志就启动测试或判失败。发布状态写入 daemon 日志同名前缀的
`.published.json`；此准备检查不代替负载后的 body witness/计数验收，也不提供
不可变版本或并发重编译保护。

mode 8 需要串行准备六个翻译入口，`test_04` / `test_10` 为此单独等待最多
90 秒并打印实际耗时。只延长产物初始化等待，不改变负载执行超时、必需产物、
返回后 body witness、寄存器或互斥/副作用检查。

普通 CALL 的真实寄存器/退出点续跑，以及上下文拒绝测试：

```sh
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 0 1
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 3 1
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 1 2
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 4 2
bash tests/test_04_spinlock.sh 8
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 8 2
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 8 3
bash tests/test_12_context_native_only.sh 10
bash tests/test_12_context_native_only.sh 11
KD_CONTEXT_LOCK_API=percpu-spill bash tests/test_12_context_native_only.sh 3
```

普通 CALL 测试检查当前退出状态、waiter 身份、返回栈及副作用恰好一次；不能用
完全原生对照代替。上下文拒绝测试则必须没有 JIT 执行，随后验证原生结果。

学习普通 helper 后的深层 mutex JIT/容量退出，日常使用已升级的两源码模块用例：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case native-mutex-depth
```

该脚本先执行 JIT 前缀并产生真实 helper CALL miss，排空调用者后让 daemon
学习第二个模块中的 helper，再检查新范围的 JIT、锁容量退出和源码 pin 退休。
必须执行 helper 中翻译后的加锁指令，验证真实容量退出、保留锁和 owner ACK；
只有第一段 body witness 不能通过整项验收。完整执行流见 5.1。
直接调用 `test_10_native_resume.sh 4 5` 仍是默认单模块诊断，不作为该复杂用例的
前置或附加步骤；只有单模块构建/路径本身受影响或需要定位时才另行选择。
学习重编译期间先排空旧调用者，并非已实现版本隔离。

### 3.1 纯原生寄存器对照

历史 `control-0/3` 的必要逻辑已并入 `test_10`，不再依赖 guest `/tmp` 中的
外部脚本。它们只在首次校验探针、修改原生对照或显式验收时选择，不属于日常
`registers`、`core`、`baseline` 或 `extended` 的前置步骤：

```sh
# Guest only, after confirming the recovery snapshot.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite native-controls
# Equivalent explicit diagnosis of the mutex reference only:
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_CONTROL=1 KD_NATIVE_REGISTERS=1 \
  bash tests/test_10_native_resume.sh 3 1
```

执行流：确认空闲 -> 共用构建/加载 -> provider 设为 `target_process=kd_unused`
并读回，保持 `mutex_jit=1` -> 启用同一寄存器汇编探针 -> 八名非目标 worker
各完成一次原生临界区 -> 只读确认 registry 为空、source 为 OPEN 且 modules/
frames/writers 均为 0 -> 正常 retire/卸载 -> 校验八条记录、16 个 GPR、CALL
返回栈和保护状态。该分支不启动 daemon、不晋升或翻译；不检查 flags。

`KD_NATIVE_CONTROL=1` 仅接受 registers=1、mode 0/3、stage 1，并继承寄存器
用例的参数互斥检查。未设置时原 JIT/续跑路径不变。`native-state.json`、
`registers.json`、environment、workload 与 dmesg 进入统一证据目录；任何 JIT
entry/body/install、native frame、owner ACK 或非零注册数都会使对照失败。
归档器可能保留先前 daemon 工作区的文件，它们不是本次生成或执行证据。
不能用纯原生对照通过替代 JIT 寄存器续跑正例；历史命令清单也不改写为新命令。

## 4. 如何判读

公共脚本强制 `KD_JIT_BODY_WITNESS=1`。实际 JIT 验收同时需要有效 `jit.bin`、
匹配 entry/lock 且 wrapper 返回后的 `JIT body witness: ... body=1`，以及负载
状态/计数检查。只看到翻译命令、安装日志或调用前 `execute_cs` IP 不足以通过。
mode 2/5 还要确认 hostcall 执行和恢复成对出现。

`body=1` 证明生成块确实进入且 wrapper 已返回，不证明每条指令/每条路径均执行。
JIT 前缀加 native 后缀不能写成“整个临界区全由 JIT 完成”。`body=0` 也不能
授权入口重放。观测插桩不是性能基线，手工运行 daemon 默认不开启。

失败时先查看 `CONTEXT_NATIVE_ONLY` / `CONTEXT_ADDRESS_WIDENED` 的源 RIP、
指令和原因，再对照 daemon 工作目录里的 `asm/jit.S`、`jit.bin`、miss 表及
脚本输出的 `Evidence:` 目录。分析精度耗尽是保守拒绝，不是发生真实越界的证据；
拒绝后的原生完成不能冒充 JIT 正例通过。

同一次翻译可能先报告无条件分析的 `CONTEXT_ADDRESS_WIDENED`，再通过带条件
分析并报告 `ENTRY_GUARDED_ADMISSION`。前一条不能单独当作最终拒绝。冷分支
补读为 `ENTRY_GUARD_WAIT_TEXT` / `TEXT_RANGE_EXTEND`，补读完成仍须重新检查。
`CFG_ROOT_EXTEND` 则表示为已缓存文本补充可达解码入口，不是额外读取文本或
接受未检查的块。
运行时 `ENTRY_GUARD_REFUSED` 表示当前入口值不满足条件，本次未执行 body；
`ENTRY_SCOPE_MISMATCH` 或 `INVALID_ENTRY_REFUSAL` 则需要核查 frame、CALL
阶段、RIP/RSP 和父请求，不能忽略错误并重试入口。

各批次的时间、源码身份和结果集中记录在 [VALIDATION](VALIDATION.md)；
[9 月 9 日矩阵清单](VALIDATION.md#recorded-matrix-manifest) 是历史执行记录，
不是当前回归的待执行清单。当前选择以第 7 节和 `tests/regression.py` 为准。
完整矩阵必须使用同一源码快照，不借用旧的短回归结果。虚拟请求取消与续跑
见 6.3，原 waiter 的等待/取消见 6.4；6.2 的真实 RCU/owner ACK 探针不执行
JIT，不能计入实际 JIT 正例。主模式、寄存器、held-B、pending-B、学习后 callee
与远端测试分别验证不同路径，不能合称所有资源耗尽或所有生命周期均已完成。

## 5. 入口条件与嵌套续点

复杂嵌套前缀中的未知别名会导致地址分析扩大并保守拒绝。生产翻译器现在自动
尝试 `context_guards.EntryGuards`，收集分析所依赖的“不重叠”条件，并在执行
任何 body 指令之前检查。它不假定 waiter 栈、记录对象或绝对地址彼此独立，
也不需要新增 daemon 参数。

```text
无条件分析遇到有界地址精度耗尽
  -> 无 IJ 学习历史，包含普通嵌套 lock 控制 CALL，才尝试单入口条件分析
  -> 补齐所有 JIT 可达冷分支，再重新分析，不把缺失文本当作安全代码
  -> 每次别名分离记录两个完整字节区间（store 包含全部写入宽度）
  -> 条件分析通过：把全部条件生成在入口分发表及 body 之前
  -> 首次 root 调用：只从保存的入口 GPR 计算地址差，不解引用目标
     不重叠：执行 body，后续锁控制/hostcall 可在同一调用内继续
     重叠：ENTRY_REFUSED=6，保留入口 GPR/RIP/RSP、虚拟栈和外部内存
  -> kernel 仅接受真正首次 root 的 pre-body 拒绝，转为未开始的原生工作
```

只接受入口 GPR 加常量或绝对地址。收集上限为 1024 个区间、256 条最终条件；
未知基址、分析或条件预算耗尽继续保守拒绝。独立进入的 callee 不借用这个
条件分析，原无条件分析仍可处理它们。只有已注册锁控制 CALL 可保留
callee-saved 分析事实，普通函数按实际指令传播效果，不获得 ABI 保留假设；
未建模/native 调用和控制服务仍保留内存 clobber；唯一新增的局部例外是
5.3 中由运行时逐字节检查的 mutex 栈窗口。
GS/current、IRQ 及已知敏感符号拒绝规则不变。

### 5.1 学习后的直接 callee

`callee_table.txt` 记录需要解码的地址，不等于授权从该地址任意进入。
已有运行时入口约束只允许首次 root 或有合法逻辑父请求的锁续点。因此在无
IJ 历史时，可以尝试把学习后的代码作为该 root 的直接控制流重新分析：

```text
本次 CALL miss -> 原 waiter 原生完成，结束本次 JIT
  -> daemon 学习目标，供未来调用重编译
  -> 补齐文本和 JIT 范围；无条件分析保持原来的独立入口规则
  -> 合格的嵌套地址精度失败：改用受入口条件约束的单 root 分析
     CALL：传播压入源返回地址之后、未知调用 clobber 之前的真实状态
     callee：检查实际指令和所有内存效果，不另加独立未知入口
     RET：在已证明的 RSP 分区内读取弹栈前目标，再传播返回后的实际状态
          目标为确切数值时取白名单交集；未知/部分改写时仍合流到全部白名单目标
     CALL 后继：不能从 CALL 直接到达，只能由合法 RET 或其他真实边到达
  -> 选中图与 root 连通、完整 RET 图与生成表一致、可能执行的效果均检查后
     才生成入口条件和 body
```

损坏的虚拟返回地址可能命中该 RET 的其他白名单目标，不能假定调用栈一定
平衡。生成表不删除任何目标；仅有顺序内存事实证明本次状态不可能取某条边时，
才不沿那条边传播。确切改写返回槽可以跳过一个已连通后继，不给该后继伪造
入口状态。但这些后继的代码和 RET 目标仍会生成，所以 GS/FS、IRQ、已知敏感
符号和异类锁引用的无条件检查必须先遍历全部生成块，不能只检查获得数据流
输入的块。检查范围仍是当前 JIT episode，普通 CALL miss 后只由 waiter 执行的
后缀不重新纳入。入口别名条件不会校验运行时返回槽内容；这里没有证明任意
并发修改下的指针或 RET 值仍然有效。游离学习目标、间接 CALL/JMP、带栈调整
的 RET、返回表不一致或预算耗尽都会拒绝此条件路径。GS/current 等拒绝仍然
适用。诊断 `ENTRY_GUARDED_ADMISSION scoped_calls=true` 表示使用了这条路径，
不是新的 daemon 参数，也不代表所有已学习 callee 都能通过。

不同 RSP 数值/符号来源保存在不同分析分区，避免两层 CALL 在共享 RET 处提前
丢失返回槽与保存寄存器的对应关系；每块最多 64 个分区，总分区/访问数仍受
CFG 预算限制。未知 RET 的目标使用常规合流，不按假想的不断弹栈深度无限展开。
返回值通过原有别名、部分写入和 clobber 模型推导，不读取运行时栈，也不假定
普通 callee 保留 ABI 寄存器。预算不足仍拒绝整项准入，不丢弃某个分区来通过。

返回表构建按直接 callee 合并调用点，使用 visited 集合和迭代遍历，避免长 CFG
耗尽 Python 递归栈。共享 RET 尾部合并所有调用点的后继，不能只保留“对应
CALL”的返回地址；位置由解码数据库的 offset API 取得，不解析标签显示字符串。
默认 65536 单位的工作量预算统计指令扫描、节点/边遍历及返回目标添加。
位置无法解析、被遍历 callee 缺少后继/数据库、预算耗尽时，不写入部分返回表；
准入比较及最终生成阶段都以 `CONTEXT_NATIVE_ONLY` 拒绝，清除旧生成物并退出 2。
这不是运行时 JIT 指令预算，也不保证固定内存/耗时或解决代码版本隔离。

相关测试合并在 `test_context_guards.py`：多调用点、共享尾部、改写返回槽三种
短程序在 guest 用户态执行真实 wrapper 和生成代码，核对 callee 次数、被跳过的
后继及精确写入；新增两层带真实 prologue/epilogue 的 CALL 共用同一个 RET，
检查三段写入、恢复的 RBX/RBP 和最终 CALL 栈。具备受检窗口时还执行跨 mutex
控制 CALL 后的两次 RET，共享/独立 RET 均检查；用户态 bridge 仅代替成功控制
包的推进，仍执行真实 wrapper 和生成指令，不代替内核栈检查或真实 mutex。
另检查确切、未知整字和未知
低字节改写都不能漏掉跨调用点敏感指针；危险程序只做拒绝分析，不执行。
同一程序还在被确切 RET 改写跳过的后继中放置九类禁用操作，spin/mutex 两个
后端均须在生成前以准确 RIP 拒绝。这些是静态拒绝检查，不执行危险指令，
不新增日常用例，也不把它们算作内核 JIT 正例。
1200 个真实解码分支只验证返回表构建；循环、预算及损坏 CFG
检查拒绝与历史表不变，不计为内核执行证据，也不证明任意控制流安全。

在 `test_10_native_resume.sh 4 5` 中，combiner 已持有外层 A；学习后的 JIT
进入 helper，继续取得 B0–B6。尝试 B7 时，A 加七把子锁已经填满记录容量，
因此在取得 B7 之前保存该 `mutex_lock(B7)` 的 CALL 包并交回 waiter。
waiter 从这次加锁继续，随后自行释放其原生取得的 B7；B0–B6 和 A 的 unlock
交给保留原生 owner 的 combiner 执行并确认。不会释放原锁后从 A 入口重跑，
也不会在这次 native 后缀中重新进入 JIT。该 live 用例证明已翻译的 helper
执行到锁容量出口，不证明它的 RET 已在 JIT 中执行；短程序另行检查 RET。

多源码扩展复用此用例，不新增基础测试。`native-mutex-depth` 选择
`KD_NATIVE_SOURCE_MODULE=1`；脚本临时以 `KDLOCK_SOURCE_HELPER=1` 构建
`klock_module` 和可选的 `kd_depth_source`，默认构建不依赖后者。执行流为：

```text
根入口翻译，source modules=1
  -> 第一波 JIT miss 到本模块 kd_resume_depth_mutex，modules 仍为 1
  -> 原 waiter 完成后缀、全部调用者 join；学习本地 helper，暂停 daemon
  -> 第二波 JIT 进入本地 helper，miss 到 kd_depth_source_enter，modules=2
  -> 原 waiter 完成后缀、全部调用者 join；学习外部 helper，停止 daemon
  -> 第三波沿两层真实 CALL 进入 JIT 外部 helper，取得 B0-B6 后 RET
  -> 返回本地 helper 的译后代码，修改记录，B7 前真实 E2BIG
  -> 原 waiter 续跑，B0-B6/A 由原 owner ACK，逐请求恰好一次
  -> frame/writer 排空，退休使旧入口 NATIVE_ONLY，释放两份 source pin
  -> 正常卸载两个源码模块，再卸载 provider，恢复默认测试模块构建
```

`source_depth_protocol.py` 比较实际模块的 ELF/运行地址、镜像哈希、设备计数、
sysfs refcnt/holders 和原 entry。第二模块在 CALL miss 前已有来自 `klock_module`
的一份静态依赖，不是 source pin；miss 后 refcnt 应从 1 变成 2，重编译/执行后
仍为 2。退休后回到 1，原模块卸载后才为 0。原模块自己的 refcnt 则从 source
pin 的 1 降至 0。卸载拒绝、入口失效和两份引用释放均单独核对。
默认八线程的三波共 24 个加深请求，含准备阶段共 12025 个记录。两个 helper
都是 `noipa`/`noinline` 的真实函数，三份镜像及 callee table 按阶段留存；每波
学习必须在新日志中出现匹配 entry/target 的 JIT body、held=1 原生续跑、完整记录
和 A 的 ACK，不能拿前一波日志代替。最终容量波仍要求七个保留 child owner、
PENDING CALL 包和 exactly-once，引用观测不能代替执行证据。外部 helper 的
RET 确实在 JIT 中执行；本地 helper 在容量出口之后的后缀与 RET 原生完成。
共享 RET 使用有界分区，mutex 控制后的栈重载使用 5.3 的受检事实；不再通过
inline 消除调用层级。thunk/编译缓解选项、窗口外内存 clobber 和别名检查不变。
这里只验证两个模块，不证明 64 个 live 模块满槽、
通用热卸载或任意锁对象释放安全。增量验收状态见 [VALIDATION](VALIDATION.md)。

```sh
# Guest, confirmed recovery; replaces the simpler daily depth case.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case native-mutex-depth
```

### 5.2 运行时续点

非 root 首次分发不能随意跳过条件。`kd_jit_entry_has_scope()` 要求逻辑父请求
已经执行并在已知锁 CALL 后发布 `WAITING` / `ENTERED`，核对相同 entry、task、
GS，以及 post-CALL RIP/RSP、目标 B 和锁层级。CPU 本地的物理 parent 不能代替
逻辑父请求。mutex B 在同一 frame 内续跑，不创建远端 mutex 子 frame。

`ENTRY_REFUSED` 只有在首次 root、未处理 continuation/hostcall、返回入口
RIP/RSP 且 witness 为零时才能清除保守的 executed 标记。专用拒绝桩保证整个
寄存器包不变；kernel 不逐个比较 GPR。已执行后的拒绝、错误包或其他退出
仍按既有错误协议处理，零 witness 单独不授权重放。

这些校验只建立逻辑调用范围，**不是代码版本证书**。并发原地重编译可能使
父请求的条件与新代码不匹配，仍属于已延期的版本隔离限制。条件比较也会
修改 flags；本次不补 flags 活跃性验证或恢复，不宣称一般内存/上下文安全。

成功生成代码还会输出一次 `CONTEXT_SCREENING_ONLY`，标明没有运行时地址保护和
并发内存有效性验证。这不是某条指令已发生错误，也不是构建、发布或执行成功的
证明。入口指针、从内存重载的指针及 JIT 运行期间被其他线程改写的指针，仍可能
绕过静态敏感符号检查；无 warning 也不能用来证明安全。当前只用于经过人工
审查的实验负载，具体缺口与后续实现顺序见
[动态地址边界](DESIGN.md#721-dynamic-address-gap)。不能在已经执行副作用后使用
`ENTRY_REFUSED` 回到临界区入口，也不能把额外日志当作新增的恢复能力。

生产翻译先取得同一设备会话的模块范围能力，再读取有界的 CPU 元数据，把所有
possible CPU 的核心静态 per-CPU 区和启动时预留的模块区加入检查。模块区从
核心区大小按 4 字节对齐后开始，当前大小为 8192 字节。`__per_cpu_start=0`
是合法偏移起点，不能把低地址整体列为敏感区；也不能按整个 unit 扩展覆盖，
因为嵌入分配器可能已把尾部页归还普通内存。
日志 `STATIC_PERCPU_SCREENING` 给出 CPU 数 `cpus`、每 CPU 的 `core_bytes`、
`module_bytes` 和二者之和 `bytes_per_cpu`。可识别的直接/传播地址与跨界访问均
检查，内部普通符号不能截断范围。能力缺失、元数据异常、短读或不稳定时停止
翻译并报环境错误，不能记录为 native-only 成功。沿用同一 ioctl 及其 16 字节
大小，版本约定见 5.3；无需新 wrapper 参数或 guest 内核修改。
这仍不验证运行时未知指针、动态 per-CPU 分配或模块对象存活，也不是并发安全
证明；边界与现有 API 评估见 [静态区契约](DESIGN.md#722-static-per-cpu-ranges)。

只改诊断、不改变准入和生成指令时，复用以下两个程序检查日志字段、静默前后的
汇编一致性及真实 wrapper；不为日志重复运行基础模式或内核 live 矩阵：

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_jit_diagnostics.py test_jit_body_witness.py'
```

按改动选择以下 guest 测试，不能在宿主机执行生成机器码；它们不是每轮全部
运行的前置清单。只改翻译分析时选择相关 Python 程序及 audit；修改运行时
scope/续点时再选择对应 fixture 和 live 寄存器/远端用例：

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_context_guards.py test_context_policy.py test_context_memory.py test_jit_diagnostics.py test_text_regions.py'
python3 tests/audit_context_spills.py

# Runtime scope/continuation changes only; separate from translator-only work.
python3 tests/unit/test_jit_entry_scope.py
python3 tests/unit/test_native_after_outer.py
```

修改上述跨后端、全生成范围的静态准入时，用以下复杂组合检查主模式、返回型
hostcall、两后端寄存器续跑、学习后的两层 CALL/RET 和独立上下文拒绝。只改
测试选择或文档时不要重跑它们；不追加已被覆盖的 mode 0/1/3 基础诊断：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite core --suite admission \
  --case registers-8-3 --case registers-4-3 --case native-mutex-depth
```

若同时修改模块范围能力，单元选择再加入 `test_source_lifetime.py`，live 取上述
组合与 `--suite mutex-parallel --case native-mutex-stack-change` 的并集。
这检查真实设备协商、两类 writer 排空与 mutex 栈续点，不附带基础 smoke。
真实地址负例仅审查翻译结果，不执行危险访问；正常复杂用例必须继续产生返回后的
JIT body witness，mutex 正例仍须加载并回读 `mutex_jit=1`。

条件测试包含真实生成代码的重叠拒绝、无重叠写入和冷分支敏感操作拒绝。
scope fixture 提取生产 executor，覆盖首次拒绝、错误包、已执行后拒绝及
远端父子校验；它替代锁原语和 wrapper 边界，不是锁并发测试。前述 live 命令
另行验证真实 JIT、嵌套竞争及寄存器续跑。文本窗口测试检查新增可达块、块内
入口分割、GS/坏指令拒绝和扩展预算；它本身不代替内核中的 body witness。
结果只维护在 [验证记录](VALIDATION.md)，后续顺序见
[TODO](TODO.md#direction-and-priority)。

### 5.3 Mutex 控制 CALL 的栈检查

`handle_known_mutex_call()` 的运行时检查与同设备能力协商已接入。条件分析仅用
它保留受检窗口内的事实，真实两层 learned helper 已通过有界验收。执行流为：

```text
JIT 到达 mutex_lock/unlock 控制 CALL
  -> 验证原 waiter kernel stack 内的 CALL 字和其上方 256 字节窗口
  -> 保存窗口；执行原有 mutex 控制操作，真实 owner 不变
  -> 核对返回地址字、原控制目标与 post-CALL RIP/RSP
     -> 窗口未变：继续当前 JIT
     -> 窗口变化：STACK_CHANGED，从已完成 CALL 的后继原生续跑
        -> 保留当前内存/GPR；真实 owner 处理其持有锁的 unlock/ACK
```

窗口从 CALL 时 `RSP+8` 开始，不包含 CALL 返回地址字，不假定 waiter 栈私有。
只使用原 waiter 的 `task_stack_page()`/`THREAD_SIZE` 范围；读失败或控制包损坏
不允许借助此状态恢复。若 CALL 字有效但其上方不足 256 字节，则在锁操作发生
前使用 PENDING 包交回原 waiter，不能伪造资源错误或从入口重跑。
最终外层完成不再回到 JIT，无需该窗口保证。spin 的远端控制可能执行后续原代码，
不适用这个局部 mutex 约定；hostcall 也未获得新的内存保持保证。

模块结束输出 `kd_mutex stack checks: bytes=256 equal=... changed=... unavailable=...`；
变化/空间不足另有 `MUTEX_STACK_CHANGED` / `MUTEX_STACK_UNAVAILABLE` warning。
这些计数不是 JIT body witness，也不是窗口以外或任意并发写入的安全证明。
检查只比较，不把快照写回，已完成的锁操作和业务副作用均不能重放。

定向单元测试复用 `test_control_call`、`test_exec_frame` 和
`test_native_after_outer.py`；后者抽取生产 dispatcher/检查器/native-begin 代码，
使用有界数组代替 task stack，并在 mock 解锁原语中逐字节改变窗口。
它检查变化保留、返回包拒绝、保留 owner ledger 和 PENDING 边界，不证明真实
Linux 栈生命周期或并发执行。

真实并发验证复用 `test_10` 的 mode 4/stage 4 七角色拓扑，设置
`KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_STACK_CHANGE=1`，不设置
`jit_fail_pending_lock`。在已确认 recovery 的 guest 执行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case native-mutex-stack-change
```

执行流为：串行 promotion、发布 NORMAL、停止 daemon -> 设置 `native_stack_armed`
-> 原 waiter 在进入 A 前公布真实局部 `volatile unsigned long` 的地址
-> combiner 执行 A 的 JIT 前缀，保存栈窗口并在原生 B 上等待
-> 非目标 `kd_native` 持 B 者在 Linux `wait_list` 中确认等待者是 A 的真实 owner，
   不是原 waiter，随后写入暴露槽并正常释放 B
-> combiner 获得 B 后检测窗口变化，交还原 waiter 从 B 的 CALL 后继续
-> 原 waiter 读取新值并完成原有副作用，B/A 解锁分别交回真实 owner 确认。

该用例只写明确共享且仍存活的局部槽，不修改 CALL 字、寄存器包或 frame。
`mutex_stack_protocol.py` 必须同时确认：返回后的 JIT body、槽在 post-CALL
RSP 开始的 256 字节窗口内、`MUTEX_STACK_CHANGED`、实际构建模块中 mutex CALL
后继与 native RIP/RSP 一致、两个锁仍由原 combiner 持有、后缀一次及 B/A 两次 ACK。
执行条目的 NORMAL/code/target 等字段必须保持不变，防止普通 observer CALL miss
被误算通过。其余角色可以注册冷入口，但必须仍为 UNINIT、无 learned target
和 body。七个调用者均退出，最终记录、互斥、origin 计数和排空检查仍独立执行。
`test_mutex_stack_protocol.py` 只检查错误观测的拒绝，不作为 JIT/并发证据。

这验证了明确暴露的单槽在阻塞控制操作期间变化，不是任意栈发布或任意并发
写入的安全证明；结果只记录在
[VALIDATION](VALIDATION.md#real-mutex-stack-mutation)。

#### 同设备能力协商

翻译会话现已通过独立 `KD_JIT_CAPS` ioctl 查询运行时约定，不增加 wrapper 参数，
不改变 64 字节 entry 或 24 字节上传头。执行流为：

```text
打开或复制继承的读写设备描述符
  -> 验证当前 cdev 身份、读写权限和 source INFO 状态
  -> 在同一描述符上查询一次 CAPS，分别缓存 mutex 栈与模块范围能力
  -> 要求模块范围可用，读取 CPU 元数据建立静态区间
  -> pin / 读取实际内核文本，再执行有界分析与翻译
  -> 关闭 lease，清零缓存；新会话必须重新查询
```

`include/kd_source_api.h` 定义 x86-64 ioctl `0x80104b73`，输出四个 `u32`，
共 16 字节。当前 provider 返回 `version=2`、`features=3`（bit 0 为 mutex 栈
检查，bit 1 为模块 per-CPU 预留区）、`mutex_stack_bytes=256`、
`percpu_module_bytes=8192`。最后一项复用版本 1 的保留字段；模块范围从核心区
末尾按 4 字节对齐后开始，不包括动态 chunk 或 unit 尾部。
运行时数组和窗口大小共用常量；模块范围常量也与内核头及非空启动预留区核对。
这是 provider 固定的实现能力，不是可变准入状态、代码版本或 `mutex_jit` 开关。
OPEN/DRAINING/RETIRED 均可只读查询；查询不会新增 writer、pin 或重开准入。

两个 getter 都要求有效会话。`mutex_stack_bytes()` 可返回 0，表示不保留可选的
跨控制 CALL 栈事实；`percpu_module_bytes()` 缺失时直接报错，不能静默省略模块
地址准入。版本 1 仍可用于 source/retire 观察及查询旧 mutex 窗口，但不能满足
当前翻译的模块范围要求；应重建并重新加载匹配的 provider。
CAPS 不存在（ENOTTY）或版本/位图/大小/包不合法时，两项缓存都为 0 并打印
`JIT_CAPABILITY_UNAVAILABLE` / `JIT_CAPABILITY_INVALID`。已知版本未宣告的能力
必须对应零字段；其他 I/O 错误终止会话。source INFO API 仍必需，不得通过环境
变量覆盖能力或把另一个 provider 的查询用于当前翻译。

在 guest 仓库根目录执行 `python3 disassem/device_session.py capabilities` 可查看
`{"mutex_stack_bytes": 256, "percpu_module_bytes": 8192}`，不支持的字段为 0；
该只读命令仅用于诊断，不建立翻译 lease。真实翻译日志另有
`Translation runtime capability: mutex_stack_bytes=... percpu_module_bytes=...`。
已有双 frame 排空测试检查孤儿 writer 的缓存和同一描述符重查均保持 256，
并继续要求退休拒绝新 writer/发布；不另建重复 smoke 用例。

**条件分析只保留受检范围内的事实。** 必须同时具备有效的同设备能力、mutex
后端和已注册的 mutex lock/unlock 控制目标。先化简并验证 IR 确实将正确的源
返回地址压入 8 字节 CALL 槽，再应用该写入及其别名效果，从 post-push RSP+8
推导所有可能的窗口起点。不能恢复 CALL 之前的内存快照来取得旧事实。

每个 byte fact 都要求基址完全相同且位于每个候选窗口内；完整 word fact 还要求
所有字节均被覆盖，部分覆盖的 word 退回字节模型。不同 entry 基址、未知/扩大的
RSP 或无法识别的 CALL IR 不获得保持保证；不靠新增“不重叠”假设证明窗口归属。
原有别名/部分写入产生的敏感候选不会消失。普通 CALL、spin、hostcall、窗口外
事实及未知别名仍按原 clobber 处理；保留检查消耗同一工作预算，快照恢复不补充
预算，影响地址的分析耗尽仍拒绝准入。能力为 0 时保持旧的保守行为。

窗口、候选 RSP、CALL 压栈与预算检查合并在 `test_context_memory.py` 和
`test_context_guards.py`，不另建基础脚本。真实两层、栈变化及受影响复杂用例的
结果见 [VALIDATION](VALIDATION.md#checked-two-level-mutex)。更广的上下文与别名
工作仍在 [TODO C5](TODO.md#c5-origin-context-and-nested-boundaries)。

## 6. 资源拒绝与测试边界

先判断拒绝发生在哪个阶段，再决定执行流。资源不足不等于可以重跑入口：

```text
模块初始化分配失败 -> 初始化返回错误，尚未安装 hook
新入口没有代码块 -> 不发布半成品条目 -> ready=false
  -> wrapper 尚未调用 -> 队列按未执行请求处理，由 waiter 原生执行
JIT 已执行，新的 lock CALL 仍为合法 PENDING，尚未取得/发布新锁
  -> 仅支持的 ENOMEM/E2BIG -> 保留当前 CALL 包，原 waiter 完成原生后缀
本地 spin 获取后的 EIO，通过 6.11 的完整检查点验证
  -> SPIN_NATIVE -> CALL 后继原生续跑，不再获取 B
其余 ENTERED/ACQUIRED，或其他未经验证的 post-entry 错误
  -> 不授权入口重放，按既有 fail-stop 协议处理
```

以下是当前主要资源路径清单，不把组件测试写成所有生产调度均已验证：

| 资源 | 当前边界与处理 | 覆盖与缺口 |
| --- | --- | --- |
| 代码块池 / 执行表 | 最多 64 个 640 KiB 块、511 个槽；注册失败不发布条目，已有 key 不重复取块；原生拒绝不回收块 | `test_exe_registry.py` 检查真实全量/部分分配、清理与并发注册；6.6 通过真实 CALL 入口填满代码池，并组合两个存活 native frame 与新队列回退；511 槽满仍是合成元数据的探测边界测试 |
| 高层 JIT 入口 | 表不存在、空槽、未就绪、native-only、无 code block 或查无空槽均在 wrapper 前返回 | `test_jit_entry_scope.py` 使用真实 lookup/ready 和高层执行器，检查 spin/mutex 的完整 GPR 包、虚拟栈和锁记录不变；wrapper/锁原语仍是替身 |
| 上传边界 | 单块容量外的 payload 被设备拒绝；未知 key 不创建新条目 | 注册测试检查真实设备读写函数与最后一个合法字节；不证明完整镜像、并发替换或上传互斥锁语义 |
| hotlock 表 | 131071 槽；新地址无法建立采样记录时不晋升，继续原生 | `test_hotlock_sampling.py` 的生产函数容量测试；不是同时访问十万把真实锁的压力测试 |
| spin gate / acquisition ticket | gate 1024 槽、每 CPU 32 个 ticket；普通 hook 预留失败转原生；虚拟 B 必须遵守 CALL 阶段 | `test_spin_gate.py` / `test_spin_entry.py` 检查生产组件；6.3 组合真实 32-ticket 耗尽、存活 JIT/native frame、1024-slot gate 表满和新锁原生互斥；不能把新锁的未开始回退当作发布后恢复，也不能把 EOVERFLOW 等当作可恢复 ENOMEM |
| mutex shadow / task 记录 | shadow 1024 槽；task 记录用 GFP_ATOMIC 分配；hook 中失败在入队前转原生 mutex | `test_mutex_resources.py` 检查生产组件；6.6 将真实 shadow 表满、原生竞争与两个存活 frame 组合；task/RCU/ACK 的独立 probe 见 6.2 |
| spin / mutex node | 每 CPU 各 4 个；普通请求无 node 时用自己的栈等待私有 gate，再取得原锁；虚拟 spin 请求先取消预留再返回 | spin producer/队列与 live observer 有界覆盖；6.3 连接真实 JIT、虚拟 ticket 取消及原生续跑，但资源输入为注入；mutex 生产组合测试取代旧模型，`test_11` 有八 waiter 争用四槽，6.7 将真实四槽占满与存活 JIT/native frame 组合 |
| frame / held-lock / shadow stack | 8 层 frame、8 个逻辑锁记录与 CPU-local held-lock 容量分别检查；栈空间不是相同资源 | 6.8 区分真实物理链的继承锁记录满与独立 local-shadow 拒绝；另有生产 frame 容量、spin producer、远端拒绝及 mutex learned-depth 有界测试，不能由一项容量通过推导全部耗尽场景 |
| 源码依赖 / 会话退休 | 每会话最多 pin 64 个 LIVE 模块；单次读取不超过 256 KiB；OPEN -> DRAINING -> RETIRED 不可逆 | `test_source_lifetime.py` 执行真实 source/device/registry 决策，模块/IRQ/VFS 为替身；6.6 连接两个真实 frame、busy retire、后缀 ACK、源 pin 阻止卸载及失效后释放；5.1 的深度扩展另行验证两份真实模块源码 pin |

代码池组件测试在真实初始化流程的分配 API 上注入失败，不修改生产容量，也不
执行生成机器码。它用 24 个 pthread 对六个 key 重复注册以竞争真实注册 gate，
所有表读取在 join 后进行；这不是 Linux IRQ、抢占或同时执行 JIT 的证明。
入口拒绝检查不是锁回滚测试，不能用于扩大已执行后的恢复范围。

在 guest 按改动点选择以下单元测试，不要求每次依次执行：

```sh
python3 tests/unit/test_exe_registry.py
python3 tests/unit/test_jit_entry_scope.py
python3 tests/unit/test_mutex_resources.py
```

注册测试的七个变异负例必须成功编译、再由断言检测；编译错误或超时不算通过。
真实 JIT 与 native 后缀仍用第 3 节命令验收，证据见
[VALIDATION](VALIDATION.md)。队列资源耗尽的下一步以 [TODO](TODO.md) 为准。

### 6.1 Mutex 资源与恢复包

```text
__kd_mutex_lock
  task 已在代理路径 / 未晋升 / mutex_jit=0 -> 原生 mutex
  shadow 表满 / task 登记失败 -> 原生 mutex；不登记 JIT、不预留 node
  登记 task、请求翻译 -> _kd_mutex_lock
    gate 空闲 -> 获取原生 mutex；physical_owner=current
    gate 忙且没有 node -> 保留 task 登记，在自身栈上等 gate，再获取原锁
    gate 忙且有 node -> 保存入口状态 -> 汇编 slowpath / 队列
      未执行交接 -> 先取得原锁，再释放 node、恢复调度状态，返回原临界区
      已完成 / native 续跑 -> 复制整个 pt_regs，清除 resume_node，释放 node
        -> 恢复抢占/迁移状态 -> 已完成跳到 unlock 后 / native 跳到当前续点
```

`test_mutex_resources.py` 提取生产的节点函数、shadow 查找、hook、入口与
原锁获取/释放辅助函数。它检查 256 个占用/可用栈组合、顺序与乱序复用、
非法释放、满表碰撞及已有条目不变，以及 cold/已有 shadow 下的 hook 回退。
真实 `_kd_mutex_lock` 分别从 hook 和直接 API 接收三种合法 slowpath 结果。
在恢复抢占的替身中立即复用刚释放的 node，随后比较整个 guest `pt_regs`
（当前 168 字节），确认 consumer 使用自己的副本。native 续跑保留 task
登记与物理 owner；borrowed unlock 只能交给通知入口，不能由 waiter 直接解锁。

八个变异负例同样要求先编译成功，再由断言检出。物理锁、task API、调度、
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
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_22_mutex_task_lifecycle.sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_TASK_CPUS=0,20,21 \
  bash tests/test_22_mutex_task_lifecycle.sh
```

第二条使用当前双 NUMA guest 的 CPU 编号；其他拓扑须先核对。
每次预期 `orders=2 acks=4 deferred_frees=2 failures=0 JIT=0`，并要求内核无
错误、task/frame 排空。脚本保存 `Evidence:`、卸载自测模块并重建默认版本。
若核心协议断言失败，探针会 fail-stop，不能带着存活读者/请求卸载代码。

这是实际内核协议测试，但不执行 JIT。续跑 RIP/RSP 是不跳转的构造包；outer
batch 回调只释放真实 A，不运行生产队列调度。测试不证明汇编跳转、任意信号/
退出竞争、多请求远端调度或热卸载安全。自测入口与释放计数在默认构建中均不存在。

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
  KD_NATIVE_VIRTUAL_RESOURCE=1 bash tests/test_10_native_resume.sh 8 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_VIRTUAL_RESOURCE=2 bash tests/test_10_native_resume.sh 8 4
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
  bash tests/test_10_native_resume.sh 8 4
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
CPU 9/10/11 的三个压力角色与 CPU 12 的控制脚本：

```text
真实 JIT 写入 -> ticket E2BIG -> 原 waiter 在 B 的 Linux 队列中等待
  B holder 已观察到该 waiter，保持 B；A combiner 保留 A 和 31 个额外锁
  -> 记录当前 gate 占用、source frames=1、原 A/B 物理 owner
  -> CPU 9 的目标线程顺序获取/解锁 1025 把不同测试锁，填满真实 gate 表
  -> CPU 10 的非目标 holder 获取最后一把无 gate 的原生 L
  -> CPU 11 的目标线程真实分配 gate 失败，在同一 Linux L 上排队
     holder 观察公有锁字的 pending/tail；两个角色按原生互斥完成写入
  -> join 三个新角色，再次确认 gate 满表与旧 native frame 仍存活
  -> 控制脚本允许旧 B holder 解锁，原 waiter 完成后缀和 A 的最终 ACK
  -> 原候选者释放额外 ticket/pin，全部调用者排空，退休并卸载
```

准备阶段只通过现有 SELFTEST 参数控制新锁的 promotion，不填造 gate 条目。
`spin_selftest_gate_count` 只在 map guard 下读实际占用；`kd_gate refusal` 标识
真实查找失败的 task/CPU/原锁。新角色使用相同的已定位 ELF CALL 入口，daemon
已停止，不能把冷入口注册或这些原生写入计为 JIT。逐锁记录检查 membership、
写入次数和值、公有/私有锁字与 pin 配平；最终全数组检查不能只看循环总次数。

`gate-pool.json` 保留模块 SHA256、真实数组/入口和 prepare/held/filled/drained
快照；这里的 drained 只表示三个压力角色退出，旧 frame 此时必须仍为 1。
`gate-protocol.log` / `gate-result.json` / `gate-role-status.tsv` 进入统一归档。
B holder 的有界等待不交接 owner；控制器出错仍释放这个测试等待条件、join
已有角色并保留失败，不能因此生成 PASS。不得在仍持锁时强制卸载。

这是 gate 表的真实耗尽和新请求的 **未开始** 原生回退，不是 gate 失败后的
JIT 重放、PENDING gate 失败或任意 pool/任务退出组合的证明。实际结果见
[gate 压力验收](VALIDATION.md#spin-gate-pressure)。修改此扩展只运行
`test_spin_gate.py`、`test_spin_entry.py`、`test_regression.py`，以及升级后的
`virtual-ticket-refusal` 和共享驱动的 `virtual-node-refusal`；不要重跑基础 smoke。
修改其他公共快照/取消分支时，再按受影响范围选对应复杂用例。

修改共享 SELFTEST 加载/清理逻辑后，还应回归原有 CPU-local shadow 容量用例。
它在 CALL advance 和虚拟 ticket 申请之前拒绝，不等同于上述两个出口：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_SHADOW_CAPACITY=1 \
  bash tests/test_10_native_resume.sh 1 4
```

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
  KD_NATIVE_WAITER_SIGNAL=10 bash tests/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=9 bash tests/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 \
  bash tests/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 \
  bash tests/test_10_native_resume.sh 4 4
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
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_19_mutex_signals.sh 1
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_19_mutex_signals.sh 3
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
  bash tests/test_10_native_resume.sh 4 4
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PENDING_CONTENDED=1 \
  KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 KD_NATIVE_WAITER_RACE=1 \
  bash tests/test_10_native_resume.sh 4 4
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
每个 waiter 都有独立记录，B 仍由自己的 A combiner 获取，不新增远端 mutex frame。

```text
两组串行预热 -> 共用一次 module-wide 等待 -> 连续执行两组晋升采样
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
  -> 真实 compiler fork/exec 建立 writer
  -> 父进程退出而子进程保留引用
  -> retire 返回 EBUSY，进入 DRAINING；子进程仍能读源码，但发布被 ESHUTDOWN 拒绝
  -> 拒绝新 writer，释放测试暂停；已有 task/origin 路由仍服务 owner unlock
  -> 指定第一组完成后缀 -> B unlock/owner ACK -> A logical unlock/owner ACK
  -> 第一组以 kd_renamed 发布 post-unlock done，再恢复 klock_test 名称
  -> 第一名原生竞争者取得/释放 B，并确认另一 frame 的 B 仍拒绝 trylock
  -> 第二组再次核对自己的 A/B owner 和未完成记录，再完成后缀与两个 ACK
  -> 第二组仍以 kd_renamed 完成记录，再恢复名称
  -> 第二名原生竞争者取得/释放自己的 B
  -> 原八个 caller 与两名 B 竞争者全部返回 -> 核对记录、镜像哈希和排空
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
  bash tests/test_23_mutex_parallel_native.sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_PARALLEL_FIRST=1 \
  bash tests/test_23_mutex_parallel_native.sh
```

`KD_MUTEX_PARALLEL_FIRST` 默认 0，仅接受 0/1，决定哪组先完成，不改变锁协议。
脚本显式加载并读回 `mutex_jit=1`，只通过 `mutex_parallel=1` 的 opt-in workload
复用 mode 3 ioctl；普通 mode 3 不变。`mutex_parallel_armed` 只能在准备完成后
置 1；双 frame 分支还显式开启/读回 `native_resume_rename=1`。除下述内置改名及
peer 信号流程外，不要与其他信号、资源注入、remote-chain
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

此时 source 仍 OPEN，comm 已不匹配目标；现有 selector 必须依赖 active-task
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
6. 只有两者取消并重新排队后才进入原来的 writer/retire 流程、释放暂停门。
   第一组 waiter 解 B 时仍通过真实 owner 执行；它的原生竞争者随后取得 B，
   在持有这把 B 时尝试另一把 B，必须失败且其 owner 仍为另一 combiner。
7. 第一名竞争者真实 `mutex_unlock(B)` 后才发布完成位。第二组原 waiter
   同时等待第一组最终 ACK/done 和该完成位，然后重新检查自己保留的 A/B
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

仅该工作负载/路由观察器变化时，在 guest 选择相关单元和原有复杂用例：

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_mutex_parallel_protocol.py test_mutex_resources.py'
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh \
  --case parallel-drain-0 --case parallel-drain-1 --case parallel-node-pressure
```

前两个入口组合改名路由、取消/重排、容量和退休；第三个保护共享驱动的真实
节点压力。若修改共享信号客户端，再追加 `test_mutex_signal_protocol.py` 和
`native-peer-1/3` 两项 live，分别保留 SIGUSR1/SIGKILL 协议；不把它们作为
每次改名路由修改的前置条件。本次改名路由及历史冻结证据见
[验收记录](VALIDATION.md#renamed-native-frame-routing)。

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
组合。结果与失败准备记录见 [代码池验收](VALIDATION.md#code-pool-with-live-frames)。

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
及地址复用断言均保留；结果见 [shadow 验收](VALIDATION.md#mutex-shadow-with-live-frames)。

这是真实队列/JIT/native/owner-ACK 的组合测试，不使用构造 frame 或额外 task
引用。它不固定 RCU 读者，不替代 6.2 的延后释放证明，也不单独采样全部 GPR；
测试模块在整个 ioctl 中有自身 fops/module 依赖保护，这不证明通用源码模块
热卸载安全；源码、锁对象和 hook 的不同寿命见 [DESIGN 3.1](DESIGN.md#31-source-lock-and-hook-lifetimes)。
完整寄存器续跑仍由第 3 节的 register gates 验证。它本身不耗尽节点；同 CPU
节点压力见 6.7。跨 NUMA/远端多请求、其他资源组合和 native 后缀内直接退出
仍需后续实现或验证。

### 6.7 同 CPU 的 Mutex JIT 拒绝

复用 `test_23`，仅将 lane 1 的 combiner 从 CPU 5 改到 CPU 1，与 lane 0 共用
CPU；逻辑 waiter 仍在 CPU 2/6。两组 entry 都必须先发布 NORMAL，daemon 随后
停止，不注入 context、不改代码状态、不构造 frame。此场景强制 lane 1 先完成：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --case parallel-shared-cpu
# Equivalent direct invocation, only in the confirmed recovery guest:
KDLOCK_RECOVERY_CONFIRMED=1 KD_MUTEX_PARALLEL_SHARED_CPU=1 \
  KD_MUTEX_PARALLEL_FIRST=1 bash tests/test_23_mutex_parallel_native.sh
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
  bash tests/test_23_mutex_parallel_native.sh
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

### 6.8 物理 Frame 链与容量检查

八层物理 frame 用例中的每个新 frame 都从 CPU-local 栈继承此前的锁记录，
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

只修改该观察器时，运行相关单元程序和现有两项复杂用例，不增加简单前置测试：

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
SELFTEST 镜像和默认恢复构建；本次结果只维护在 [VALIDATION](VALIDATION.md)。

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
[early-outer continuation](VALIDATION.md#early-outer-continuation)；选择器单元与
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
[VALIDATION](VALIDATION.md#queued-spin-acquisition)，不拼接成新完整矩阵。

## 7. 分层与增量回归

基础验收通过后，不再把基础用例作为每轮回归的前置步骤。按修改的行为选择
复杂代表用例及相关单元测试；这是减少重复运行，不是缓存旧 PASS 后假装重跑。
翻译准备中的 warmup、promotion、发布检查仍必须保留，否则无法保证实际 JIT。

替代依据是执行路径和断言，而不是代码长度或循环次数。复杂用例必须覆盖同一
后端/配置下原用例的关键结果和实际 JIT 执行证据，才可替代对应正例；不同退出
边界、失败分支和协议观测仍独立保留。开发新功能时可先用基础用例定位，复杂
验收通过后，把覆盖较小的用例移出日常范围；完全重复的脚本合并或删除，并更新
本节的替代说明和选择器检查，不让基础用例重新成为每轮默认前置步骤。

`tests/run_all.sh` 无参数只列出范围，不执行内核测试。命令定义集中在
`tests/regression.py`，`--suite` 可重复，`--case` 可点选，两者按用例名称取并集。
所有日常范围都排除基础验收和被更复杂用例覆盖的普通诊断项；`extended` 也排除
已经登记替代关系的十一项诊断。这些关系集中在选择器的 `COVERED_DIAGNOSTICS`，
无参数或 `--list` 会列出，`test_regression.py` 检查它们不会重新进入套件。
去重只针对同一个用例身份，不静默删除用户显式点选的简单诊断，也不因为历史
通过而跳过本次选中的用例；点选诊断不会自动附带它的替代用例。
`--list` / `--dry-run` 不构建、不加载；真正执行只允许 root 在规定 guest 路径，
并要求已经确认 recovery。以下例子按需要选择，不是顺序执行清单：

```sh
# Preview on either host or guest; mode 5 appears only once.
bash tests/run_all.sh --suite mutex --suite hostcall --case mode-5 --dry-run

# Guest only, after confirming recovery: ordinary mutex changes, modes 4/5.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite mutex

# Dual-frame code/shadow pools, peers and retirement, plus combined node pressure.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite mutex-parallel

# Focused unit programs only; TESTS= avoids unrelated C unit builds/runs.
make -C tests/unit run TESTS= PY_TESTS='test_regression.py test_mutex_parallel_protocol.py'
```

### 选择范围

| 范围 | 用途与覆盖 |
| --- | --- |
| `baseline` | 首次验收/故障定位：设备加载卸载、无 JIT 执行的翻译链路、mutex_jit=0 原生对照；不随日常回归运行 |
| `native-controls` | 显式纯原生寄存器对照 control-0/3；非目标线程、无翻译/JIT，不加入其他范围，流程见 3.1 |
| `spin` | mode 2/7/8：hostcall、非 LIFO 解锁、多队列嵌套 |
| `mutex` | mode 4/5：竞争嵌套、重复 hostcall/同 CPU waiter/持续竞争，均 mutex_jit=1 |
| `core` | `spin` 与 `mutex` 的五个复杂代表用例；不是全部功能验收 |
| `hostcall` | mode 2/5，不能用普通深层嵌套替代 native service 返回 JIT 的检查 |
| `registers` | 八个退出边界的 GPR/返回栈检查，不被普通业务状态正确所替代 |
| `admission` | 十二项上下文/GS/别名拒绝负例；修改分析器还须运行独立 admission audit |
| `spin-native` / `mutex-native` | 对应后端的退出点续跑、提前 A 释放/原生依赖、资源拒绝/容量、后续 native-only 策略；spin 另含受检获取后续跑；mutex 还含真实栈变化、同队列同 CPU 续跑、两项并行 frame 与跨队列同 CPU 满槽/拒绝组合 |
| `spin-remote` | 八层物理 frame 的同/跨 NUMA、多请求远端和三种 late-exit，日常不先重复一层/两层 |
| `mutex-signals` | 原 waiter 的两种不可中断信号、两种 API 的取消/获得/无偏置竞争、独立 native peer |
| `protocol` | 原生参与者互斥和两种 RCU/owner ACK 探针；JIT=0 的探针不能计为 JIT 正例 |
| `mutex-parallel` | 两个真实 JIT/native frame 的两种顺序，合并代码池与 mutex shadow 表满/新队列回退、原生 B 竞争者取消后重排、退休与重载；另含同 CPU 满槽/上下文拒绝/task 分配失败组合 |
| `extended` | 64 项独立/复杂代表用例，排除 baseline、native-controls 及十一项已覆盖诊断；保留 mode 6 的同一 frame 三锁检查，仅用于大范围变动或验收 |

以上是按行为划分的起点，不是自动影响分析。wrapper/ABI、共享 executor、锁入口
或生命周期的改动可能影响多个范围，须取相关范围并集；内核基线变化先重新做
基础验收。只改文档不运行 JIT；只改某个 oracle/测试驱动，验证该驱动及对应 live
用例即可。不能因为复杂业务正例通过而删除尚未覆盖的错误分支或独立协议。
如果只修改测试选择规则，运行
`make -C tests/unit run TESTS= PY_TESTS=test_regression.py` 与 `--dry-run` 即可，
不加载模块或重复 live 验收；单元测试清单仍保留完整入口供首次/显式全量检查。
纯原生对照入口的改动选择 `test_regression.py`、`test_native_registers.py`，
两项 `native-controls` 和受影响的嵌套寄存器 JIT 正例。只是修改选择规则时仍
只做单元/预览，不把原生对照变成每轮必跑的基础检查。

设备会话改动选择已有的 `test_daemon_policy`、`test_text_regions.py` 和
`test_jit_diagnostics.py`，分别检查真实 fork/exec、分块传输、设备身份/关闭和
翻译错误分类；不新增重复的基础脚本。对应 live 选择 mode 2/4/5、
`native-mutex-depth` 和 `context-mixed`，覆盖两后端执行、hostcall、学习后的
再次翻译和 native-only 发布。独立的真实 cdev 引用探针及其边界见
[设备会话验收](VALIDATION.md#device-session-binding)，不能计为一次 JIT 执行。

只修改 5.3 的能力协商时，选择 `test_source_lifetime.py`、`test_text_regions.py`
和 `test_native_after_outer.py`，分别检查真实 ioctl/退休边界、同设备缓存/错误包、
共享窗口常量与运行时续点。live 用 `native-mutex-stack-change` 替代普通 mode 4，
保留 mode 2/5、`native-mutex-depth`、`context-mixed`，再取 `mutex-parallel` 并集。
这覆盖实际能力查询、两种孤儿 writer 排空及共用清理，不新增基础前置检查；
没有修改分析规则时不附带完整 admission audit。

源码生命周期改动再选择 `test_source_lifetime.py` 及实际受影响的 registry、
frame、入口和路由测试。该专属程序提取生产 source/device/retire 逻辑，检查
容量、去重、LIVE/init 范围、关闭后的准入、忙状态和失效先于 module_put，
不以用户态替身声称内核 reader 已排空。其 live 验证并入现有两个
`parallel-drain-*`，原来的 JIT/逐锁 ACK/精确记录断言不减少。同 CPU 资源压力
分支不提前退休，避免阻止待测的新请求；所有分支结束时都经公共 retire 清理。
仅测试驱动修正时重跑失败项及对应复杂用例，不自动附带已通过的基础检查。
6.6 的 writer/重载、代码池、shadow 表和 B peers 共用三个 `mutex-parallel`
复杂用例，不另保留旧简单版本或附带 baseline。相关驱动修改选择
`test_mutex_parallel_protocol.py`，再按实际资源改动补注册表/入口或
`test_mutex_resources.py`，不运行全量单元测试。shared-CPU 压力分支检查共用
脚本的默认路径。只改观察器时只选其单元与受影响 live；只改文档时不运行 JIT。
额外锁的晋升准备是资源实验前提，不是重复的基础验收；失败结果与不同冻结
版本仍须分开保留。
两源码扩展升级现有 `native-mutex-depth`，与 `native-4-4` 一起检查可选模块路径及
共享脚本的 PENDING 路径（现含 6.1 的同 CPU 续跑）；不附带单模块 depth 或基础 smoke。新增观测用
`test_source_depth_protocol.py` 检查错误状态、pin/loader 混淆、错误目标和提前释放；
选择器另检查残留 `kd_depth_source` 必须阻止下一项。修改观测后只重跑该程序；
生产 source/寄存器/分析器未变时，不把已接受的独立测试全部重新运行。
当前该用例已升级为两次真实 CALL 学习，不再附带旧的 inline 适配器版本。
若同时修改 5.3 的分析规则，先运行相关分析/生成单元程序和 audit，再取 `core`、
`native-mutex-depth`、真实栈变化、mutex 两个寄存器退出边界及 `context-mixed`
的并集；相同观察器或默认驱动已被其中用例覆盖时不再重复选择。

例如修改两后端共用的返回表生成器，先选择 5.2 的五个分析/生成程序和 audit，
再运行 `core` 加已学习深度路径，不附带 baseline、单锁 mode 0/3 或全量单元测试：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite core --case native-mutex-depth
```

### 合并与保留

以下是普通成功路径的替代关系，不是对所有故障、指令或调度的等价证明。
基础诊断仍可用 `--case` 点选；其余独立负例、寄存器和生命周期探针不因此删除。

| 仅点选的诊断 | 回归中的替代用例 | 保留的检查 |
| --- | --- | --- |
| `mode-0` | `mode-2` | 单 spin 锁的 JIT body、完整状态、排空，并增加 hostcall 返回 |
| `mode-1` | `mode-8` | A/B 嵌套锁/解锁、实际 JIT、完整状态，并增加内层队列竞争 |
| `mode-3` | `mode-5` | mutex_jit=1 的单锁代理、实际 JIT、原锁互斥与状态，并增加重复 hostcall/持续竞争 |
| `node-physical-1-0` / `node-physical-2-0` | `node-physical-8-0` | 相同 NUMA 配置的真实物理 frame/node 生命周期与队列观测 |
| `node-physical-1-1` / `node-physical-2-1` | `node-physical-8-1` | NUMA-aware 配置下相同断言，增加链深度 |
| `parallel-shared-cpu` | `parallel-node-pressure` | 同 CPU pre-body 拒绝、存活 frame/owner ACK，并增加真实满槽和 task 分配失败 |
| `native-1-4` | `virtual-ticket-refusal` | 相同 PENDING B 续跑、实际 JIT、原 waiter 排队和最终 ACK，增加真实 32-ticket/gate 表满及新锁原生互斥 |
| `native-1-3` / `native-4-3` | `registers-1-3` / `registers-4-3` | 同后端普通 held-B CALL miss、业务记录/native probe、B->A 后缀，增加原始寄存器和 CALL 栈检查；不覆盖 6.10 的提前 A 释放 |

mode 6 不属于上述替代关系：同一 frame 中保留 A/B/C 与多层物理 frame 不同。
日常核心范围无需先跑它，但 `extended` 仍检查该独立深度路径。
`shadow-capacity` 同样不是八层物理链的重复项；二者到达不同的容量检查，见
[6.8](#68-物理-frame-链与容量检查)。保持 `spin-native` / `extended` 中的独立入口。

- 删除 `test_03_hotlock.sh`、`test_06_daemon.sh`，合并到 `test_02_jit_engine.sh`：
  一次准备检查 promotion、entry、内核文本读取、生成物、确切入口发布和排空后清理。
  `pipeline` 不执行生成代码，仅用于首次验收/定位。
- 删除 `test_07a_mutex_jit_smoke.sh`；mode 3 的 `test_07` 验证同类单锁成功路径、
  总计数和更多竞争场景，且有返回后 body witness；不再为“恰好一次 JIT”单设
  调度烟测。需要单锁定位时用 `--case mode-3`。
- mode 0/1/3/6、一层/两层 frame 等诊断入口仍可点选，但不附带在复杂用例前执行。
  `test_09` 保留为主模式兼容入口，无参数只显示统一清单；显式模式去重且不会
  自动附带其替代用例。需要完整主模式验收时须明确传入模式，见第 3 节。
  不删除 benchmark 的 mode 定义。
- 同 CPU 用例复用 `test_23` 的参数分支；日常用 `parallel-node-pressure` 同时验证
  context refusal、真实满槽和另一请求的注入 task 分配失败，不再运行覆盖较小的
  `parallel-shared-cpu`，也不为每种资源增设重复的基础脚本。
- 源码退休 busy/排空检查扩展已有双 frame 用例，不另设“加载一次、卸载一次”的
  smoke；同设备能力协商也复用该用例中的实际 writer。状态机边界与错误变异
  测试仍独立保留，不能由复杂正例通过替代。
- 栈变化续跑扩展 `test_10` 的七角色竞争驱动，不另加简单 smoke。它检查已完成
  控制 CALL 的后继，不能替代 PENDING 未开始获取或普通 CALL miss 的独立检查。
- `waiter-interruptible` / `waiter-killable` 检查取消后 A 的最终 ACK 已完成、
  原生 B owner 仍持锁。释放竞争用例允许 B 更早解锁，即使也返回 `-EINTR`，
  仍不覆盖这个持锁进度断言。因此前两项保留在 `extended` 并可单独点选，
  不自动加入日常 `mutex-signals`；同一命令的不同环境参数不能直接当作重复项。
  具体执行流和 oracle 见 6.4/6.5，选择器测试检查两类用例不会被相互替代。
- 单元测试中刻意构造的边界、失败变体和 JIT=0 协议探针并非重复正例，继续保留。

### 执行与证据

执行流为：选择/去重 -> 确认 guest/recovery 与空闲状态 -> 冻结源码及起始环境 ->
按项运行现有脚本和 oracle -> 检查退出码、dmesg、排空、源码未变 -> 归档证据 ->
全部满足后创建 `accepted` 并运行下一项。任何失败停止后续，不自动重试、强制
卸载或放宽判定。
runner 清除继承的 `KD_*` / `KDLOCK_*` 注入变量，只使用选中命令的明确设置和
recovery 确认；特殊参数实验应直接调用相应脚本，不冒充命名用例。

输出目录默认 `/tmp/kdlock-regression.*`，或 `--output` 指定一个仓库外的新目录。
不用再从多个临时目录手工拼接常规用例证据：

| 文件 | 用途与边界 |
| --- | --- |
| `selection.json` | 精确脚本、参数与本次选定的注入环境，不包含未运行项目的通过结果 |
| `source.json` / `source.tar.gz` / `source-archive.json` | 冻结运行/测试输入及逐文件、整包 SHA256；含 `guest.config` 和 guest 补丁，排除 Kbuild 生成文件 |
| `environment.json` / `kernel.notes` | 用例开始前的 boot notes、uname、启动参数、CPU/NUMA、挂载/抢占/sysctl、工具和 Python 依赖查询；不是完整构建环境或执行中配置证明 |
| 每项的 `output.log` / `exit-status` / `dmesg.log` | 脚本输出、原始退出码和结束时内核日志；日志读取失败也使验收失败 |
| `artifacts.tar.gz` / `protocol.tar.gz` | 生成工作区，以及脚本明确宣告的协议/角色/daemon 文件，不扫描无关临时文件 |
| `post-case-builds.tar.gz` | 用例结束时存在的模块、daemon 和 benchmark 文件；可能包含恢复的默认构建或先前的可选模块，不等于实际加载镜像的身份 |
| `evidence.json` | 三个证据包及各成员的 SHA256、原目录/文件路径和符号链接文本 |
| `result.json` / `accepted` | 独立记录 script_exit、kernel_fault、drained、source_unchanged、evidence_complete、错误与起止时间；全部通过后才创建标记 |

环境采集使用与脚本相同的基础环境，固定 `LC_ALL=C`；命名用例的 `KD_*` 设置
仍在 `selection.json` 中。只保存代码内明确列出的 PATH、编译/Python 等继承
变量，不转储整个环境；未设置的变量为 JSON `null`，不等于工具的默认值。
只读查询常用 gcc/cc、make、binutils、bash，记录选择路径、解析目标、SHA256、
版本输出和状态；不执行任意 `CC`/`MAKEFLAGS` 字符串来猜测完整构建命令。
Python 依赖通过 PATH 中的 `python3` 查询，不假定它与 runner 解释器相同。
记录 miasm、pyelftools、future、pyparsing 的安装版本、位置与声明依赖，不导入
翻译器或访问 JIT 设备。启动保留原工具/虚拟环境链接路径，哈希读取解析目标；
这不改变协议归档禁止跟随链接的规则。

每个命令查询限时 10 秒；缺失工具/包、非零退出、超时、损坏 JSON 或无法读取
运行设置会在 `environment.json` 中保留错误并停止，尚未启动任何用例。
`stage=before_cases` 是起始观察，不是整个测试期间配置/依赖未变化的证明。
脚本随后可能设置 sysctl 或重建 SELFTEST 镜像，仍以脚本和逐项协议证据为准。
版本元数据和工具二进制哈希不覆盖全部导入代码、动态库、编译参数或加载镜像；
不得据此自动跳过测试、把未运行项记 PASS，或宣称已有依赖锁定/可重复构建。

`results.tsv` 的 0 只代表脚本退出码，不能替代 `accepted`。脚本通过也可能因
缺少已宣告文件或归档失败而被拒绝；归档完整也不证明执行了 JIT，仍须保留本
文规定的返回后 body witness 和逐用例 oracle。上下文负例允许没有 `jit.bin`。

现有 `Evidence: /tmp/kdlock-*` 声明整棵协议目录，公共 daemon 启动函数另输出
`Evidence file:`。重复声明或已经在协议目录内的 daemon 日志只收集一次。
协议树中的符号链接仅保存目标文本，既不读取目标，也不在 tar 中创建活动链接；
writer 探针指向的 helper 本身已在冻结源码包中。源码、生成工作区和独立声明
的文件仍不允许通过链接越界。设备、FIFO、递归包含输出目录以及文件变化都
使归档失败；失败的 `.partial` 不是完整证据包。

失败且调用者/模块已排空时也保留镜像和协议，以便后续清理临时目录后查验。
未确认排空时只保留已经取得的源码、命令、输出和状态，标记
`evidence_complete=false` 并停止；不把仍在变化的文件伪装成冻结证据，也不强制
卸载或重跑来补齐 PASS。原始临时目录不自动删除；主输出目录可直接整体 tar
归档，SHA256 清单用于核对内容，不是签名或不可变 JIT 版本证明。

已有输出目录可用仓库内的只读工具校验，`RUN_DIR` 指向该目录：

```sh
python3 tests/verify_evidence.py "$RUN_DIR"
```

执行流：读取冻结源码、起始环境与选择清单 -> 核对 boot notes/源码包 -> 按
选择顺序核对 journal、退出码、日志、result 和 accepted -> 核对三个证据包的
精确成员及哈希 -> 再查读取期间文件未变 -> 输出 JSON。工具不执行记录中的
命令、不解包载荷、不跟随 tar 链接，也不访问当前 guest/JIT 设备或修改结果。
不要求 root/recovery；离线归档复核可在宿主机或 guest 完成，工具单测仍在 guest。

- 退出 0：所选项目都有一致且通过的历史记录。
- 退出 1：记录完整但含失败，或部分选中项目尚无记录。
- 退出 2：记录矛盾、缺少必需文件、未完整归档、文件变化或格式/大小不支持。

`unrecorded_cases` 只表示缺少结果，不证明进程从未运行或已经退出，不能据此
重启 VM。工具限制单文件元数据 16 MiB、压缩包 256 MiB、单包完整解压流 1 GiB
和清单/包成员 100000 项；超限不静默忽略。只认当前采集格式，不自动补造旧记录。
这些检查不认证记录来源，也不重新执行逐用例 oracle；若内容与全部清单一起被
改写，一致性本身不能识别伪造。仍需可信的外层包 SHA256、原执行证据和
case-specific JIT/协议检查。不得把离线校验记为新 JIT、当前源码通过或加载镜像证明。
只改该只读工具时运行 `test_regression.py`，再检查已有成功/失败归档即可，
不重跑无关负载。当前工具验证见 [离线校验](VALIDATION.md#offline-evidence-verifier)。

只修改用例开始前的只读环境采集时，运行 `test_regression.py` 即可；它同时
实际读取 guest 环境、核对工具字节和检查缺失/超时/坏输出的停止边界，不加载
模块或重复 JIT。当前结果见 [环境证据](VALIDATION.md#environment-evidence)。
修改逐项归档流程时运行该单元程序，再选一个带协议目录的复杂正例、
独立 daemon 日志的 hostcall 正例和已有上下文负例。归档修正后只重跑失败项及
尚未运行的受影响项，不重复已经覆盖且实现未变的路径。本轮冻结版本与失败
记录见 [归档验收](VALIDATION.md#scoped-evidence-capture)。源码包不包含系统依赖的
完整字节、guest 磁盘或整个内核构建目录。原生对照已改用 3.1 的仓库内驱动，
起始工具/依赖元数据也已采集，但系统依赖交付、内核构建环境及历史镜像身份
仍独立保留，不能宣称任意 fresh checkout 已能重现
全部历史结果。

每项默认外层超时 600 秒，可显式调整；不要因此取消 SSH 的外层超时。
在输出目录创建 `STOP`，会等当前项结束并检查排空后于下项之前退出 93；
不改写运行中的脚本，不在 native waiter 仍持有 frame 时中断它。

当前 `extended` 包含已登记脚本的代表组合，不穷举所有参数，也不等于历史
67 项矩阵：它不自动包含显式 `native-controls` 和上述已覆盖诊断，另含 shadow-capacity、
两项 native-peer 和同 CPU context refusal/真实满槽扩展。历史矩阵的命令和结果
仍按当时冻结版本记录，不改写为新的选择范围。
最新结果见 [VALIDATION](VALIDATION.md)。每次只报告实际选择的项目；未选择项是
未重跑，不把旧结果合成当前版本的“全量通过”。
