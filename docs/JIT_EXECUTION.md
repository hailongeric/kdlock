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

普通 CALL miss 的 `regs.ip` 指向原 callee，`regs.sp` 保留刚压入的源返回地址。
waiter 不是从临界区入口重跑，之前的写入和已完成的 B 不重放，也不做事务回滚。
native 续跑期间，combiner 保留已经获得的物理锁并按既有协议处理 unlock 通知；
等待这次 native 续跑完成，不恢复同批其他代理请求的执行。
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

只在可恢复的 guest 中构建和运行，不能在宿主机加载模块。当前 guest SSH
端口为 2222，已有 Linux 6.1.159 hook/exports；本次不修改 guest 内核。
先确认恢复快照和空闲状态，完整流程见 [AGENTS.md](AGENTS.md)。
normal 模式共享源码无需复制；recovery 模式虽路径相同但使用 ext4，只同步
哈希不同的文件，不移动或整目录复制仓库。

以下命令全部在 guest 的 `/root/host_fs/kdlock` 执行：

```sh
cd /root/host_fs/kdlock
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
make -C tests/unit run
python3 tests/audit_context_spills.py
```

确认恢复快照后执行主要模式。脚本负责编译、加载、检查、停止 daemon 和卸载：

```sh
export KDLOCK_RECOVERY_CONFIRMED=1
bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5
```

该入口遇到失败立即停止；检查每种模式时可分别传入一个 mode，不能因为前面
通过就假定后面执行过。mode 3/4/5 脚本显式加载 `mutex_jit=1` 并检查实参。
daemon 的 `--mode 1/2` 只选择工作目录布局，不是 benchmark 的 mode。
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

学习普通 helper 后的深层 mutex JIT/容量退出单独运行：

```sh
bash tests/test_10_native_resume.sh 4 5
```

该脚本先执行 JIT 前缀并产生真实 helper CALL miss，排空调用者后让 daemon
学习 helper，再检查新范围的 JIT 和锁容量退出。必须执行 helper 中翻译后的
加锁指令，验证真实容量退出、保留锁和 owner ACK；只有第一段 body witness
不能通过整项验收。学习重编译期间先排空旧调用者，并非已实现版本隔离。

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

最新批次的时间、源码身份、结果及逐项命令集中记录在
[VALIDATION](VALIDATION.md) 和 [测试清单](VALIDATION.md#current-matrix-manifest)。
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
未建模/native 调用和控制服务的内存 clobber 仍保留。
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
     RET：把实际返回后的状态传给全部允许的返回目标
     CALL 后继：不能从 CALL 直接到达，只能由合法 RET 或其他真实边到达
  -> 所有选中块均可达、RET 效果边与生成目标表一致，才生成入口条件和 body
```

损坏的虚拟返回地址可能命中该 RET 的其他白名单目标，不能假定调用栈一定
平衡。分析必须覆盖生成表的所有边；游离学习目标、间接 CALL/JMP、带栈调整
的 RET、返回表不一致或预算耗尽都会拒绝此条件路径。GS/current 等拒绝仍然
适用。诊断 `ENTRY_GUARDED_ADMISSION scoped_calls=true` 表示使用了这条路径，
不是新的 daemon 参数，也不代表所有已学习 callee 都能通过。

在 `test_10_native_resume.sh 4 5` 中，combiner 已持有外层 A；学习后的 JIT
进入 helper，继续取得 B0–B6。尝试 B7 时，A 加七把子锁已经填满记录容量，
因此在取得 B7 之前保存该 `mutex_lock(B7)` 的 CALL 包并交回 waiter。
waiter 从这次加锁继续，随后自行释放其原生取得的 B7；B0–B6 和 A 的 unlock
交给保留原生 owner 的 combiner 执行并确认。不会释放原锁后从 A 入口重跑，
也不会在这次 native 后缀中重新进入 JIT。

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

在 guest 中运行，不能在宿主机执行生成机器码：

```sh
python3 tests/unit/test_context_guards.py
python3 tests/unit/test_jit_entry_scope.py
python3 tests/unit/test_native_after_outer.py
python3 tests/unit/test_text_regions.py
make -C tests/unit run
python3 tests/audit_context_spills.py
```

条件测试包含真实生成代码的重叠拒绝、无重叠写入和冷分支敏感操作拒绝。
scope fixture 提取生产 executor，覆盖首次拒绝、错误包、已执行后拒绝及
远端父子校验；它替代锁原语和 wrapper 边界，不是锁并发测试。前述 live 命令
另行验证真实 JIT、嵌套竞争及寄存器续跑。文本窗口测试检查新增可达块、块内
入口分割、GS/坏指令拒绝和扩展预算；它本身不代替内核中的 body witness。
结果只维护在 [验证记录](VALIDATION.md)，后续顺序见
[TODO](TODO.md#direction-and-priority)。

## 6. 资源拒绝与测试边界

先判断拒绝发生在哪个阶段，再决定执行流。资源不足不等于可以重跑入口：

```text
模块初始化分配失败 -> 初始化返回错误，尚未安装 hook
新入口没有代码块 -> 不发布半成品条目 -> ready=false
  -> wrapper 尚未调用 -> 队列按未执行请求处理，由 waiter 原生执行
JIT 已执行，新的 lock CALL 仍为合法 PENDING，尚未取得/发布新锁
  -> 仅支持的 ENOMEM/E2BIG -> 保留当前 CALL 包，原 waiter 完成原生后缀
已经 ENTERED/ACQUIRED，或其他未经验证的 post-entry 错误
  -> 不授权入口重放，按既有 fail-stop 协议处理
```

以下是当前主要资源路径清单，不把组件测试写成所有生产调度均已验证：

| 资源 | 当前边界与处理 | 覆盖与缺口 |
| --- | --- | --- |
| 代码块池 / 执行表 | 最多 64 个 640 KiB 块、511 个槽；注册失败不发布条目，已有 key 不重复取块；原生拒绝不回收块 | `test_exe_registry.py` 提取真实 init/add/lookup/publish/exit，检查全量及部分分配、失败清理、并发重复注册；当前配置先耗尽代码池，511 槽满是合成元数据的探测边界测试 |
| 高层 JIT 入口 | 表不存在、空槽、未就绪、native-only、无 code block 或查无空槽均在 wrapper 前返回 | `test_jit_entry_scope.py` 使用真实 lookup/ready 和高层执行器，检查 spin/mutex 的完整 GPR 包、虚拟栈和锁记录不变；wrapper/锁原语仍是替身 |
| 上传边界 | 单块容量外的 payload 被设备拒绝；未知 key 不创建新条目 | 注册测试检查真实设备读写函数与最后一个合法字节；不证明完整镜像、并发替换或上传互斥锁语义 |
| hotlock 表 | 131071 槽；新地址无法建立采样记录时不晋升，继续原生 | `test_hotlock_sampling.py` 的生产函数容量测试；不是同时访问十万把真实锁的压力测试 |
| spin gate / acquisition ticket | gate 1024 槽、每 CPU 32 个 ticket；普通 hook 预留失败转原生；虚拟 B 必须遵守 CALL 阶段 | `test_spin_gate.py` / `test_spin_entry.py` 检查真实组件耗尽；仍需更多 hook 到队列的组合失败调度，不能把 EOVERFLOW 等都当作可恢复 ENOMEM |
| mutex shadow / task 记录 | shadow 1024 槽；task 记录用 GFP_ATOMIC 分配；hook 中失败在入队前转原生 mutex | `test_mutex_resources.py` 填满真实 shadow 表并测试 hook 回退，task API/IRQ 为替身；`test_22` 单独连接真实 task get/put、owner ACK 和 RCU 延后释放，边界见 6.2 |
| spin / mutex node | 每 CPU 各 4 个；普通请求无 node 时用自己的栈等待私有 gate，再取得原锁；虚拟 spin 请求先取消预留再返回 | spin producer/队列与 live observer 有界覆盖；6.3 连接真实 JIT、虚拟 ticket 取消及原生续跑，但资源输入为注入；mutex 生产组合测试取代旧模型，`test_11` 另有八 waiter 争用四槽的真实回退 |
| frame / held-lock / shadow stack | 8 层 frame、8 个逻辑锁记录与 CPU-local held-lock 容量分别检查；栈空间不是相同资源 | 生产 frame 容量、spin producer、远端拒绝及 mutex learned-depth 有界测试；不能由一项容量通过推导全部耗尽场景 |

代码池测试在真实初始化流程的分配 API 上注入失败，不修改生产容量，也不
执行生成机器码。它用 24 个 pthread 对六个 key 重复注册以竞争真实注册 gate，
所有表读取在 join 后进行；这不是 Linux IRQ、抢占或同时执行 JIT 的证明。
入口拒绝检查不是锁回滚测试，不能用于扩大已执行后的恢复范围。

在 guest 运行：

```sh
python3 tests/unit/test_exe_registry.py
python3 tests/unit/test_jit_entry_scope.py
python3 tests/unit/test_mutex_resources.py
make -C tests/unit run
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

这是实际 JIT/原锁/取消/续跑的组合测试，但不是自然池耗尽证明：context 原本
已分配，仅局部视图被置空；count=4 不代表四个真实存活节点。它不覆盖 gate/
ticket 池自然耗尽、发布后失败、任意抢占、任务退出或 flags 恢复。所有新增
探针均在 `KDLOCK_SELFTEST` 内，默认执行流和两元素 wrapper ABI 不变。

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
