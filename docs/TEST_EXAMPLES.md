# 测试用例与重叠分析

本文按测试入口说明用途、覆盖关系和保留理由。2026-09-12 已核对
`tests/unit/Makefile`、全部单元入口及相关 fixture、21 个 shell 驱动和
`regression.py` 的 case/环境参数，并完成节点、mutex、frame、CALL 和 tail 模型精简。
2026-09-13 复核清单并补强既有远端单元的完整寄存器包与 DONE 发布检查，未增加入口。
同日复用现有热锁采样单元，复现并修复跨锁窗口缩短及锁外旧时间戳误判；
最终生产检查和六项复杂 JIT 结果见 [热锁验收](VALIDATION.md#hotlock-promotion-ordering)。
同日将既有 mode 4 升级为七角色/双 CPU，复用 mutex 协议单元验证真实等待和身份；
普通/OOO 分支及受影响的 mode 5 已定向验证，未新增日常 case 或重复基础验收。
普通 mode 4 还增加独立会话，覆盖两 A 共用原生 B 时的 native 后缀、后继 JIT 和
非目标 peer；原七角色阶段保留。入口按源码 CALL 返回地址识别，额外 hot-B
生成物不计为 A 的执行证据，见 [6.15](JIT_EXECUTION.md#615-两个-a-combiner-共享原生-mutex-b)。
mode 5 还保留原有服务返回阶段并加入 CALL 超额度 native 后缀；复用两个现有
单元入口检查生产退出包和完整日志，执行流见 [6.13](JIT_EXECUTION.md#613-call-次数额度与原生后缀)。
mode 2/5 的时钟后还执行标量 `int_sqrt`，消费高位参数的返回结果；既有生成、
consumer 和日志单元覆盖第三个服务，不新增程序、方法或命名 case。正常 JIT
每次返回两个服务，mode 5 超额度后的标量调用则由原 waiter 原生执行。
mode 8 保留原复杂阶段，再加入两条独立 A 请求共享 B 的纯 JIT、混合完成阶段；
额度退出的 remote parent 包和 B 后继顺序复用现有 consumer/远端日志单元，
没有新增程序或命名 case，角色与证据边界见 [6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner)。
逐项分析是静态审查，
精简后的定向单元验证单独记录，不代表全部测试重跑。
测量基础新增一个不重叠的 `test_benchmark.py` 入口：实际用户态驱动的计时、
分位数和部分失败契约此前没有单元覆盖；它不重复内核 CS oracle 或新增 live case。
执行边界及参数见 [负载测量](JIT_EXECUTION.md#33-带观测的负载测量)。
同入口另有 113 项配对观测检查，覆盖参数/顺序、计时阶段 body、发布/镜像变更、
服务计数、翻译资源/时间区间/身份、控制台变化、同输入配对及失败保留。
队列计量复用既有 executor、spin/mutex producer 和配对观察器入口，检查保存的
dispatch 端点不含正文时间、单次消费、拒绝保留和 native 发布前的记录顺序；
实际排队/JIT 证据另由现有代表用例提供，不新增极端组合或固定 case。
`paired_benchmark.py` / `benchmark_arm.sh` 是
独立的显式性能实验，不加入下面 80 个固定 case 或任一套件；命令与准备/测量
执行流见 [配对实验](JIT_EXECUTION.md#34-原生锁与-jit-配对实验)。
运行策略统一见 [分层与增量回归](JIT_EXECUTION.md#7-分层与增量回归)，
实际结果见 [VALIDATION](VALIDATION.md)。

## 1. 数量与结论

以下库存于 2026-09-16 按分组目录核对；运行约定为基础简单功能加直接相关功能，
不因保留完整库存而自动全量运行。目录和命令见 [测试入口](../tests/README.md)。

| 统计对象 | 当前数量 | 含义 |
| --- | --- | --- |
| `tests/unit/Makefile` 的入口 | 40 | 2 个 C 程序、38 个 Python 程序；`make ... run` 默认仅两个基础 C，`run-all` 显式全量 |
| Python `test_*` 方法定义 | 500 | 静态 AST 计数；不含 C 断言、`main()` 驱动和 `subTest` 参数展开，不能作为全部用例数 |
| `tests/live/test_*.sh` | 22 | 编号有空缺，不能按最大编号 24 计数；包括调度器、组件自测和 GS 正例 |
| `regression.py` 的 `CASES` | 80 | 固定回归的唯一命名用例；不含配对实验按参数生成的会话 |
| `SUITES` | 15 | 可重叠的选择视图，不能相加计算独立用例数 |
| `extended` | 64 | 排除 3 项 baseline、2 项 native control 和 11 项已覆盖诊断 |

已确认存在语义重叠：11 项 live 诊断已经从套件中排除；单元中的
`test_spin_node_count.c` 三项模型行为已有生产代码测试覆盖，现已移除该模型。
`test_mutex_transition.c` 的四项契约已对应到生产 hook/selector 和 combiner 测试，
补齐改名与关闭准入的检查后也已移除。
`test_exec_frame.c` 的保留契约已迁入生产 frame/ledger/清理测试，过时的 A 记录删除
模型改为验证当前的保留记录语义。`test_jit_call_policy.c` 的保留检查已迁入生产
CALL/hostcall 测试，移除过时的远端 mutex B 模型。`test_tail_encoding.c` 的五项
检查已迁入生产 mutex 编解码测试，移除该模型和仅供旧模型使用的两个头文件。
补充原 waiter 退出、嵌套调度、CALL 额度、双根和显式计量装载检查后，当前 496 个 Python 方法
未发现完全相同的 AST 方法体；这只排除直接复制，
不证明它们在语义上全无重叠。

除上述模型外，独立测试及 live 选择规则保留；双 frame 原 waiter 退出扩展复用
既有程序和 case，不新增日常入口。下文区分已经生效的去重、精简候选，
以及尚无充分替代依据的检查。文件数减少与运行成本减少是两件事：
把多个程序拼成一个文件，仍执行原来的断言，并不会自动减少工作量。

## 2. 选择与环境

本表清单不是完成项目必须全部跑过的门槛。按最新的
[交付范围](TODO.md#delivery-scope)，低概率边界不要求继续补实现或专项测试；
已有用例保留供相关主路径改动和显式诊断使用。只按改动选代表用例，不反复扩展
极端组合；未选择的场景不记为通过，已选用例的实际 JIT 和状态断言不能削弱。

宿主机或 guest 都可以只读预览：

```sh
bash tests/run_all.sh --list
bash tests/run_all.sh --suite mutex --suite hostcall --case mode-5 --dry-run
```

第二条只选择 `mode-4`、`mode-5`、`mode-2`，其中 `mode-5` 执行一次。
去重依据是 case 名称；显式同时选择 `mode-3` 和 `mode-5` 时仍运行两项。
`run_all.sh` 只转交参数，无参数只列清单。源码未改、环境未变且基础验收已有
证据时，后续按修改行为选择复杂用例，不重复 baseline。

模块构建、单元测试、daemon、benchmark 和 live 测试均在 guest
`/root/host_fs/kdlock` 执行。先按 [依赖步骤](PROJECT_GUIDE.md#33-检查依赖与空闲状态)
选定 venv 的 PATH；运行包使用 `disassem/requirements.txt`。新环境首次验收可用
既有全量单元、admission 和 core，不增加测试入口或日常前置矩阵。
以下是分别选择的例子，不是必须顺序运行的清单：

```sh
# Guest: only the changed selection/evidence controller.
make -C tests/unit run TESTS= PY_TESTS=test_regression.py

# Guest: only the changed pending-CALL helper and its production consumer.
make -C tests/unit run TESTS=basic/test_control_call PY_TESTS=test_native_after_outer.py

# Guest: initial acceptance or an explicitly requested full unit run.
make -C tests/unit run

# Guest: affected mutex JIT paths, after confirming a recoverable snapshot.
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/run_all.sh --suite mutex
```

选择单元程序时同时指定 `TESTS` 和 `PY_TESTS`；只设置其中一个不会清空另一个的
默认列表。`mutex_jit=0` 是排除 JIT 干扰的显式 debug 对照；项目的 mutex JIT
正例必须使用 `mutex_jit=1`。正例须同时核对生成物、entry/lock 匹配且 wrapper
返回后的 `body=1`、负载副作用；拒绝负例和 JIT=0 组件探针分别报告。

### 2.1 Recovery Guest 与 Normal

Recovery Guest 指 `run_vm.sh recovery` 启动的可恢复实验环境，不是另一套
kdlock 协议，也不会自动关闭 JIT。两种模式的 guest 工作目录相同，底层存储不同：

| 项目 | Recovery | Normal |
| --- | --- | --- |
| guest 源码路径 | `/root/host_fs/kdlock`，guest 本地 ext4 | `/root/host_fs/kdlock`，9p 共享 |
| 宿主机编辑 | 不自动同步；比较单文件哈希后按需 scp | 共享挂载可见；不要同时编辑或改写在运行的输入 |
| QEMU 外设 | 不启用 VirtFS/VFIO，支持记录的 `savevm/loadvm` 流程 | 启用共享等配置，不能假定支持同样快照 |
| 测试用途 | 复杂 JIT/模块实验，执行前确认可恢复快照 | 开发准备；不能跳过 live 测试的恢复前提 |

宿主机仓库是 `/home/eric/vm/vm-shared/kdlock`，与上述 guest 路径并不相同。
已记录的测试配置为 40 vCPU、28 GiB、双 NUMA、`nokaslr` 和 voluntary 抢占；
实际环境及内核 Build ID 每次按 [手动运行](PROJECT_GUIDE.md#3-一步一步运行)
和 [baseline](../kernel_baseline/README.md) 核对。
从宿主机 `/home/eric/vm/qemu-scripts` 启动脚本；已有 VM 时先检查进程与 SSH，
不重复启动。`KDLOCK_RECOVERY_CONFIRMED=1` 只表示已完成快照确认，不能创建或
证明快照存在；重启也不等于 `loadvm`。具体操作只维护在
[VM 操作手册](AGENTS.md#虚拟机存活检查与重启)。

## 3. Shell 驱动逐项分析

下表覆盖全部 21 个 `test_*.sh`，合并原来的 case 映射和脚本清单，避免两份描述
漂移。所有 shell 文件均在 `tests/`。精确参数以
`bash tests/run_all.sh --case <name> --dry-run` 为准。

| 脚本 | 命名 case 或调用方 | 实际检查与重叠结论 |
| --- | --- | --- |
| `test_01_module_load.sh` | `module` | 设备创建/删除、入口符号、模块加载卸载；与复杂用例准备阶段重叠，保留首次/定位入口 |
| `test_02_jit_engine.sh` | `pipeline` | promotion、翻译、上传并等待 NORMAL，随后不再跑临界区；`jit_success=0`，不能算 JIT 执行 |
| `test_04_spinlock.sh` | `mode-6/7/8`；`test_09` 的 `mode-0/1/2` | 普通、hostcall、单 frame 三锁、非 LIFO、远端多队列；mode 8 三阶段分别检查单 logical waiter、双 root 纯 JIT、首 waiter 退出后的同 B 后继 JIT，不以深度替代请求隔离 |
| `test_05_mutex.sh` | `mutex-off` | mode 3/4/5 的 `mutex_jit=0` debug 对照；不作为 JIT 前置 |
| `test_07_mutex_jit.sh` | `test_09` 的 `mode-3` | 单 mutex 重复委托、同 CPU 多 waiter、持续竞争；普通成功路径由 mode 5 覆盖，显式定位时保留 |
| `test_08_mutex_jit_modes.sh` | `test_09` 的 `mode-4/5` | mode 4 保留七角色/双 CPU，再单独检查两 A/共享原生 B 的 native 后缀、后继 JIT 和非目标 peer；OOO 只复用第一阶段；mode 5 保留服务返回和超额度后缀。执行流见使用指南 6.12/6.13/6.15 |
| `test_09_jit_execution_modes.sh` | `mode-0` 至 `mode-5` | 调度上述实现；也可显式分发 mode 10/11 拒绝检查；不是另一份 JIT 测试，不应连同子脚本再跑一遍 |
| `test_10_native_resume.sh` | `registers-*`、`control-*`、`native-*`（不含 peer）、`virtual-*`、`shadow-capacity`、`late-*`、`waiter-*`，共 35 项 | 原生续跑主驱动；CALL miss、PENDING、已完成控制 CALL、提前 A 解锁、资源/信号边界各有独立断言；不能只因共用脚本而去重 |
| `test_11_mutex_native_protocol.sh` | `mixed-mutex` | 目标与非目标线程共享同一 Linux mutex，包含 promotion 和节点不足回退；`mixed` 指参与者，不是 spin/mutex 混用 |
| `test_12_context_native_only.sh` / `test_24_gs_jit.sh` | `context-*` | GS read/write/RMW/current 为实际 JIT 正例；IRQ/BH、混合锁后端及多种线性 per-CPU 地址传播仍须拒绝 |
| `test_13_spin_shadow_capacity.sh` | 独立手动组件诊断 | 实际内核 full-shadow 队首路径，JIT=0；与 `shadow-capacity` 的 JIT 退出前缀及 PENDING 包检查不同，已不在套件中 |
| `test_14_spin_frame_depth.sh` | `node-physical-{1,2,8}-{0,1}`，共 6 项 | 物理 frame 链、继承的锁记录和 watermark；日常只选八层的两种配置，浅层点选 |
| `test_15_spin_native_gate.sh` | 独立手动组件诊断 | 真实原锁 L/私有队列 S 排斥与原生进度，JIT=0；不同于用户态替代原语，也不同于 gate 表满压力 |
| `test_16_spin_entry.sh` | 独立手动组件诊断 | 真实 ticket 容量、跨 CPU 通知、task pin 与保留 B，JIT=0；组件定位时保留 |
| `test_17_spin_native_protocol.sh` | `mixed-spin` | JIT 与非目标原生 spin API 的互斥、数据完整性；不能替代无 JIT 的确定性路由观测 |
| `test_18_spin_routing.sh` | 独立手动组件诊断 | promotion 前后、排队和改名时真实 hook 路由；刻意无翻译/JIT，已不在套件中 |
| `test_19_mutex_signals.sh` | `native-peer-1/3` | 被发信号的是非目标原生 mutex 竞争者；与原 waiter 接受信号的 `test_10` 不同 |
| `test_20_remote_outer.sh` | `mode-8` 的 `multi` / `multi quota` 阶段；其余为手动 JIT 诊断 | 两个 root 的完成/借用分支共用驱动；quota 以 ACK-drained B pop 观察 TID 脱离，不同于 `test_21` 的无锁 root finish；不能删除任一契约 |
| `test_21_remote_depth.sh` | `node-remote-plain`、`remote-late-2/3/4`、`remote-multi-b` | 四至八执行者、late-exit、多 deferred、跨 NUMA 与 TID 退出；不同释放状态分别验证 |
| `test_22_mutex_task_lifecycle.sh` | `kernel-task-local/cross-numa` | 实际 task 路由、RCU 读者延迟回收及最终 owner ACK，JIT=0；双 frame 完成不能替代 RCU 读者检查 |
| `test_23_mutex_parallel_native.sh` | `parallel-drain-0/1`、`parallel-shared-cpu`、`parallel-node-pressure` | 两个 frame 重叠、原 waiter 信号/退出后另一 frame 仍存活、代码/shadow 池、原生 peer、退休；同 CPU 分支是一个 frame 加另一个请求拒绝。保留两种 drain 顺序及合并压力项 |

`CASES` 直接引用 14 个脚本，`test_09` 再调用 `test_07/08`；另有 5 个独立手动入口。
因此不能用“未被 `CASES` 直接引用”判断脚本无用，也不能声称 `extended` 会运行
所有 shell 脚本或穷举所有环境参数。

## 4. 单元入口逐项分析

以下文件均在 `tests/unit/`。这里的“保留”表示有独立验证目的，后续按改动选择，
不表示每轮必跑。`*_fixture.c` 是相应 Python 驱动的编译输入，
`workload_modules/lock_scenarios/fragments/*` 是 Demo 临界区片段，
`tests/kernel/*` 是 provider 观察器/组件自测；均由模块 include，不另算独立入口。
完整文件对应关系见 [目录索引](PROJECT_GUIDE.md#59-单元测试-testsunit)。

### 4.1 两个 C 程序

| 文件 | 实际被测内容 | 重叠判断与处理建议 |
| --- | --- | --- |
| `test_control_call.c` | 直接调用生产 `kd_call.h`，阶段/错误组合、post-CALL 边界和不改栈 | 与高层 consumer 是 helper/集成关系；独立组合检查保留 |
| `test_daemon_policy.c` | 编译生产 daemon，结果缓存、分块 wire、fork/exec lease；可选真实子进程资源计量及 EINTR/时钟/资源失败 | 与翻译器设备会话测试覆盖不同端；计量默认关闭仍验证，真实 child 不是内核 JIT；保留 |

两项直接使用生产实现，不是复制公式的模型；各自的独立检查仍需保留。

### 4.2 翻译与生成代码：九个 Python 程序

| 文件 | 实际被测内容 | 重叠判断 |
| --- | --- | --- |
| `test_context_policy.py` | 完整准入入口、敏感符号/静态 per-CPU、CFG、CALL/RET 与上下文传播 | 与 memory/guards 共享语料；既有符号方法还对照旧 glob 检查合并正则的边界与克隆名，保留 |
| `test_context_memory.py` | byte/word、alias、partial store、RMW、合流/预算及 IR 接入 | 底层事实域的独立边界；复杂 CFG 正例不覆盖所有失败输入，保留 |
| `test_context_guards.py` | 有界 CALL/RET 范围与实际执行的入口谓词、拒绝时状态不变 | 生成机器码语义不同于静态准入结论；保留 |
| `test_context_spill_audit.py` | 独立 audit 的具体 witness、错误分类、无镜像拒绝条件 | 验证 audit 能发现错误，不等于运行整个 audit corpus；保留 |
| `test_hostcall_codegen.py` | 三个 manifest 服务的解析、精确目标/出口编号、不覆盖 RDI、未知 CALL/服务出口不弹虚拟返回地址 | 与生产 hostcall consumer 分属生成/消费两端，保留；缺失 miasm 不能记 SKIP 通过 |
| `test_segment_codegen.py` | GS lowering、logical task、FS/base 指令拒绝、双元素 wrapper 布局 | 通过实际 wrapper 和独立 origin storage 执行 GS 正例；FS/base 仍拒绝，保留 |
| `test_text_regions.py` | 跨文本窗口 CFG、读预算、lease/CAPS、设备身份和关闭 | 文本获取与会话边界不被普通上下文语料替代，保留 |
| `test_jit_diagnostics.py` | warning/error 定位、去重、flags/特殊指令现状及构建错误 | 验证诊断而非修复指令语义；其 helper 供其他单元复用，保留 |
| `test_jit_body_witness.py` | 实际 wrapper/body marker、dispatcher 负例、entry/lock 匹配日志 | 与 guards 共用用户态执行工具，但专测执行证据是否可信，保留 |

### 4.3 生产资源与控制流：十四个 Python 程序

这些程序提取或包含生产 C，通常以确定性原语替代锁、CPU、调度或 JIT body，
不是内核并发证明。代码提取 helper 的 import 不会运行提供方的 `main()`；
共享 helper 不是重复执行一遍提供方测试。

| 文件 | 实际被测内容 | 重叠判断 |
| --- | --- | --- |
| `test_exe_registry.py` | registry 探测、真实代码池、注册/上传设备边界；实际服务表的编译契约及计量重置/卸载 | 与 entry-scope 是发布者/执行消费者关系；服务 manifest/adapter 变化也须运行，保留 |
| `test_exec_capacity.py` | 生产 frame 分配/ledger/完成状态、完整包、容量及 remote/native 引用未排空的 pop 拒绝、两后端清理和 TID 退出观察器 | 已接替旧 frame 模型；实际 pop/观察器检查不同于真实 ACK/退出，链表、物理解锁、PID/RCU/time 仍为替代，保留 |
| `test_jit_entry_scope.py` | 生产入口/续点、远端准入/source 拒绝、typed hostcall allowlist、完整 RDI 参数/RAX 返回/共同额度，以及超额度 CALL 包的前进续跑与坏包拒绝；可选边界计时及开关前后完整 frame/包一致性 | 承接 CALL 模型的高层策略；wrapper/服务/时钟是替代原语，不能取代 guards 或真实服务数值验证，保留 |
| `test_source_lifetime.py` | source pin、设备能力、OPEN/retire、writer/frame 计数 | 与 source-depth 日志测试及 live 退休是不同层次，保留 |
| `test_hotlock_sampling.py` | 替代 TSC 下的生产采样：快/慢锁两种发现顺序、两个实际 producer 的交错更新、在途窗口、严格截止/样本数量、容量；四种策略变异 | 精确时间边界不被自然 promotion 成功覆盖，保留；旧生产实现被新断言拒绝，不新增单元入口 |
| `test_spin_gate.py` | 生产 gate/hold map、代际/原锁 owner；另测冷入口和已执行 JIT 的 gate-pressure 日志 | 后者要求独立 ENOMEM/CALL 包、双 frame、一次副作用与 ACK；与 entry/routing 共用实现但直接验证表和 owner 边界，保留 |
| `test_spin_entry.py` | 生产 ticket、origin 引用、task/CPU pins 的生命周期 | 与 gate 不同资源层，保留 |
| `test_spin_routing.py` | 生产 selector/hook 和获取分支，替代队列等待 | 入口分流不同于 ticket 分配或 combiner 执行，保留 |
| `test_spin_shadow.py` | 生产队首、combiner、native/virtual node producer、取消与嵌套返回 | 已覆盖被删除的节点计数模型；保留此生产测试 |
| `test_spin_outer_progress.py` | 生产 batch/frame/ticket、提前 outer-release、frame 池拒绝、真实 gate 满表 ENOMEM 的完整包不变，以及 release 前的包和唤醒后槽复用 | gate 失败由真实 nested producer 产生、PENDING helper 恢复 callee/SP；与 shadow 队首部分交叉，但保留 frame/原锁和发布边界；不证明实际 JIT 或硬件内存序 |
| `test_remote_outer.py` | 生产远端祖先解锁/native ACK，完整 168 字节寄存器包、CALL 返回字和 DONE 后父 frame 复用；两后端 native wait 计量开关、错误返回及多层区间重叠；含十一种故障变异 | 本地 outer 验证 node 发布，本项验证跨执行者关系，protocol 单元验证坏日志；三者不能互相替代。CPU/发布/时钟观察为替代，不证明硬件 flags/并发 |
| `test_mutex_resources.py` | 生产 tail 编解码、node mask、shadow 表、hook/selector、完整 slowpath 包、改名/关闭准入路由 | 接替 mutex/tail 模型；per-CPU 存储和 task 引用仍为替代原语，保留资源边界与故障变异 |
| `test_mutex_outer_progress.py` | 生产 mutex executor/combiner/outer-event、owner 保留和后继进度；真实日志宏的 INFO/格式/次数，以及 ALERT/关闭日志两个变异 | 与 spin outer 是不同后端；提供被删除 mutex 模型的生产控制流检查。仅替代 printk sink，不证明串口或调度成本；定向结果见 [日志验收](VALIDATION.md#mutex-routine-log-severity) |
| `test_native_after_outer.py` | 生产 native/control CALL、mutex B 获取/解锁、提前 A、栈变化、已获取 spin 续点；附 acquired oracle | 与 combiner 是事件生产者/消费者关系；原生 B 等待替代，CALL 阶段与拒绝不变性保留 |

### 4.4 观察器与证据：十五个 Python 程序

多数程序构造或修改日志，要求判定器拒绝缺失、重复、错 owner、错时间顺序等
证据。复杂 live 正例只能证明它接受某份正确记录，不能证明它会拒绝伪造记录。

| 文件 | 实际被测内容 | 重叠判断 |
| --- | --- | --- |
| `test_native_registers.py` | 实际用户态汇编 probe/checker 与 GPR/SP/IP、native-control 负例 | 寄存器样本不同于普通 workload 计数，保留 |
| `test_mutex_signal_protocol.py` | 发布等待、mode 4 同 CPU 调度及两 A/共享原生 B、mode 5 CALL 额度/ACK、native peer/原 waiter 的信号及竞争日志 | 正常 JIT 返回、共享 B 混合完成、额度 native 后缀、PENDING 和信号退出各有独立顺序/计数契约；复用一个入口，不以警告或总计数替代完整证据，保留 |
| `test_mutex_stack_protocol.py` | 真实栈变化、post-control 包、entry/镜像/owner 的日志判定 | 不被 PENDING 或普通 miss 日志覆盖，保留 |
| `test_native_ooo_protocol.py` | 两后端 A-before-B、副作用、owner/ACK 和原生依赖日志 | 与远端祖先的 RPC 作用域不同，保留 |
| `test_remote_outer_protocol.py` | 两/三执行者祖先释放、owner 依赖、RPC 和 placement；两个独立 root 的逐请求/JIT/副作用日志 | 深链不替代独立 logical task 隔离；坏日志与真实执行分层，复用同一程序 |
| `test_remote_depth_protocol.py` | 深链/refusal/readmission/TID 退出日志；实际等待谓词/观察器 | 与 outer 是不同驱动契约；保留 |
| `test_remote_deferred_protocol.py` | 多 deferred、取消与接链顺序；实际选队和 trace | 深度大并不自动覆盖 deferred 选队规则；保留 |
| `test_spin_frame_protocol.py` | 物理 frame、watermark、held/PENDING refusal、与 deferred 的组合记录 | frame 级身份与 stack 状态不同于 node 计数；保留 |
| `test_spin_node_protocol.py` | reservation/drain、CPU 覆盖、profile 及坏计数 | 与真实 producer 是观察结果的判定层；保留 |
| `test_source_depth_protocol.py` | 两模块学习、loader ref/source pin、逐波 body 与终态日志 | live/生产 source 状态机不能替代引用归因判定；保留 |
| `test_mutex_parallel_protocol.py` | 双 frame 重叠/退出顺序、单 frame 拒绝、池压力、peer 信号重排、退休；实际客户端 peer 两次 ioctl、原 waiter 一次 ioctl | 与单 frame 信号检查部分交叉，但独立队列的 owner/ACK/存活区间不能删；保留 |
| `test_cs_oracle.py` | 生产 workload 状态更新/完整性函数及损坏输入 | live 调用同一 oracle；单元防止 oracle 自身失效，保留 |
| `test_benchmark.py` | 实际 pthread ioctl 驱动的计时/失败协议，及配对控制器的阶段、翻译/可选十项 JIT/native/队列计量、控制台、身份、顺序与部分失败契约 | 30 个生产驱动场景及 113 个配对观测检查；替代设备、时钟或日志，另含真实 guest 时钟路径；不执行内核 workload，不是实际 JIT 证明 |
| `test_kernel_baseline.py` | 只读基线验证器的身份、哈希、路径和归档损坏输入 | 验证器负例，与检查当前 guest 身份不同，保留 |
| `test_regression.py` | 选择去重、停止边界、归档（含依赖配方而不含任意生成文本）、环境采集和离线 verifier；显式计量的直接/组合装载、原超时及错误选择检查 | 验证运行器，装载原语为替代，不证明 JIT；这些控制层断言保留 |

## 5. 哪些可以精简

### 5.1 已生效的 Live 去重

已审核替代关系集中在
[`COVERED_DIAGNOSTICS`](../tests/regression.py)，具体规则和边界统一维护在
[合并与保留](JIT_EXECUTION.md#合并与保留)。`--list` 可查看当前 11 对关系。
它们包括 mode 0/1/3、相同配置的一/二层物理 frame、简单 shared-CPU、
普通 stage-3 native 和较简单的 PENDING 诊断。所有套件均排除这些诊断，
显式 `--case` 仍可用于定位。

`core` 是 `spin` 与 `mutex` 的并集；`hostcall` 重用 mode 2/5；
`mutex-parallel` 的三项也包含在 `mutex-native` 中。
一次命令选择多个 suite 时取并集，另起多个命令则会再次运行相同 case。
所有套件的并集为 69 项，仍不含 11 项显式诊断；这与 80 项完整目录并不矛盾。
不能先运行 `core`，再把 `spin`、`mutex`、`hostcall` 当成额外独立覆盖全跑一遍。

### 5.2 单元精简进展与顺序

已删除 `test_spin_node_count.c`、其 Makefile 入口和生成物忽略项。
原来的三个断言组分别对应到
[`spin_node_pool_fixture.c`](../tests/unit/spin/spin_node_pool_fixture.c) 的
`producer_path_case()` / `producer_live_prefix()` / `run_producer_cases()`：

| 模型行为 | 已有生产测试依据 |
| --- | --- |
| nested 节点满后计数不泄漏 | `count == MAX_NODES` 的 virtual 路径返回 `-E2BIG`，不发布节点，并比较原计数/存活前缀 |
| native 节点满后直接等待且计数不变 | 同容量下真实 slowpath 走 native fallback，检查等待次数、未创建节点和原计数 |
| 释放后容量可复用 | 未满时获取/返回后恢复原计数，各占用深度反复检查；更广路径覆盖 native/virtual producer |

生产函数由 `test_spin_shadow.py` 从 `kd_spinlock.c` 提取；fixture 的锁/CPU/peer
仍是替代原语，不能据此声称 Linux 并发已经通过。精简后在 guest 运行
`python3 tests/unit/run.py spin/test_spin_shadow.py --mutations`：生产路径的 NUMA off/on
配置通过，九种故障变异全部被拒绝。该参数只改临时提取副本，不修改生产源文件。
源码身份、命令与日志见 [本次验证](VALIDATION.md#redundant-node-model-removal)，
未因此重复其他单元或 live 矩阵。

随后删除 `test_mutex_transition.c`、其 Makefile 入口和生成物忽略项；
不新增单元入口，扩展已有的 `test_mutex_resources.py` 和 fixture：

| 原模型契约 | 生产测试中的对应检查 |
| --- | --- |
| promotion 不绕过原生 owner | `check_promotion_and_routing()` 跨越冷锁 promotion，并让原生 peer 先持有 L；真实 hook 必须调用原生获取，再发布自己的 owner |
| 借用执行不转移原生 owner | `check_slowpath_packets()` 保留 peer 的 A，waiter 仅拥有自己的 C，借用 A 的 unlock 必须经过通知；combiner 的五种场景检查 retained owner |
| 改名后仍能解锁 | 从 `kd_main.c` 提取实际 `__is_kd_mutex_task()`；原 owner 和 borrower 改名且 source 关闭后仍路由，最后一个替代 task 引用释放后停止路由 |
| 私有队列交接不转移原生 owner | 两次目标获取之间由原生 peer 先持有 L，生产获取路径必须等待其释放，不能仅凭取得 S 当作已持有 L |

guest 定向运行资源与 outer-progress 两个程序通过，资源测试的十一种故障变异
均被检测，包括新增的丢失 retained-task 路由、绕过 source 关闭和绕过借用解锁通知。
物理锁、task 引用与 ACK 在该 fixture 中仍是替代实现，不证明 Linux 排队或 RCU；
既有 live 及 `kernel-task-*` 检查继续保留。证据见
[mutex 模型精简](VALIDATION.md#redundant-mutex-model-removal)。

第三步删除 `test_exec_frame.c`、入口和生成物忽略项，扩展现有
`test_exec_capacity.py` / `exec_capacity_fixture.c`，不新增程序。原 11 项对应如下：

| 原模型检查 | 当前生产测试依据 |
| --- | --- |
| `frame_parent_and_lifo` | `exercise()` 在实际八层容量内逐深度检查 parent、LIFO、完整寄存器和归还后存储清零 |
| `live_context_rejects_foreign_task` | 异 task push/pop 拒绝，完整 context、输出包及 source 引用不变 |
| `lock_stack_is_dense_and_ooo_pop_is_tracked` | `ledger()` 检查非末尾 nested pop 同步移动地址/kind/node/released，移除祖先时调整 outer index；A 提前释放由下一项保留记录 |
| `outer_unlock_is_required_and_exactly_once` | `completion()` 拒绝缺失/错误/重复 outer 事件，outer callback 只执行一次 |
| `deep_nested_ooo_release_waits_for_inner_locks` | A 已释放仍保留 ledger；B/C 或远端 WAITING/NATIVE 未结束时禁止完成 |
| `repeated_acquisition_is_rejected` | 真实 push 和初始 ledger 拒绝重复地址，不改完整 context |
| `lock_stack_capacity_fails_closed` | 真实八项 ledger 接受，第九项返回 E2BIG 且不改原记录 |
| `invalid_initial_stack_does_not_mutate_frame` | 缺失 outer、重复/零地址、非法 kind、空输入和超限均检查错误码及不变性 |
| `error_path_can_pop_without_completion` | abort 只改状态；物理 LIFO、task、远端依赖和 native 请求/路由仍限制 pop，拒绝不改输出包或引用 |
| `abort_releases_only_nested_locks_in_reverse_order` | `cleanup()` 直接提取两后端 helper，八种配置检查逆序、已释放项不二次 unlock、原 A 保留及 mutex kind/node 拒绝 |
| `gs_context_is_inherited_and_args_remain_two_words` | GS/task 继承由上一轮已验证且未修改的实际 node producer 覆盖；当前 allocator 检查完整输入，entry-scope/segment 检查实际高层双元素参数和生成器布局 |

旧模型允许把 A 从仍有 B/C 的 ledger 删除，这不是当前协议。现有生产路径使用
`mark_released` 保留 A，不能把旧模型的成功结果当作该操作的支持依据。
清理 helper 的直接测试没有 JIT body；后端仍禁止用它回滚或重跑已经执行的临界区。
guest 定向运行 frame、entry-scope、segment 三个程序通过，frame 的十二种故障
变异均以断言失败被检测。证据见
[frame 模型精简](VALIDATION.md#frame-model-consolidation)，未重复其他单元或 live。

之后在同一入口补充 native 请求、路由及两者同时残留的终态回收负例：旧生产
pop 接受坏终态并提前改包/释放引用，定向单元拒绝该行为；增加回收门禁后，
两个后端的 ERROR/COMPLETE 组合和两种新增 guard 变异通过检查，共十四种变异。
正常 ACK 的发生与路由生命周期仍由独立 protocol/live 验证，不用这个替代环境
宣称实际并发 UAF 已复现。执行流和选择见 [Frame 回收门禁](JIT_EXECUTION.md#frame-回收门禁)。

第四步删除 `test_jit_call_policy.c`、入口和生成物忽略项。扩展已有 entry-scope
和 native-after-outer 程序，不新增入口，七项原模型检查对应如下：

| 原模型检查 | 当前生产测试依据 |
| --- | --- |
| `outer_unlock_completes` | `check_mutex_call_pair()` 调用实际 dispatcher，最终 outer 完成不提前消费 CALL；entry-scope 检查高层结果 |
| `inner_lock_and_unlock_continue` | 实际 nested-lock producer 先获取 B、发布 NATIVE ledger，再消费 CALL；解锁后移除 B，完整 GPR 包保留 |
| `contended_inner_lock_resumes_after_remote_unlock` | 旧假设已失效，不保留远端 B 的成功模型；当前在替代原生 peer 等待后由同一 A executor 获取 B，从 lock 后继继续，见 DESIGN 5.3 |
| `api_hostcall_continues` | 实际 manifest、类型适配器、dispatcher 与 CALL advance；两个时钟和标量服务由替代原语返回，检查完整 RDI 参数/RAX、其他 GPR、栈及重新进入 wrapper 的双元素输入；数值计算仍由 live 检查 |
| `unknown_hostcall_is_rejected_without_stack_change` | 未知/未解析地址和全部安全属性组合；高层区分拒绝、invoke 失败和坏返回包，不授权入口重跑 |
| `unknown_call_preserves_native_continuation` | 普通及 allowlist 内目标的 CALL_MISS 都保留完整原生 CALL 包，不调用服务、不返回本次 JIT |
| `hostcall_continuation_is_bounded` | 服务和已知控制 CALL 共用额度；不分派超额 callee，受检包转交 waiter，坏包仍 fail-stop；检查无弹栈/重放/学习、完整包与源驻留调用 |

首轮 native-after-outer 和 hostcall-codegen 通过，entry-scope 的坏包构造失败：
SP 在入口前置零，实际触发了入口拒绝。修正为模拟 wrapper 返回坏包后，只重跑
entry-scope，823 项检查及六种故障变异通过；两个已通过程序的源码未受此修正影响，
其结果仍记为首轮证据，不合写成同一冻结版本的全量通过。详细日志见
[CALL 模型精简](VALIDATION.md#call-model-consolidation)。没有内核 JIT 重跑。

第五步删除 `test_tail_encoding.c`、入口和生成物忽略项，将检查迁入现有
`test_mutex_resources.py` / `mutex_resources_fixture.c`。直接提取 `kd_mutex.c`
的 encoder 和 decoder，只替代 `per_cpu_ptr` 存储，使用不同 CPU/slot 的独立地址。
同时检查实际 slowpath 生成的 `node->tail` 能解回原节点，不再复制字段解码公式。

| 原模型检查 | 当前生产测试依据 |
| --- | --- |
| `encode_decode_cpu0_idx0` | 固定 wire 值 `0x10`，实际 decoder 返回 CPU 0/slot 0 的节点 |
| `encode_decode_cpu7_idx3` | 固定 wire 值 `0x8c`，实际 decoder 返回 CPU 7/slot 3 的节点 |
| `encode_decode_cpu39_idx2` | 固定 wire 值 `0x288`，实际 decoder 返回 CPU 39/slot 2 的节点 |
| `encode_nonzero` | CPU 0-39、每 CPU 四槽的 160 个生产编码全部非零；不把空队列的零哨兵传给 decoder |
| `different_cpus_different_tails` | 160 个编码严格递增且往返到各自节点，保留低两位不影响节点选择的检查 |

仅供旧模型使用的 `mock_kernel.h` / `test_harness.h` 已无引用，一并删除并移除
Makefile 中的依赖；历史 hash/hotlock 模型的无效忽略项也已清理。
guest 强制重建并运行剩余两个 C 程序及 mutex 资源程序，3/3 通过；资源测试
16,768 项检查和 16 种故障变异通过，包括五种新增的 CPU/slot/零哨兵错误。
证据见 [tail 模型精简](VALIDATION.md#tail-model-consolidation)。这是有限的 mutex
编解码输入，不代表 spin 编码、Linux per-CPU 并发或内核 JIT 验收，未重复 live。

### 5.3 相似但不能互相替代

| 相似用例 | 必须保留的区别 |
| --- | --- |
| mode 4 / mode 5 | 嵌套 B 竞争与 hostcall 返回 JIT，不同控制路径 |
| mode 6 / 八层 physical frame | 同一 frame 三把锁与多个 frame 的继承容量，不同 ledger 结构 |
| `shadow-capacity` / frame-depth | local shadow 容量与继承锁记录的逻辑深度，不同拒绝点 |
| `native-4-4` / `parallel-node-pressure` | 同队列同 CPU 的续跑进度与跨队列同 CPU 的准入拒绝 |
| `parallel-drain-0` / `parallel-drain-1` | 先完成不同 frame，检查剩余 frame 的 owner/ACK 独立性 |
| `native-spin-acquired` / PENDING refusal | 已实际获取 B 后的 post-CALL 状态与尚未获取 B 的 CALL-entry 状态 |
| `waiter-interruptible/killable` / `waiter-race-*` | 强制取消要求最终 A ACK 后 B owner 仍持锁；释放竞争允许 B 更早释放 |
| `waiter-*` / `native-peer-*` | 被发信号的是借用锁执行的原 waiter，或外部 Linux mutex 竞争者 |
| `kernel-task-*` / `parallel-*` | 活跃 RCU 读者阻止回收，或 native frame/owner 存活；TID 退出不等于回收 |
| mode 8 quota / `remote-late-3` | 同一 B combiner 在旧 waiter 退出后代理另一 root，或无锁祖先等待一个 child；暂停点分别为已发 ACK 的 pop 与无需 ACK 的 finish |
| codegen / 生产 C fixture / live / 日志变异 | 分别检查生成结果、控制决策、实际并发执行、错误证据拒绝；不能用某一层的正例替代其他层 |

## 6. 辅助文件与后续运行

`common.sh` 是共享驱动函数，不是独立用例。`*_protocol.py` 包含判定器和
控制器，部分会访问 sysfs、控制真实客户端，不能全部当成只读脚本执行。
`regression_evidence.py` / `verify_evidence.py` 分别采集证据和离线校验；
`audit_context_spills.py` 是独立准入审计；`audit_spin_native.py` 是保留旧假设的
历史审计，不作当前协议的日常通过门槛。
各文件用途只维护在 [控制器与 oracle 索引](PROJECT_GUIDE.md#57-测试控制器和-oracle)。

后续运行按 [选择范围](JIT_EXECUTION.md#选择范围) 选择受影响单元和复杂 live；
首次环境验收才按 [手动指南](PROJECT_GUIDE.md#3-一步一步运行) 做完整准备。
只改本文的目录/分析时检查文件清单、命令预览和文档链接，不运行 JIT。
只改选择规则时运行 `test_regression.py`；改 workload/oracle 时选对应单元与
受影响 live。每次运行后的归档、退出码、drain 和离线校验统一查
[执行与证据](JIT_EXECUTION.md#执行与证据)，不把历史 PASS 记为本次运行。
