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

尚未通过的 learned-depth 主功能单独运行：

```sh
bash tests/test_10_native_resume.sh 4 5
```

该脚本先执行 JIT 前缀并产生真实 helper CALL miss，排空调用者后让 daemon
学习 helper，再检查新范围的 JIT 和锁容量退出。目前扩大范围被准入拒绝，
因此即使第一段有 body witness，整项仍失败；不能把原生完成当作此项通过。

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

本轮实测结果与未通过项集中记录在
[VALIDATION: Cross-Window CFG Completion](VALIDATION.md#cross-window-cfg-completion)。
完整矩阵的逐项命令见 [测试清单](VALIDATION.md#current-matrix-manifest)，
本轮使用相同的 51 个选择器重新执行，不借用旧的短回归结果。
完整 51 项中 50 通过、1 失败，通过项包含 36 项实际 JIT。mode 0–8、
mode 1/4 的普通 CALL 寄存器、held-B、pending-B，以及 mode 8 的两项寄存器
续跑检查通过。mutex 学习深层 callee 后的扩大准入仍未通过，不能将本轮
改进写成整个项目或所有资源耗尽场景已完成。

## 5. 入口条件与嵌套续点

复杂嵌套前缀中的未知别名会导致地址分析扩大并保守拒绝。生产翻译器现在自动
尝试 `context_guards.EntryGuards`，收集分析所依赖的“不重叠”条件，并在执行
任何 body 指令之前检查。它不假定 waiter 栈、记录对象或绝对地址彼此独立，
也不需要新增 daemon 参数。

```text
无条件分析遇到有界地址精度耗尽
  -> 单一初始 root，且包含普通嵌套 lock 控制 CALL，才尝试条件分析
  -> 补齐所有 JIT 可达冷分支，再重新分析，不把缺失文本当作安全代码
  -> 每次别名分离记录两个完整字节区间（store 包含全部写入宽度）
  -> 条件分析通过：把全部条件生成在入口分发表及 body 之前
  -> 首次 root 调用：只从保存的入口 GPR 计算地址差，不解引用目标
     不重叠：执行 body，后续锁控制/hostcall 可在同一调用内继续
     重叠：ENTRY_REFUSED=6，保留入口 GPR/RIP/RSP、虚拟栈和外部内存
  -> kernel 仅接受真正首次 root 的 pre-body 拒绝，转为未开始的原生工作
```

只接受入口 GPR 加常量或绝对地址。收集上限为 1024 个区间、256 条最终条件；
未知基址、分析或条件预算耗尽继续保守拒绝。已学习的独立根、已解码的独立
callee 不借用这个条件分析，原无条件分析仍可处理它们。只有已注册锁控制 CALL
可保留 callee-saved 分析事实，普通调用不获得该假设，内存 clobber 仍保留。
GS/current、IRQ 及已知敏感符号拒绝规则不变。

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
结果只维护在 [验证记录](VALIDATION.md#cross-window-cfg-completion)，后续顺序见
[TODO](TODO.md#learned-callee-increment)。
