# 入口条件与控制边界验证

这里集中入口 guard、learned callee 和 mutex 栈检查的协议与测试说明。
当前准入算法见 [准入设计](../design/admission.md)；通过范围见
[测试冻结记录](../../tests/README.md)，旧专门协议不自动继承新采样器的通过结论。

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
不支持的 segment/base、IRQ 及已知敏感符号仍拒绝；显式 GS 使用 origin base。

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
入口状态。但这些后继的代码和 RET 目标仍会生成，所以不支持的 segment/base、IRQ、已知敏感
符号和异类锁引用的无条件检查必须先遍历全部生成块，不能只检查获得数据流
输入的块。检查范围仍是当前 JIT episode，普通 CALL miss 后只由 waiter 执行的
后缀不重新纳入。入口别名条件不会校验运行时返回槽内容；这里没有证明任意
并发修改下的指针或 RET 值仍然有效。游离学习目标、间接 CALL/JMP、带栈调整
的 RET、返回表不一致或预算耗尽都会拒绝此条件路径。不支持的 segment/base 等拒绝仍然
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
通用热卸载或任意锁对象释放安全。增量验收状态见 [VALIDATION](../VALIDATION.md)。

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
审查的实验负载。用户于 2026-09-13 明确继续延期访问时 guard、从原内存指令交回
waiter 的新出口及其局部条件码保护；当前没有对应开关或可运行验收，不再等待范围
确认。现有 CALL miss/受检控制出口的原生续跑保持不变。具体缺口与未来实现契约见
[动态地址边界](../design/admission.md#721-dynamic-address-gap)。不能在已经执行副作用后使用
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
证明；边界与现有 API 评估见 [静态区契约](../design/admission.md#722-static-per-cpu-ranges)。

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
python3 tests/tools/audit_context_spills.py

# Runtime scope/continuation changes only; separate from translator-only work.
python3 tests/unit/run.py execution/test_jit_entry_scope.py
python3 tests/unit/run.py execution/test_native_after_outer.py
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
入口分割、GS lowering、FS/坏指令拒绝和扩展预算；它本身不代替内核中的 body witness。
结果只维护在 [验证记录](../VALIDATION.md)，后续顺序见
[TODO](../TODO.md#direction-and-priority)。

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

定向单元测试复用 `test_control_call`、`test_exec_capacity.py` 和
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
[VALIDATION](../VALIDATION.md#real-mutex-stack-mutation)。

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
结果见 [VALIDATION](../VALIDATION.md#checked-two-level-mutex)。更广的上下文与别名
工作仍在 [TODO C5](../TODO.md#c5-origin-context-and-nested-boundaries)。
