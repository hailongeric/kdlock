# 代码与文档索引

按职责定位当前源文件；主执行链和手动环境步骤见
[项目指南](PROJECT_GUIDE.md)。私有 `.inc` 保持原编译单元，Python 组件通过
显式接口组合。测试入口与 case/fixture 分开，列表不表示全量必跑。

拆分以职责和依赖为界：符号解析、值分析、CFG 准入彼此分开；C 私有组件仍由
原编译单元包含。薄转发层和仅改 ABI 参数的测试入口合并。独立协议 oracle、
真实汇编夹具及 owner/ACK 状态不因文件小而合并，也不按行数机械切开同一测试
场景。TCLock upstream 和捕获的内核基线保持原字节，便于核对上游及恢复。
设计/测试专题保留原章节编号和锚点，方便追溯旧引用。

## 5. 完整目录与文件索引

以下覆盖当前维护的源码、脚本、构建入口和基线材料。生成文件按[项目指南第 4 节](PROJECT_GUIDE.md#4-产物与参数怎么读)分类，不逐个
列入源码清单。脚本编号有空缺是整理后的结果，不要恢复旧的重复 smoke 文件。

### 5.1 顶层与文档

| 文件/目录 | 用途 |
| --- | --- |
| [README.md](../README.md) | 项目 idea、状态、快速入口和限制摘要。 |
| [.gitignore](../.gitignore) / [.gitattributes](../.gitattributes) | 生成物排除规则和基线证据的窄格式例外。 |
| `.git/` | Git 元数据，不手工清理；仅按用户要求提交。 |
| `.agents/`、`.codex/` | 工作区工具配置，非 guest 运行输入，不搬入 VM。 |
| [AGENTS.md](AGENTS.md) | 操作安全边界、恢复和验证约定。 |
| [DESIGN.md](DESIGN.md) | 原锁/队列、frame、source、hostcall、续跑协议。 |
| [JIT_REGISTER_ABI.md](JIT_REGISTER_ABI.md) | 两参数、GPR/栈槽、退出和待实现的访问时契约。 |
| [JIT_EXECUTION.md](JIT_EXECUTION.md) | JIT 范围、复杂测试执行流、增量选择。 |
| [TODO.md](TODO.md) | 当前待办、已知失败、可选扩展与明确延期；完成日志转查历史证据。 |
| [VALIDATION.md](VALIDATION.md) | 历史结果的时间、源码冻结与归档索引；新增测试/benchmark 结果维护在各自目录 README。 |
| [PROJECT_GUIDE.md](PROJECT_GUIDE.md) | 主执行链、逐步操作和阅读顺序。 |
| [CODE_MAP.md](CODE_MAP.md) | 本文：组件及文件索引。 |
| [PERFORMANCE_PLAN.md](PERFORMANCE_PLAN.md) | 下一阶段性能任务、依据、实验及停止条件。 |
| [design/](design/) | 生命周期、锁协议、准入、frame 的单一详细契约。 |
| [testing/](testing/) | 入口准入及 spin/mutex/native 专门协议的角色、命令和 oracle。 |

### 5.2 生产模块 `kernel_module/`

| 文件 | 阅读用途 |
| --- | --- |
| [Makefile](../kernel_module/Makefile) | provider 对象组成、SELFTEST/NUMA 开关、guest Kbuild。 |
| [kd_main.c](../kernel_module/kd_main.c) | 初始化/逆序退出，spin int3 selector、mutex 无条件分派与 hook 发布。 |
| [kd_lock.c](../kernel_module/kd_lock.c) | hook 路由、原生操作适配、mutex shadow 查找。 |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | CPU 与单锁均本地识别，每 10240 次共用一次时间检查；仅达标地址进入共享集合，尚不代表 JIT 就绪。 |
| [sys.c](../kernel_module/sys.c) | 设备 open/read/write/ioctl、CAPS、退休协议。 |
| [exe.c](../kernel_module/exe.c) | RIP 注册、代码池、wrapper 退出分派、控制/服务处理；默认关闭的 `jit_timing` 只读装载开关及排空后边界统计。 |
| [kd_exec.c](../kernel_module/kd_exec.c) | frame/锁 ledger、远端关系、native 请求与 owner ACK；pop 拒绝未排空的 remote/native 引用。 |
| [kd_source.c](../kernel_module/kd_source.c) | source pin、writer/frame lease、终止式退休。 |
| [kd_spinlock.c](../kernel_module/kd_spinlock.c) | spin 排队、嵌套代理、IRQ 保存/恢复与非局部恢复桩；combiner 使用 task 栈，物理 waiter 使用每 CPU shadow 等待栈。 |
| [spin/request.inc](../kernel_module/spin/request.inc) | 独立于 node 的预分配 request 槽领取和最后用户归还。 |
| [spin/combiner.inc](../kernel_module/spin/combiner.inc) | 新旧及混合 ABI 的统一批次循环，完成/pop/发布、后继准入。 |
| [spin/execute.inc](../kernel_module/spin/execute.inc) | 复杂出口消费、native/remote 与原 owner/ACK；在原编译单元包含。 |
| [execution/wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc) | 入口范围、ABI/镜像、body witness 与批次准入。 |
| [execution/frame_lifecycle.inc](../kernel_module/execution/frame_lifecycle.inc) | frame 准备/绑定/push/pop 和普通完成/退休。 |
| [spin/wait.inc](../kernel_module/spin/wait.inc) | 物理 waiter 连续汇编切入 shadow 栈再发布/轮询；未执行的队首恢复旧 RSP，完成或 native 唤醒放弃旧 C 帧并转入 task 栈的安全位置恢复。 |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c) | origin ticket、代际、task/CPU 引用与借用生命周期。 |
| [kd_mutex.c](../kernel_module/kd_mutex.c) | mutex 节点池、combiner、原生 owner、waiter 续跑；正常 queue/JIT 日志保留为 INFO。 |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | acquisition task 引用、rename 后路由及 RCU 回收。 |

### 5.3 共享接口 `include/`

| 文件 | 阅读用途 |
| --- | --- |
| [exe_info.h](../include/exe_info.h) | daemon/kernel 共用 entry、状态、代码块和上传布局。 |
| [exe.h](../include/exe.h) | C 执行器接口及返回值；区别于 wire/wrapper 状态。 |
| [kd_jit_batch.h](../include/kd_jit_batch.h) | 版本化 wrapper 目录、最小入口描述及新旧编译器 clobber 调用边界。 |
| [kd_exec.h](../include/kd_exec.h) | frame、ledger、远端状态及不变量辅助 API。 |
| [kd_call.h](../include/kd_call.h) | PENDING/已完成控制 CALL 的目标、SP、返回 token 校验。 |
| [kd_lock.h](../include/kd_lock.h) | hook 和原生锁辅助声明。 |
| [kd_hotlock.h](../include/kd_hotlock.h) | 本地采样准入与已晋升身份查询接口；计数/窗口不暴露为共享状态。 |
| [kd_mutex.h](../include/kd_mutex.h) | 私有 mutex gate/node 布局和容量。 |
| [kd_spinlock.h](../include/kd_spinlock.h) | spin node/队列与 JIT 上下文布局。 |
| [kd_spin_entry.h](../include/kd_spin_entry.h) | hook/virtual ticket 与 origin ref。 |
| [kd_spin_fast.h](../include/kd_spin_fast.h) | 可关闭的原生站点缓存与独立 S/L hold；匹配缓存不重复查询，保留解锁/退休约束。 |
| [kd_comm.h](../include/kd_comm.h) | 装载时准备的完整 task comm 掩码匹配，保留 NUL/超长名字语义。 |
| [qspinlock_i.h](../include/qspinlock_i.h) | 私有调度字的 qspinlock 风格位布局/辅助宏。 |
| [kd_segment.h](../include/kd_segment.h) | 在 origin CPU 记录 kernel GS base。 |
| [kd_source.h](../include/kd_source.h) | source 生命周期内部接口。 |
| [kd_source_api.h](../include/kd_source_api.h) | source/CAPS ioctl 常量和固定布局。 |
| [kd_hostcall.h](../include/kd_hostcall.h) | 服务 ID 和安全属性定义。 |
| [kd_hostcalls.def](../include/kd_hostcalls.def) | 唯一服务清单：两个 ktime 服务及标量 int_sqrt，不支持任意 printk 或指针服务。 |
| [asm_head.h](../include/asm_head.h) | pt_regs 共享 GPR backing 与 wrapper 独立控制槽的汇编偏移；R11 为包基址。 |
| [wrapper.S](../include/wrapper.S) | 装载/回写寄存器，包含生成的 jit.S；flags 不持久化。 |
| [sys.h](../include/sys.h) | 设备初始化/退出接口。 |
| [utils.h](../include/utils.h) | 日志辅助，不是成功判定器。 |

### 5.4 翻译器 `disassem/`

| 文件 | 阅读用途 |
| --- | --- |
| [requirements.txt](../disassem/requirements.txt) | CPython 3.10 翻译器与证据读取器的固定运行包版本；3.3 维护唯一安装步骤，不锁定完整工具链。 |
| [disassem.py](../disassem/disassem.py) | CLI 和翻译总流程；解码、准入、发射、组装。 |
| [device_session.py](../disassem/device_session.py) | lease/source pin/CAPS；可直接执行 status/capabilities/retire。 |
| [memread.py](../disassem/memread.py) | 从 kcore 的 ELF 映射读取固定窗口和冷分支。 |
| [entry_abi.py](../disassem/entry_abi.py) | 普通 spin/mutex clobber 入口的有界未定义位分析，拒绝观察未捕获的初始 GPR。 |
| [context_policy.py](../disassem/context_policy.py) | 对外准入接口、CFG/JIT 范围、数据流求解与锁深度；显式重导出兼容接口。 |
| [context_symbols.py](../disassem/context_symbols.py) | 敏感符号、控制目标及静态 per-CPU 范围加载。 |
| [context_values.py](../disassem/context_values.py) | 寄存器常量、抽象值传播和上下文引用分析；预算耗尽仍拒绝。 |
| [context_memory.py](../disassem/context_memory.py) | 有界顺序 byte/word 事实、别名、clobber；不是实时内存快照。 |
| [context_guards.py](../disassem/context_guards.py) | 正文前的入口 disjointness 条件，不是访问时 guard。 |
| [normal.py](../disassem/normal.py) | 普通 operand、地址和寄存器映射。 |
| [special_inst.py](../disassem/special_inst.py) | 单条指令分派及 CALL/RET/虚拟 PUSH/POP/控制指令；已合并原 translation.py 的薄转发层。 |
| [conflict.py](../disassem/conflict.py) | 虚拟特殊寄存器到物理 scratch/spill 的映射。 |
| [indirect_jump.py](../disassem/indirect_jump.py) | 有界返回图与 learned IJ 分发表。 |
| [hostcall.py](../disassem/hostcall.py) | 读取共享清单并产生服务出口。 |
| [assist.py](../disassem/assist.py) | 指令名、branch 分类、operand/汇编格式辅助。 |
| [miasm_compat.py](../disassem/miasm_compat.py) | 已支持 miasm 表达式接口差异的适配。 |
| [solve_bug.py](../disassem/solve_bug.py) | LEA 解码和 LOCK 相关输出的局部修正，不是通用语义保证。 |
| [diagnostics.py](../disassem/diagnostics.py) | 每次翻译的定位、分级和去重日志。 |

### 5.5 桥接、负载与基线

`workload_modules/` 统一保存 test/bench 的 Demo 内核临界区模块。
`lock_scenarios/` 承接原 `klock_module/` 及其临界区片段，`spin_cacheline/`
保存 cacheline microbenchmark 驱动。模块名 `klock_module`、`kd_depth_source`、
`spin_cacheline` 以及设备/ioctl 接口保持原样；目录命名表达负载集合的职责。
用户态客户端和扫描入口仍在 `bench/`，协议与回归入口仍在 `tests/`。

```text
workload_modules/
  Makefile                          构建全部 Demo 模块
  lock_scenarios/
    Makefile, klock_module.c         多模式测试/benchmark 负载
    kd_depth_source.c, .h           可选第二源码模块
    fragments/                      被模块 include 的临界区片段
  spin_cacheline/
    Makefile, module.c               独立 spin cacheline 负载
    payload.h, api.h                 展开临界区及共享 ioctl 定义
```

在 recovery guest 构建生产 provider 后，可用 `make -C workload_modules W=1`
构建两组负载；只需一组时使用 `make -C workload_modules lock_scenarios`
或 `make -C workload_modules spin_cacheline`。后者不依赖 kdlock 符号。
原测试脚本通过 `KLOCK_DIR` 使用新的 `lock_scenarios/` 路径；cacheline 的
`make -C bench/spin_cacheline module` 会委托给新的负载目录。

| 文件 | 使用方式 |
| --- | --- |
| [daemon/daemon.c](../daemon/daemon.c) | 唯一常驻用户态桥接进程、CLI 和轮询调度。 |
| [workspace.inc](../daemon/workspace.inc) / [compiler.inc](../daemon/compiler.inc) / [publication.inc](../daemon/publication.inc) | 同一 C 编译单元内的工作区/学习缓存、子进程编译与可选计量、ABI 校验及发布。 |
| [daemon/Makefile](../daemon/Makefile) / [README](../daemon/README.md) | daemon 构建、参数、会话和诊断说明。 |
| [bench/klock_test.c](../bench/klock_test.c) | pthread ioctl 驱动及可选结构化测量，参数含义见[负载说明](../bench/lock_scenarios/README.md)。 |
| [bench/README.md](../bench/README.md) | benchmark 总入口；具体伪代码、运行命令与结果维护在各负载的子目录 README。 |
| [tclock_backend/README.md](../tclock_backend/README.md) | 独立 TCLock 原生后端：上游来源、完整栈切换逻辑、hook 与验收边界。 |
| [tclock_compare/README.md](../bench/tclock_compare/README.md) | 同负载三方六臂交替矩阵、采样、计时外 allocator guard、冻结输入与结果。 |
| [spin_cacheline/README.md](../bench/spin_cacheline/README.md) / [Makefile](../bench/spin_cacheline/Makefile) | 独立 cacheline 对比的构建、参数化扫描、临界区与测试伪代码、结果解释、汇编查看及排空入口。 |
| [spin_cacheline/EXECUTION_PATHS.md](../bench/spin_cacheline/EXECUTION_PATHS.md) | 首次发现/注册、原生快路径、队列代理、JIT wrapper 与恢复的源码伪代码，以及按路径区分的性能检查点。 |
| [workload_modules/Makefile](../workload_modules/Makefile) | Demo 模块统一构建入口，可分别选择 lock_scenarios 或 spin_cacheline。 |
| [spin_cacheline/Makefile](../workload_modules/spin_cacheline/Makefile) / [module.c](../workload_modules/spin_cacheline/module.c) / [payload.h](../workload_modules/spin_cacheline/payload.h) / [api.h](../workload_modules/spin_cacheline/api.h) | 不依赖 kdlock 符号的外部模块，64B 数据槽、五种展开 CS、布局/run/排空计数 ioctl。 |
| [post_work.h](../workload_modules/spin_cacheline/post_work.h) / [post_work_fixture.c](../bench/spin_cacheline/post_work_fixture.c) | 正文返回后的固定寄存器乘加及其编译产物检查；负载定义见 benchmark README。 |
| [provider/prepare.py](../bench/spin_cacheline/provider/prepare.py) / [observation.patch](../bench/spin_cacheline/provider/observation.patch) | 在 bench 私有副本应用观测层并构建 kdlock；严格检查补丁上下文，冻结原始/最终输入哈希，主项目源码和产物不被覆盖。 |
| [provider/kd_bench.c](../bench/spin_cacheline/provider/kd_bench.c) / [kd_bench.h](../bench/spin_cacheline/provider/kd_bench.h) | 只加入 benchmark 专用 provider 的默认关闭 quiet 与锁地址选择，wrapper 返回后的 per-CPU 正文计数和只读排空查询。 |
| [client.c](../bench/spin_cacheline/client.c) | 逐线程绑核、原子 ready/go/abort 起跑、单 ioctl 循环、wall/线程 CPU 汇总及全部数据槽差值检查。 |
| [run.py](../bench/spin_cacheline/run.py) / [summarize.py](../bench/spin_cacheline/summarize.py) | 扫描入口、有效会话选择、kdlock 最佳吞吐/原生中位数及完整配对 CSV。 |
| [bench_runtime.py](../bench/spin_cacheline/bench_runtime.py) / [bench_session.py](../bench/spin_cacheline/bench_session.py) | 计划/环境/数据检查，以及单会话的准备、发布确认、测量和排空。 |
| [assembly.py](../bench/spin_cacheline/assembly.py) / [test_assembly.py](../bench/spin_cacheline/test_assembly.py) | 排空后按临界区及文件内容去重导出原生/JIT 汇编，生成查看索引并核对来源。 |
| [dispatch_floor/Makefile](../bench/spin_cacheline/dispatch_floor/Makefile) / [module.c](../bench/spin_cacheline/dispatch_floor/module.c) / [run.py](../bench/spin_cacheline/dispatch_floor/run.py) | 独立原生 selector/最小 callback 调用成本对照；复用实际负载和数据/排空检查，不计作 kdlock/JIT 成绩。 |
| [kernel_identity.py](../bench/spin_cacheline/kernel_identity.py) | 默认核验 clobber 独立基线；显式选择也须验证配置/源码/build/live 身份。 |
| [profile.py](../bench/spin_cacheline/profile.py) / [profile_summary.py](../bench/spin_cacheline/profile_summary.py) | 独立低频内核 IP 采样及只读离线 period 加权汇总；复用真实负载、JIT 差值和排空，不计为正式性能样本。 |
| [mutex_clobber/README.md](../kernel_experiments/mutex_clobber/README.md) / [guest-kernel.patch](../kernel_experiments/mutex_clobber/guest-kernel.patch) / [capture.py](../kernel_experiments/mutex_clobber/capture.py) | 独立 kdclobber2 普通 mutex 调用者 ABI、static-call 桥接与基线捕获。 |
| [spin_clobber/README.md](../kernel_experiments/spin_clobber/README.md) / [guest-kernel.patch](../kernel_experiments/spin_clobber/guest-kernel.patch) / [capture.py](../kernel_experiments/spin_clobber/capture.py) | 独立 kdclobber1 普通 spin 调用者 ABI、版本化桥接与基线捕获，保留原内核和缓解配置。 |
| [spin_static/README.md](../kernel_experiments/spin_static/README.md) / [guest-kernel.patch](../kernel_experiments/spin_static/guest-kernel.patch) / [capture.py](../kernel_experiments/spin_static/capture.py) | 经授权的独立 spin hook 直接调用内核实验与基线捕获；保留原内核和原基线。 |
| [test_spin_cacheline.py](../bench/spin_cacheline/test_spin_cacheline.py) / [client_fixture.c](../bench/spin_cacheline/client_fixture.c) | guest 定向布局/真实客户端/聚合/配对/正文计数检查，并核对增大批次不增加 ioctl/时钟调用；替代设备与 CPU 原语不算实际内核 JIT。 |
| [control_fixture.c](../bench/spin_cacheline/control_fixture.c) | 提取驱动实际原子准入函数，验证在途 writer 与独占计数快照相互排斥；客户端夹具另覆盖延迟 ready 和创建/绑核失败。 |
| [workload_modules/lock_scenarios/Makefile](../workload_modules/lock_scenarios/Makefile) | workload 构建与可选第二源码模块开关。 |
| [klock_module.c](../workload_modules/lock_scenarios/klock_module.c) | mode 分派、复杂 CS 记录、独立完整性检查和测试片段宿主；mode 4 分会话检查同 CPU 的 B 等待及两 A 共用原生 B。 |
| [kd_depth_source.c](../workload_modules/lock_scenarios/kd_depth_source.c) / [头文件](../workload_modules/lock_scenarios/kd_depth_source.h) | 两模块 learned-depth 实验的外部七锁 helper；普通启动不用加载。 |
| [hotlock_record/run.py](../bench/hotlock_record/run.py) / [组件驱动](../tests/kernel/hotlock_record/record_bench.c) | 冻结旧/新生产采样器，独立测发现延迟、冷地址流及正向命中成本；不装 hook 或执行 JIT。 |
| [kernel_baseline/README.md](../kernel_baseline/README.md) | 已捕获内核身份、已有 hook 差异和重建边界。 |
| [verify.py](../kernel_baseline/verify.py) | 只读检查 source/build/running；不是安装脚本。 |
| [manifest.json](../kernel_baseline/manifest.json) | 源码、构建文件和运行身份的基线哈希。 |
| [guest.config](../kernel_baseline/guest.config) | 捕获的内核配置，不是要求立即应用的新配置。 |
| [linux-6.1.159-guest.patch](../kernel_baseline/linux-6.1.159-guest.patch) | 已有改动证据；字节和旧注释保持原样，不作阅读性重写。 |

### 5.6 测试入口 `tests/`

文档入口为 [tests/README.md](../tests/README.md)，包含环境、用例选择、Demo
模式和证据解释；根 README 不维护测试命令或成绩。

测试入口通过 `run_all.sh --case/--suite` 选择，下面列原始驱动便于阅读。不要把
每个 `.sh` 都依次运行。复杂驱动管理角色和超时，直接以默认参数运行也可能加载模块。

| 文件 | 覆盖/用途 |
| --- | --- |
| [run_all.sh](../tests/run_all.sh) / [regression.py](../tests/regression.py) | 统一选择、去重、空闲门禁、执行和证据；`--jit-timing` 显式选择每个 case 的计量，不改变固定目录。 |
| [paired_benchmark.py](../tests/tools/paired_benchmark.py) / [benchmark_arm.sh](../tests/tools/benchmark_arm.sh) | 显式同负载原生锁/JIT 配对、交替重复及扫描；文件名中的 `arm` 指实验组，不是架构适配。shell 管理新会话，Python 校验准备/计时/发布/body，关联翻译资源和控制台设置；不进入固定回归目录。 |
| [common.sh](../tests/common.sh) | 驱动共享的构建、JIT 检查、daemon/清理函数；`load_kdlock` 统一各阶段装载/计量检查，保留可选 insmod 超时；start_daemon 透传显式选项，不交互 source。 |
| [regression_evidence.py](../tests/regression_evidence.py) / [verify_evidence.py](../tests/verify_evidence.py) | 捕获冻结输入与输出；离线一致性校验。 |
| [test_01_module_load.sh](../tests/live/test_01_module_load.sh) | 基础模块/设备显式诊断。 |
| [test_02_jit_engine.sh](../tests/live/test_02_jit_engine.sh) | promotion/翻译/上传管线诊断，不执行 JIT。 |
| [test_04_spinlock.sh](../tests/live/test_04_spinlock.sh) | spin 主模式、复杂记录及生成体证据；mode 8 追加独立双根阶段并保存前一阶段证据。 |
| [test_05_mutex.sh](../tests/live/test_05_mutex.sh) | mutex_jit=0 的原生互斥对照。 |
| [test_07_mutex_jit.sh](../tests/live/test_07_mutex_jit.sh) | mode 3 的发布门禁与独立 origin CPU 单锁竞争。 |
| [test_08_mutex_jit_modes.sh](../tests/live/test_08_mutex_jit_modes.sh) | mode 4 同 CPU 和共享原生 B 两阶段；OOO 只运行第一阶段。mode 5 服务返回和额度后缀。执行流见 [6.12](testing/mutex_protocols.md#612-同-cpu-的嵌套-mutex-jit)、[6.13](JIT_EXECUTION.md#613-call-次数额度与原生后缀)、[6.15](testing/mutex_protocols.md#615-两个-a-combiner-共享原生-mutex-b)。 |
| [test_09_jit_execution_modes.sh](../tests/live/test_09_jit_execution_modes.sh) | 显式 mode 兼容入口；无参只列清单。 |
| [test_10_native_resume.sh](../tests/live/test_10_native_resume.sh) | CALL/native 后缀、寄存器、资源、信号和受检边界的主驱动。 |
| [test_11_mutex_native_protocol.sh](../tests/live/test_11_mutex_native_protocol.sh) | 目标/非目标共享 Linux mutex。 |
| [test_12_context_native_only.sh](../tests/live/test_12_context_native_only.sh) | 上下文拒绝负例，必须没有实际 JIT。 |
| [test_13_spin_shadow_capacity.sh](../tests/live/test_13_spin_shadow_capacity.sh) | 显式 full-shadow 队首诊断。 |
| [test_14_spin_frame_depth.sh](../tests/live/test_14_spin_frame_depth.sh) | 自然物理 frame 链和继承的锁容量。 |
| [test_15_spin_native_gate.sh](../tests/live/test_15_spin_native_gate.sh) | 原锁 L/私有 S 内核组件检查。 |
| [test_16_spin_entry.sh](../tests/live/test_16_spin_entry.sh) | origin ticket/task/CPU 原生引用组件检查。 |
| [test_17_spin_native_protocol.sh](../tests/live/test_17_spin_native_protocol.sh) | spin 与非目标原生 API 的 Linux 互斥。 |
| [test_18_spin_routing.sh](../tests/live/test_18_spin_routing.sh) | 真实 hook 路由，刻意不执行 JIT。 |
| [test_19_mutex_signals.sh](../tests/live/test_19_mutex_signals.sh) | 非目标原生 mutex peer 的信号取消。 |
| [test_20_remote_outer.sh](../tests/live/test_20_remote_outer.sh) | 远端祖先提前释放和 owner 依赖；mode 8 调用 `multi` 纯 JIT 与 `multi quota` 混合完成两个变体。 |
| [test_21_remote_depth.sh](../tests/live/test_21_remote_depth.sh) | 四至八层、多请求、跨 NUMA/deferred 组合。 |
| [test_22_mutex_task_lifecycle.sh](../tests/live/test_22_mutex_task_lifecycle.sh) | 真实 task/RCU/final ACK，不计 JIT。 |
| [test_23_mutex_parallel_native.sh](../tests/live/test_23_mutex_parallel_native.sh) | 双队列 frame、资源压力、rename、peer、source 退休。 |
| [test_24_gs_jit.sh](../tests/live/test_24_gs_jit.sh) | mode 10/11 的 GS 读、写、RMW 和 current 代理正例。 |

### 5.7 测试控制器和 oracle

这组文件由驱动调用；部分会控制真实进程/sysfs，不应当作全部只读工具。名字带
`protocol` 表示检查器/协调器，而不是生产锁协议实现。

| 文件 | 用途 |
| --- | --- |
| [cpu_placement.py](../tests/protocols/cpu_placement.py) | 采集真实 CPU/NUMA 拓扑。 |
| [audit_context_spills.py](../tests/tools/audit_context_spills.py) | 独立静态准入 corpus，不执行危险指令。 |
| [mutex_signal_client.c](../tests/clients/mutex_signal_client.c) | pidfd/信号实验的单进程客户端；双 frame 原 waiter 只执行一次 ioctl，原生 peer 取消后显式重试。 |
| [mutex_signal_protocol.py](../tests/protocols/mutex_signal_protocol.py) | 就绪检查、mode 4 同 CPU 及两 A/共享原生 B 的身份/JIT/ACK、mode 5 超额度 CALL，以及 signal peer 控制/判定。 |
| [mutex_parallel_protocol.py](../tests/protocols/mutex_parallel_protocol.py) | 双 frame、原 waiter 的 pidfd 信号/退出、共享 CPU 和资源组合协调。 |
| [mutex_shadow_protocol.py](../tests/protocols/mutex_shadow_protocol.py) | 双 frame 内真实 shadow map 压力。 |
| [mutex_stack_protocol.py](../tests/protocols/mutex_stack_protocol.py) | 共享栈变化后的 post-control 续跑判定。 |
| [native_only_protocol.py](../tests/protocols/native_only_protocol.py) | 真实设备拒绝协议，不执行代码。 |
| [native_ooo_protocol.py](../tests/protocols/native_ooo_protocol.py) | 原 waiter 的 A-before-B 完成顺序。 |
| [native_register_protocol.py](../tests/protocols/native_register_protocol.py) | CALL-entry GPR/SP/IP 样本与 native frame 关联。 |
| [native_waiter_signal_protocol.py](../tests/protocols/native_waiter_signal_protocol.py) | 原 waiter 的信号、B 获取/取消和最终 A ACK。 |
| [native_waiter_signal_race.py](../tests/protocols/native_waiter_signal_race.py) | pidfd signal 与真实 B release 竞争。 |
| [readmission_protocol.py](../tests/protocols/readmission_protocol.py) | 两次尝试的真实队列重入契约。 |
| [remote_depth_protocol.py](../tests/protocols/remote_depth_protocol.py) | 深层远端 chain 和请求证据。 |
| [remote_outer_protocol.py](../tests/protocols/remote_outer_protocol.py) | 远端祖先/原生依赖及两个独立 root 共享 B 的逐请求证据；quota 阶段还关联首 waiter TID 退出与第二 root JIT。 |
| [spin_acquired_protocol.py](../tests/protocols/spin_acquired_protocol.py) | 本地已获取 B 的受检 post-CALL native。 |
| [spin_frame_protocol.py](../tests/protocols/spin_frame_protocol.py) | task 栈物理 frame 与 RSP 采样判定；兼容校验历史独立栈 watermark，区分两种指标。 |
| [spin_gate_protocol.py](../tests/protocols/spin_gate_protocol.py) | gate map 饱和、冷入口原生互斥，以及第二个 JIT 前缀的 PENDING ENOMEM/双 frame/最终 ACK。 |
| [spin_node_protocol.py](../tests/protocols/spin_node_protocol.py) | 排空后的节点 reservation 检查。 |
| [source_depth_protocol.py](../tests/protocols/source_depth_protocol.py) | 两层/两模块学习及 loader ref 与 source pin 区分。 |
| [source_retirement.py](../tests/protocols/source_retirement.py) | dual-frame 的 busy/finish/reuse source 阶段。 |
| [source_session_driver.c](../tests/clients/source_session_driver.c) / [source_session_child.py](../tests/clients/source_session_child.py) | 实际 fork/exec 设备 lease 存活探针，不是假装翻译成功。 |

### 5.8 Demo 临界区与内核测试片段

`workload_modules/lock_scenarios/fragments/` 的片段被 `klock_module.c` 或另一个
workload include；`tests/kernel/` 的观察器/组件自测在 `KDLOCK_SELFTEST` 下被
provider include。具体 include 点可用
`rg '#include.*(fragments|tests/kernel|workload)' workload_modules kernel_module` 查找。

| 文件 | 用途 |
| --- | --- |
| [context_lock_workload.c](../workload_modules/lock_scenarios/fragments/context_lock_workload.c) | IRQ/BH/per-CPU 原生拒绝源码。 |
| [native_register_probe.h](../workload_modules/lock_scenarios/fragments/native_register_probe.h) / [native_register_workload.c](../workload_modules/lock_scenarios/fragments/native_register_workload.c) | 无 C prologue 的 GPR 样本和可翻译前缀。 |
| [native_ooo_workload.c](../workload_modules/lock_scenarios/fragments/native_ooo_workload.c) | A 提前解锁的本地 native/JIT 场景。 |
| [native_waiter_signal_workload.c](../workload_modules/lock_scenarios/fragments/native_waiter_signal_workload.c) | 原 waiter 信号后仍保留副作用和 A ACK。 |
| [mutex_signal_workload.c](../workload_modules/lock_scenarios/fragments/mutex_signal_workload.c) | 原生 peer 的 interruptible/killable 等等待。 |
| [mutex_parallel_workload.c](../workload_modules/lock_scenarios/fragments/mutex_parallel_workload.c) | 两独立队列的真实 native frame；第二 frame 的有界门用于观察第一 waiter 退出。 |
| [mutex_shared_workload.c](../workload_modules/lock_scenarios/fragments/mutex_shared_workload.c) | 两个 A executor 与非目标 peer 共用原生 B；保留 owner 的普通 CALL 后缀与后继 JIT、真实 Linux 等待队列和精确记录。 |
| [mutex_parallel_peers.c](../workload_modules/lock_scenarios/fragments/mutex_parallel_peers.c) | 双 B 原生 peer 的取消/重排和 owner 观察。 |
| [mutex_code_pool_workload.c](../workload_modules/lock_scenarios/fragments/mutex_code_pool_workload.c) | 64 个真实 cold CALL site 消耗代码池，不计 JIT。 |
| [mutex_shadow_workload.c](../workload_modules/lock_scenarios/fragments/mutex_shadow_workload.c) | 原 hook 获取造成 shadow map 耗尽。 |
| [mutex_stack_workload.c](../workload_modules/lock_scenarios/fragments/mutex_stack_workload.c) | B owner 改写共享栈字，触发受检 native 后继。 |
| [spin_native_workload.c](../workload_modules/lock_scenarios/fragments/spin_native_workload.c) | 原生 L 排斥和 alternate API 数据 oracle。 |
| [spin_routing_workload.c](../workload_modules/lock_scenarios/fragments/spin_routing_workload.c) | 可控目标/非目标 hook 路由。 |
| [spin_chain_workload.c](../workload_modules/lock_scenarios/fragments/spin_chain_workload.c) | 八层物理 queue/combiner 链。 |
| [spin_multi_workload.c](../workload_modules/lock_scenarios/fragments/spin_multi_workload.c) | 两个独立 A root 共享 B；14 角色门禁、逐 root 副作用，quota 变体检查原 waiter 的单 origin pin、B 暂停及后继 JIT。 |
| [remote_depth_workload.c](../workload_modules/lock_scenarios/fragments/remote_depth_workload.c) | 一个 logical waiter 的多物理执行者和 deferred 请求。 |
| [remote_outer_workload.c](../workload_modules/lock_scenarios/fragments/remote_outer_workload.c) | 远端祖先解锁及独立 owner 依赖。 |
| [spin_ticket_workload.c](../workload_modules/lock_scenarios/fragments/spin_ticket_workload.c) | 真实获取填满 32 个 ticket。 |
| [spin_gate_workload.c](../workload_modules/lock_scenarios/fragments/spin_gate_workload.c) | 旧后缀存活时填满 gate map，再执行已发布 A2 JIT 并在无 gate 的 C 上原生续跑；角色和控制参数见使用指南 6.3。 |
| [spin_acquired_workload.c](../workload_modules/lock_scenarios/fragments/spin_acquired_workload.c) | B 私有队首、后继竞争者与已提交 A 前缀。 |
| [mutex_shadow_trace.c](../tests/kernel/mutex/mutex_shadow_trace.c) | 只观察真实 shadow 表，不填造成员。 |
| [spin_node_trace.c](../tests/kernel/spin/spin_node_trace.c) | node reservation 排空记录。 |
| [spin_frame_trace.c](../tests/kernel/spin/spin_frame_trace.c) | frame 深度与实际 task 栈边界/RSP 余量采样；不填色活栈，不在深栈上打印。 |
| [spin_refusal_trace.c](../tests/kernel/spin/spin_refusal_trace.c) | 拒绝包、owner/ledger 的只读快照。 |
| [spin_readmission_trace.c](../tests/kernel/spin/spin_readmission_trace.c) | bounded readmission 观察。 |
| [spin_deferred_trace.c](../tests/kernel/spin/spin_deferred_trace.c) | 真实 deferred 队列选择/接链观察。 |
| [exec_capacity_probe.c](../tests/kernel/execution/exec_capacity_probe.c) | 固定 frame 容量拒绝及包不变观察。 |
| [exec_relay_exit_probe.c](../tests/kernel/execution/exec_relay_exit_probe.c) | 无锁 root finish 或已发 ACK 的远端 B pop 等待原 waiter TID 脱离；仅持有 PID 身份，不加 task ref、不伪造 ACK。 |
| [spin_entry_selftest.c](../tests/kernel/spin/spin_entry_selftest.c) | task/CPU pins、tickets 与原生锁组件。 |
| [spin_shadow_selftest.c](../tests/kernel/spin/spin_shadow_selftest.c) | full-shadow 队首路径。 |
| [spin_virtual_selftest.c](../tests/kernel/spin/spin_virtual_selftest.c) | virtual 请求资源拒绝/取消检查。 |
| [mutex_task_selftest.c](../tests/kernel/mutex/mutex_task_selftest.c) | task 路由删除、跨 reader RCU 与 final ACK。 |

### 5.9 单元测试 `tests/unit/`

`Makefile` 中的程序才是通常运行入口；`*_fixture.c` 多由对应 Python 程序生成
生产代码头后编译，不能脱离该驱动直接编译。模型、替代原语和 log mutation
不证明 Linux 并发正确；程序自身标明何处执行真实生成机器码。
默认仅运行 2 个基础 C；Python 入口通过 `unit/run.py`
按分组路径或唯一文件名选择，完整库存只供显式全量。逐项的覆盖重叠、模型
精简进展和保留理由见 [测试分析](TEST_EXAMPLES.md#4-单元入口逐项分析)；
本节保留源码与 fixture 的阅读索引。大型测试的 `*_cases.py` 由驱动显式收集，
辅助组件不作为额外入口：

- admission：`context_case_support.py` 共享助手，`context_symbols_cases.py`、`context_flow_cases.py`、`context_instructions_cases.py` 按职责分组。
- mutex：`parallel_fixtures.py` 共享日志，`parallel_signals_cases.py` 和 `parallel_pools_cases.py` 验证信号及资源池。
- infrastructure：`regression_boundary_cases.py` 和 `regression_evidence_cases.py` 验证退出边界及归档。

| 文件 | 用途 |
| --- | --- |
| [run.py](../tests/unit/run.py) | 单项 Python 入口，统一配置跨组夹具导入；无参数只列出库存。 |
| [Makefile](../tests/unit/Makefile) | 默认 2 个基础 C 程序；PY_TESTS 按需增加，run-all 显式全量。 |
| [test_control_call.c](../tests/unit/basic/test_control_call.c) | 直接使用生产 kd_call 规则。 |
| [test_daemon_policy.c](../tests/unit/basic/test_daemon_policy.c) | 编译生产 daemon，测试结果缓存、真实子进程 lease/reap 和 wire；计量默认关闭、wait4 中断重试与时钟/资源失败。 |
| [test_clobber_entry.py](../tests/unit/admission/test_clobber_entry.py) | 新 ABI 未捕获寄存器、部分写、控制边界、入口栈槽与别名拒绝。 |
| [test_context_policy.py](../tests/unit/admission/test_context_policy.py) | 上下文/CFG/静态范围/有界分析 corpus。 |
| [test_context_memory.py](../tests/unit/admission/test_context_memory.py) | byte/word、alias、RMW、clobber 顺序事实。 |
| [test_context_guards.py](../tests/unit/admission/test_context_guards.py) | 实际运行入口谓词及有界 CALL/RET 生成体。 |
| [test_context_spill_audit.py](../tests/unit/admission/test_context_spill_audit.py) | 独立 spill audit 的错误分类。 |
| [test_hostcall_codegen.py](../tests/unit/codegen/test_hostcall_codegen.py) | manifest 与服务出口生成一致性。 |
| [test_segment_codegen.py](../tests/unit/codegen/test_segment_codegen.py) | segment lowering 与 wrapper 偏移。 |
| [test_text_regions.py](../tests/unit/admission/test_text_regions.py) | cold text、CFG 扩展、设备 session/CAPS。 |
| [test_jit_diagnostics.py](../tests/unit/codegen/test_jit_diagnostics.py) | 可复用 mocked-text harness 和定位/告警判定。 |
| [test_jit_body_witness.py](../tests/unit/codegen/test_jit_body_witness.py) | guest 用户态运行真实 wrapper 和生成体 marker。 |
| [test_shared_reg_bank.py](../tests/unit/codegen/test_shared_reg_bank.py) | 返回前验证 backing 双向共用，高寄存器压力、部分 R11、hostcall 续跑和 block 额度出口。 |
| [test_jit_entry_scope.py](../tests/unit/execution/test_jit_entry_scope.py) / [jit_entry_scope_fixture.c](../tests/unit/execution/jit_entry_scope_fixture.c) | 生产 JIT 入口/scope/拒绝包，typed hostcall 策略、完整 RDI/RAX 参数返回与共同额度；额度出口不弹 CALL 栈、不重放或触发学习。边界计时开关前后完整 frame/包一致；服务和计时原语为替代，实际执行需 live 验证。 |
| [test_exe_registry.py](../tests/unit/execution/test_exe_registry.py) / [exe_registry_fixture.c](../tests/unit/execution/exe_registry_fixture.c) | 生产 registry、代码池及上传边界、服务表编译契约和计量重置/卸载。服务 manifest/adapter 变化也须独立运行本入口。 |
| [test_exec_capacity.py](../tests/unit/execution/test_exec_capacity.py) / [exec_capacity_fixture.c](../tests/unit/execution/exec_capacity_fixture.c) | 生产 frame/ledger/完成状态、remote/native 未排空的回收拒绝、两后端清理和实际退出观察器；PID/RCU/time 等原语替代，不替代真实 ACK/退出。 |
| [test_hotlock_sampling.py](../tests/unit/infrastructure/test_hotlock_sampling.py) / [hotlock_sampling_fixture.c](../tests/unit/infrastructure/hotlock_sampling_fixture.c) | 替代 CPU/TSC 下的生产采样：批量门槛、独立窗口、碰撞、并发发布、重入、时间倒退与终态；不是实际 JIT。 |
| [test_mutex_resources.py](../tests/unit/mutex/test_mutex_resources.py) / [mutex_resources_fixture.c](../tests/unit/mutex/mutex_resources_fixture.c) | 生产 tail/node/shadow/hook、频率先于进程选择、hook 改名/降温/关闭路由及完整 packet；per-CPU 存储为替代原语。 |
| [test_mutex_wait_clobber.py](../tests/unit/mutex/test_mutex_wait_clobber.py) | ABI 2 生产 shadow 切栈/毁栈恢复；wrapper 共用检查由 codegen/test_clobber_abi.py 承担。 |
| [test_mutex_outer_progress.py](../tests/unit/mutex/test_mutex_outer_progress.py) / [mutex_outer_progress_fixture.c](../tests/unit/mutex/mutex_outer_progress_fixture.c) | 生产 mutex combiner/outer-event、原 owner/后继进度；编译真实日志宏，仅替代 printk sink，检查 INFO/格式/保留次数和两个日志变异，不模拟串口或调度耗时。 |
| [test_native_after_outer.py](../tests/unit/execution/test_native_after_outer.py) / [native_after_outer_fixture.c](../tests/unit/execution/native_after_outer_fixture.c) | 生产 native/control 边界和 mutex B 获取/解锁，原语为替代实现。 |
| [test_native_registers.py](../tests/unit/execution/test_native_registers.py) / [native_register_fixture.c](../tests/unit/execution/native_register_fixture.c) | 实际用户态汇编 probe 与 GPR oracle。 |
| [test_spin_gate.py](../tests/unit/spin/test_spin_gate.py) | 历史 gate 证据解析；当前单字协议没有 gate map。 |
| [test_spin_entry.py](../tests/unit/spin/test_spin_entry.py) / [spin_entry_fixture.c](../tests/unit/spin/spin_entry_fixture.c) | 生产 origin ticket/ref 生命周期。 |
| [test_clobber_abi.py](../tests/unit/codegen/test_clobber_abi.py) | 合并的 ABI 1/2 wrapper 入口，默认两者；真实 caller clobber、精简/完整出口和混合交接，检查 poisoned packet 及寄存器压力。 |
| [test_tclock_context.py](../tests/unit/spin/test_tclock_context.py) | TCLock 六寄存器、RSP 与原生 lock/unlock 续点的真实汇编验证；不等于复杂内核场景覆盖。 |
| [test_spin_wwjump.py](../tests/unit/spin/test_spin_wwjump.py) / [legacy_batch.S](../tests/unit/spin/legacy_batch.S) | 当前旧入口 clobber 适配与历史外壳兼容对照；后者仅为测试夹具。 |
| [test_spin_batch.py](../tests/unit/spin/test_spin_batch.py) / [spin_batch_fixture.c](../tests/unit/spin/spin_batch_fixture.c) | 批内失效、三种预取策略、共享/独立包与栈边界；不可读页验证预取不追读 frame/包，另验 per-CPU 统计。 |
| [test_spin_shadow.py](../tests/unit/spin/test_spin_shadow.py) / [spin_shadow_fixture.c](../tests/unit/spin/spin_shadow_fixture.c) | 提取实际队首和 combiner 路径；区分容量交接与普通批次发布。 |
| [test_spin_wait.py](../tests/unit/spin/test_spin_wait.py) / [spin_wait_fixture.c](../tests/unit/spin/spin_wait_fixture.c) | guest 用户态执行生产发布/等待汇编；覆盖旧 C 栈后验证完成/native 非局部恢复，以及未执行队首的正常返回；[spin_restore_fixture.c](../tests/unit/spin/spin_restore_fixture.c) 执行共享包恢复汇编，核对 GPR 与最后读取后归还引用。 |
| [spin_node_pool_fixture.c](../tests/unit/spin/spin_node_pool_fixture.c) / [spin_queue_return_fixture.c](../tests/unit/spin/spin_queue_return_fixture.c) | 上述 fixture include 的真实 producer、容量和嵌套返回。 |
| [test_spin_outer_progress.py](../tests/unit/spin/test_spin_outer_progress.py) / [spin_outer_progress_fixture.c](../tests/unit/spin/spin_outer_progress_fixture.c) | 生产 spin batch/frame/outer-release、满 gate 表时 nested ENOMEM/PENDING 包，以及 release 发布和槽复用；不执行实际 JIT。 |
| [test_remote_outer.py](../tests/unit/execution/test_remote_outer.py) / [remote_outer_fixture.c](../tests/unit/execution/remote_outer_fixture.c) | 生产远端/祖先解锁及 native ACK；完整 pt_regs、CALL 包、DONE 前脱链和发布后父 frame 复用；计量开关下的完整包、错误返回及两后端分类。CPU/发布/时钟为替代，不恢复硬件 flags。 |
| [test_remote_deferred_protocol.py](../tests/unit/execution/test_remote_deferred_protocol.py) / [deferred_trace_fixture.c](../tests/unit/execution/deferred_trace_fixture.c) | deferred oracle 与实际选队/trace 代码。 |
| [test_spin_frame_protocol.py](../tests/unit/spin/test_spin_frame_protocol.py) / [spin_refusal_trace_fixture.c](../tests/unit/spin/spin_refusal_trace_fixture.c) | frame/refusal 日志与提取的观察器。 |
| [test_source_lifetime.py](../tests/unit/infrastructure/test_source_lifetime.py) / [source_lifetime_fixture.c](../tests/unit/infrastructure/source_lifetime_fixture.c) | 生产 source/CAPS/retire，内核原语替代。 |
| [test_source_depth_protocol.py](../tests/unit/infrastructure/test_source_depth_protocol.py) | 破坏 source/loader-ref 记录，确认 oracle 拒绝。 |
| [test_mutex_parallel_protocol.py](../tests/unit/mutex/test_mutex_parallel_protocol.py) / [mutex_parallel_client_fixture.c](../tests/unit/mutex/mutex_parallel_client_fixture.c) | 双 frame oracle、pidfd 退出协调、实际客户端的单次 waiter 与两次 peer ioctl 路由。 |
| [test_mutex_stack_protocol.py](../tests/unit/mutex/test_mutex_stack_protocol.py) | 拒绝伪造的栈变化/post-control 日志。 |
| [test_mutex_signal_protocol.py](../tests/unit/mutex/test_mutex_signal_protocol.py) | 同 CPU 嵌套 JIT、CALL 额度包/计数/ACK、signal/peer/原 waiter 的坏日志、身份/顺序和参数。 |
| [test_native_ooo_protocol.py](../tests/unit/execution/test_native_ooo_protocol.py) | A-before-B 日志 oracle。 |
| [test_remote_outer_protocol.py](../tests/unit/execution/test_remote_outer_protocol.py) | 远端祖先依赖及双根身份、owner、JIT/副作用的坏日志拒绝。 |
| [test_remote_depth_protocol.py](../tests/unit/execution/test_remote_depth_protocol.py) | 深链记录及真实 workload wait predicate。 |
| [test_spin_node_protocol.py](../tests/unit/spin/test_spin_node_protocol.py) | reservation/drain 坏记录。 |
| [test_cs_oracle.py](../tests/unit/infrastructure/test_cs_oracle.py) | 实际 workload 状态更新与完整性函数。 |
| [test_benchmark.py](../tests/unit/infrastructure/test_benchmark.py)、[benchmark_fixture.c](../tests/unit/infrastructure/benchmark_fixture.c) | 真实 pthread 驱动的 30 项测量/失败场景及 113 项配对观测检查；含翻译身份/区间/资源、可选十项 JIT/native/队列计数及无效记录、控制台和历史字段边界。替代 ioctl/确定时钟，另验证真实 guest 时钟；日志替身不证明实际 JIT，不加载内核模块。 |
| [test_kernel_baseline.py](../tests/unit/infrastructure/test_kernel_baseline.py) | 基线 reader 的损坏/伪造输入，不读取 live kernel。 |
| [test_regression.py](../tests/unit/infrastructure/test_regression.py) | 用例选择去重、停止边界、证据捕获和离线 verifier；计量选择覆盖直接/组合装载和原超时，拒绝重复配置。 |


`tests/protocols/mutex_parallel_protocol.py` 保留双 frame 总体验证和 CLI；
[events](../tests/protocols/mutex_parallel_events.py) 校验逐角色事件，
[signals](../tests/protocols/mutex_parallel_signals.py) 核对客户端身份并处理信号，
[pools](../tests/protocols/mutex_parallel_pools.py) 校验代码池及退休后重载。
拆分保持各验证函数及失败条件，不改变 live 操作顺序。

当前显式对象和协议回归：

| 文件 | 职责 |
| --- | --- |
| [kd_spin_type.h](../include/kd_spin_type.h) | 四字节 KD 对象及初始化，与 Linux 对象分离 |
| [spin_single_mock.h](../tests/unit/spin/spin_single_mock.h) | 单字/ticket 提取式回归的确定性 CPU 原语 |
| [lifetime_selftest.c](../tests/kernel/hotlock/lifetime_selftest.c) | 真实持锁淘汰、mutex 等待迁移 CPU |
| [scenario.h](../workload_modules/spin_cacheline/scenario.h) | 可选显式双锁 nested/early JIT 负载，默认性能正文不变 |
