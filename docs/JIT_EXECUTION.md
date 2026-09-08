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
  +-- combiner 持有原生 L --> wrapper 装载 waiter 的 pt_regs
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
当前 mode 1/4 仍被保守准入拒绝，因此上述完整命令不能预期全绿；这也是要
单独保留失败日志的原因。mode 0/2/3/5 已通过本轮实际 JIT 检查。

普通 CALL 的真实寄存器/退出点续跑，以及上下文拒绝测试：

```sh
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 0 1
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 3 1
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 1 2
KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 4 2
bash tests/test_12_context_native_only.sh 10
bash tests/test_12_context_native_only.sh 11
KD_CONTEXT_LOCK_API=percpu-spill bash tests/test_12_context_native_only.sh 3
```

普通 CALL 测试检查当前退出状态、waiter 身份、返回栈及副作用恰好一次；不能用
完全原生对照代替。上下文拒绝测试则必须没有 JIT 执行，随后验证原生结果。

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

本轮实测结果与未通过项集中记录在
[VALIDATION: JIT Episode Scope](VALIDATION.md#jit-episode-scope)。
完整矩阵的逐项命令见 [测试清单](VALIDATION.md#current-matrix-manifest)，
本次整理文档后的短回归另记于 [提交前验证](VALIDATION.md#commit-verification)，
不能将短回归当作完整矩阵重跑。
完整 51 项中 37 通过、14 失败，通过项包含 23 项实际 JIT。mode 0/3 的
普通 CALL 寄存器续跑检查通过；复杂 mode 1/4/8 及相关路径仍需进一步实现，
不能把本轮范围选择的完成写成整个项目或所有模式已完成。

## 5. 入口条件分析（尚未接入生产）

复杂嵌套前缀中的未知别名会导致地址分析扩大并保守拒绝。新增
`context_guards.EntryGuards` 收集分析所依赖的“不重叠”条件，而不是直接假定
waiter 栈、记录对象及绝对地址相互独立。**生产 `dis_assem` 不启用此分析，也不
调用 emitter；没有可开启它的 daemon 参数。mode 1/4 仍未通过实际 JIT 验收。**

当前已实现的分析/测试流程：

```text
测试显式传入 collector，限定一个 CFG root
  -> 每次别名分离记录两个完整字节区间（store 包含全部写入宽度）
  -> 合并相邻区间，保留间隙，生成有界条件集合
  -> 用户态测试把 predicate 放到真实 wrapper 的 body 标签之前
  -> 从保存的入口 GPR 计算地址差，不读取指针指向的内存
  -> 重叠：实验退出，保存的寄存器包/虚拟栈/外部内存不变
     不重叠：执行测试用 MOV/RET body，并检查返回后的 witness
```

只接受入口 GPR 加常量或绝对地址；无法识别的基址继续保守处理。收集上限为
1024 个区间、256 条最终条件，耗尽不能当作通过。已学习的独立根和已解码的
独立 callee 暂不支持。只有已注册锁控制 CALL 可保留 callee-saved 分析事实，
普通调用不获得该假设，内存 clobber 仍保留。GS/current、IRQ 及已知敏感符号
拒绝规则不变；这些条件也不是任意指针或并发内存的安全证明。

在 guest 中运行，不能在宿主机执行生成机器码：

```sh
cd /root/host_fs/kdlock
python3 tests/unit/test_context_guards.py
python3 tests/unit/test_native_after_outer.py
make -C tests/unit run
python3 tests/audit_context_spills.py
```

前两项分别覆盖 14 项条件测试和真实 CALL 推进函数的保存包检查；不是内核
锁并发或 guarded mode 1/4 的执行证明。捕获文本回放只能证明候选分析可通过，
不能安装其未检查的汇编。测量及源文件身份只维护在
[验证记录](VALIDATION.md#entry-guard-foundation)。

接入前仍须实现专用 pre-body 拒绝协议，并证明非入口续跑继承同一逻辑调用的
已通过条件。实验 emitter 的非 root 分支目前跳过检查，生产不能无条件采用。
真正未开始的工作才可原生执行；已产生副作用的异常仍不能入口重放。之后再做
真实锁控制/远端执行、负条件拒绝、mode 1/4/8 及完整矩阵测试，任务顺序见
[TODO](TODO.md#guarded-admission-increment)。不新增第三个参数，不修改 guest 内核，
也不在此次基础提交中扩展已延期的 flags 或代码版本隔离工作。
