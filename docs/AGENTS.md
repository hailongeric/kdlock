# kdlock 操作手册

本文只规定环境、安全边界和操作流程。执行流见
[JIT_EXECUTION.md](JIT_EXECUTION.md)，协议见 [DESIGN.md](DESIGN.md)，
测试与 benchmark 的说明、运行入口及新增结果分别维护在
[tests/README.md](../tests/README.md)、[bench/README.md](../bench/README.md)
及对应子目录 README；历史证据保留在 [VALIDATION.md](VALIDATION.md)。
根 README 只保留项目介绍和目录导航。剩余任务见 [TODO.md](TODO.md)。
逐文件阅读、目录索引及从零开始的手动步骤统一维护在
[PROJECT_GUIDE.md](PROJECT_GUIDE.md)，不要再建立平行的安装/手动测试清单。

## 开发约定

项目范围固定为 x86_64 内核 spin/mutex JIT 代理。任务描述、实现与测试均不安排
其他架构适配，不将跨架构移植保留为延期任务。实验组命名和探针启用事件不是
架构分支；不得因此删除现有 x86_64 测试或改写已捕获的内核基线。

1. 先读代码、文档及 `git status --short`，保留已有改动，不重置未知文件。
2. 新增或修改协议、算法、测试时，必须注释其目的、用途和关键约束，尤其解释
   为什么需要该分支或顺序；不要求逐行复述代码。
3. 优先完成常见主路径和可执行的端到端验证。用户于 2026-09-14 明确：极少
   出现的情况可以不补实现、不专项测试；具体任务分类见
   [交付范围](TODO.md#delivery-scope)。不再为极端资源组合、特殊取消/退出时序
   或任意别名组合持续扩展用例，也不将其作为当前交付前置条件。已知缺口保留
   为限制，不把未测写成通过；常见目标路径已复现的错误仍须处理。
   当前主模式及 mutex 两层 learned helper、受检栈事实与真实栈变化续跑已通过。
   用户于 2026-09-13 明确继续延期访问时 guard、新的原指令续跑出口及其局部
   条件码保护；保留为未实现限制，不再等待或重复请求范围确认，也不擅自实现。
   已有 owner/ACK、资源和生命周期约束继续保留；修改相关主路径时选择对应回归。
   代码池、mutex shadow 表真实耗尽和原生 B 竞争者的取消/重排已并入双 frame 退休用例；
   不要再单设基础 smoke。
   更广的 CALL/RET、别名和并发上下文作为可选扩展。保持实际 JIT 验收，
   不能削弱敏感地址检查或删除探针来制造通过。
   RET 值分析可能不给某个后继传播状态，但只要它仍在生成范围/返回表内，就必须
   先做无条件上下文与后端检查；不能据此假定运行时返回槽不受并发修改。
   动态指针和并发改写的实际用户态反例已复现，见 DESIGN 7.2.1；
   `CONTEXT_SCREENING_ONLY` 仅标注缺口，不是运行时保护。只改这种日志时复用
   使用指南 5.2 的诊断/wrapper 测试，不重复内核 live 矩阵。
   核心静态 per-CPU 与模块启动预留区通过已有设备会话的能力和 CPU 元数据建立；
   元数据异常或模块范围能力缺失是翻译环境错误，不能当作 native-only 通过。
   修改此准入时按 5.2/5.3 选择相关 unit/audit 和复杂 JIT 组合，不把动态分配、
   模块对象存活或未知指针记为已覆盖；禁止按整个 unit 大小扩大范围。
4. 默认只改 kdlock，不修改、编译或安装 guest 内核；现有 hook 无法支持的
   能力单独评估。不可变 JIT 版本和 flags/特殊指令语义修复已明确延期。
   2026-09-15 用户在直接调用补丁草案后要求继续优化并定位耗时，已授权本轮
   spin hook 独立实验内核的构建、启动和验证。保留原内核及捕获基线；实验
   使用独立源码/build、release 和基线，不将这次授权扩展为任意内核改动。
5. 不扩展两元素 wrapper 输入 ABI，不恢复已删除的 futex 执行入口。
6. 提交前核对差异、测试证据和文档。仅在用户要求时提交 Git；不能把历史
   结果记为本次重跑，也不能把未通过的主功能写成已完成。
7. 文档按职责维护单一入口。旧验收只保留关键结果与证据索引，详细调查通过
   Git 历史追溯；不要持续追加重复实现说明或保留已失效的下一步指令。
   用户于 2026-09-15 再次明确：benchmark/test 信息不写入根 README，写入
   各自目录的 README；不得把运行命令、模式表或成绩重新放回根文档。
8. 测试与 benchmark 的 Demo 内核临界区模块统一放在 `workload_modules/`，
   按负载分子目录；客户端、运行器与结果处理放在 `bench/` 或 `tests/`。
   生产 provider 的专用观察器/组件自测继续放在 `tests/kernel/`，不混入 Demo 负载。

## 环境边界

| 操作 | 位置 |
| --- | --- |
| 读写源码、静态格式检查、Git、归档、控制 VM | 宿主机 `/home/eric/vm/vm-shared/kdlock` |
| 只读离线归档校验 | 宿主机或 guest；不执行用例或访问 JIT 设备 |
| 编译、单元测试、模块、daemon、benchmark | guest `/root/host_fs/kdlock` |
| SSH | `root@127.0.0.1:2222` |
| guest 内核源码/build | `/root/linux-6.1.159` |
| QEMU 脚本 | 宿主机 `/home/eric/vm/qemu-scripts/run_vm.sh` |

不要在宿主机执行 make、模块加载、daemon 或 benchmark。
normal 模式用 9p 共享源码，不需要同步；recovery 模式同一路径是 guest ext4，
不会自动同步。比较单文件 SHA256，只 scp 变化文件，必要时先建对应子目录。
禁止移动、递归覆盖或清空 `/root/host_fs`；避免两侧同时编辑。

现有 baseline 不是新内核修改。不能只凭 `uname -r` 判断兼容性；
只读核对命令在 guest 执行：

```sh
cd /root/host_fs/kdlock
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
```

该命令核对捕获材料、18 个源码/接口文件、配置、九个构建文件及 live Build ID，
不代替完整源码扫描或运行配置检查。另查 `nokaslr`、voluntary 动态抢占、
CPU/NUMA 拓扑和挂载类型。具体身份与重建限制见
[baseline](../kernel_baseline/README.md)。不匹配时先查原因，不能自动改内核。

## 验证顺序

1. 宿主机检查 Git 和 VM，核对并按需同步源码哈希。
2. guest 确认没有在跑的 benchmark、daemon、旧模块及在途请求。
3. 新环境按 [手动指南 3.3](PROJECT_GUIDE.md#33-检查依赖与空闲状态) 安装固定版本
   的 Python 运行依赖，将 venv/bin 放到 PATH 首位供测试和 daemon 继承；不升级
   全局 pip 包。首次环境验收运行 `make -C tests/unit run` 和独立 admission audit；之后只运行
   改动影响的单元测试。修改分析器时再运行 `python3 tests/audit_context_spills.py`。
   必需依赖缺失、SKIP 或编译失败不能作为通过。
4. guest 构建后，首次开发可逐级进行模块加载、小负载；基础用例已经通过且
   环境未变化时，直接选择受影响的复杂 live 用例，不再重复基础验收。
5. 高风险加载前，从宿主机 monitor 确认可恢复快照；之后才设置
   `KDLOCK_RECOVERY_CONFIRMED=1`。环境变量本身不是快照存在的证据。
6. mutex JIT 只在已授权且可恢复的测试中使用 `mutex_jit=1`；
   `mutex_jit=0` 仅作为显式原生对照开关，不能作为默认运行策略。
7. 对 benchmark 和 SSH 都加外层 timeout。ConnectTimeout 只限制建连，
   不能限制已连接但卡住的远端命令。
8. 测试后核查结果、dmesg 错误、调用者退出及模块排空，再运行下一项。

修改已冻结的运行/测试输入前，先通过预置的用例边界停止机制等待当前用例
完成清理，再停止运行器。不要改写正在执行的 shell 文件。保留部分运行，
新输入按改动范围重新验证，不能拼接不同冻结版本的通过项冒充完整矩阵。
基础用例不作为每个增量的前置依赖；只有共享 ABI、跨后端公共逻辑、内核基线
等大范围变化，或发布验收/用户明确要求时才扩大回归。未重跑项标明历史结果。

完整手动顺序维护在 [PROJECT_GUIDE](PROJECT_GUIDE.md#3-一步一步运行)；
[README](../README.md#quick-start) 保留简短入口，复杂用例的命令和判定维护在
[JIT_EXECUTION](JIT_EXECUTION.md#3-环境与操作)。`tests/run_all.sh` 无参数只列出范围，
`--suite` / `--case` 才运行，`--dry-run` 只预览；多个范围按用例身份去重。
所有 live 用例仍须确认 recovery。分层、覆盖替代关系和增量命令只维护在
[测试选择](JIT_EXECUTION.md#7-分层与增量回归)，不要擅自把基础或 extended 加入日常范围。
只改选择规则时运行 `test_regression.py` 和命令预览，不因此重跑 JIT。统一入口
与旧多模式入口都要求显式选择才执行，重复用例去重，遇到失败即停止。
十一项已登记替代关系的诊断不进入任何套件，但显式 `--case` 仍可运行。
纯原生 `native-controls` 只作显式对照，不能计入实际 JIT 或成为每轮前置。

按行为选择复杂用例，具体命令、角色与不可替代的检查统一查以下章节。
下表是查阅索引，不是逐项必跑清单；只有选中用例后，才要求完整执行其判定，
不能为制造通过而删掉其中的边界检查。

| 行为 | 执行流与增量选择 |
| --- | --- |
| 同队列同 CPU 的 PENDING 续跑 | [6.1](JIT_EXECUTION.md#61-mutex-资源与恢复包)；不同于跨队列 context refusal |
| 真实 ticket/gate 压力与注入取消 | [6.3](JIT_EXECUTION.md#63-spin-虚拟请求取消与续跑)；核对额外 CPU 9-18，第二个 JIT 前缀的 gate ENOMEM 与旧 ticket E2BIG 分开验收 |
| 双 frame、代码/shadow 池、原生 peer 与退休 | [6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame) |
| 跨队列 context/node/task 拒绝 | [6.7](JIT_EXECUTION.md#67-同-cpu-的-mutex-jit-拒绝) |
| 物理 frame 链与锁记录容量 | [6.8](JIT_EXECUTION.md#68-物理-frame-链与容量检查)；不能替代 local shadow 容量 |
| 无锁 root 与 waiter 正常退出 | [6.9](JIT_EXECUTION.md#69-无锁祖先与-waiter-退出)；TID 脱离不等于 RCU 回收 |
| 提前释放 A 后的原生 owner 依赖 | [6.10](JIT_EXECUTION.md#610-提前释放-a-的原生依赖)；不同于普通 held-B CALL miss |
| 私有队首已获取 B 后的受检续跑 | [6.11](JIT_EXECUTION.md#611-spin-获取后的受检续跑)；不同于 FAST、PENDING 或远端发布失败 |
| A executor 与 B holder 同 CPU 的嵌套 JIT | [6.12](JIT_EXECUTION.md#612-同-cpu-的嵌套-mutex-jit)；七角色/双 CPU，不交回原 waiter 跑 native 后缀 |
| 两个 mutex A executor 共用原生 B | [6.15](JIT_EXECUTION.md#615-两个-a-combiner-共享原生-mutex-b)；普通 mode 4 的独立第二阶段，一个保留 owner 的 native 后缀、另一个 JIT 和非目标 peer，不是远端 B combiner |
| mode 5 服务返回和 CALL 次数额度退出 | [6.13](JIT_EXECUTION.md#613-call-次数额度与原生后缀)；保留正常 JIT 返回，再关联超额 callee 的 waiter/native/ACK，不是访问时 guard |
| 两个独立 A root 共用 B executor | [6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner)；mode 8 已含原复杂、双根纯 JIT、混合完成三个阶段；第三阶段在 B 发出 ACK 后的 pop 观察首 waiter TID 退出，再执行第二 root，不再另跑 `multi` |

覆盖关系按协议而非深度数字判断，单 frame 三锁和 local shadow 容量仍是独立检查。
不得为通过而填造 frame/队列、改容量、改原 owner 或添加改变 task 生命周期的测试引用。
真实耗尽与注入失败分开标注，未开始的原生回退不算额外 JIT。具体边界以表中章节为准，
这里不重复维护每次测试升级的进展日志。

### 验收与清理

实际 JIT 必须同时有有效生成物、匹配 entry/lock 且 wrapper 返回后的
`JIT body witness: ... body=1`、正确的负载状态。公共脚本强制
`KD_JIT_BODY_WITNESS=1`；单纯翻译命令、安装日志、调用前 IP 不够。
hostcall 还要检查执行与恢复；native-only 负例必须没有 JIT。
这些观测不是完整指令覆盖、版本证明或性能基线。

独立 [spin_cacheline microbenchmark](../bench/spin_cacheline/README.md) 的专用
provider 在 `bench/` 内构建，观测代码不得加入主项目源码或普通模块。其 quiet
模式以匹配被测锁的只读 `bench_jit_bodies` 测量前后差值替代逐次正文日志，
仍要求 wrapper 返回后的实际正文、有效生成/发布和完整数据校验。零差值为
NO_JIT，只保留性能结果，不是实际 JIT 通过；既有回归继续使用原正文日志判定。

生成物出现不代表设备已发布。mode 3/4/5 使用已有协议观察器等待对应 RIP/TGID
条目为 NORMAL，再运行负载；不能用即时安装日志代替发布状态，或用发布状态
代替实际 body witness。测试准备顺序见 [使用指南](JIT_EXECUTION.md#3-环境与操作)。

保留每项命令/环境、退出码、源文件哈希、内核身份、日志、生成物及 dmesg。
统一运行器现在自动保存冻结源码、boot notes、已宣告的协议目录和 daemon 日志；
用例开始前还查询工具/Python 依赖和运行设置，缺失或查询失败即停止，不记 SKIP。
这只是起始环境快照，不能证明整个运行中依赖未变，也不能自动复用历史 PASS。
只改这种只读采集时运行相关 `test_regression.py`，不额外重跑基础或 JIT 负载。
`tests/verify_evidence.py` 提供已有输出目录的离线一致性校验；操作、退出码、
大小限制和非执行边界只维护在上述证据流程中。它不会认证日志来源或重跑
逐项 oracle，不能取代可信外层哈希、当前回归或真实进程/VM 存活检查。
失败且已排空时也归档，未排空则明确标记证据不完整，不读取仍在变化的工作区。
归档文件与判定字段只维护在 [证据流程](JIT_EXECUTION.md#执行与证据)。
失败正例即使原生完成也仍是失败。扫描 `BUG:`、`panic`、`double fault`、
`soft lockup`、`unable to handle`；检查脚本退出码之外的内核状态。
信号测试仅对已经核对身份的 guest 测试客户端发信号。SIGKILL 的预期退出码
不能单独作为通过条件，仍须核对 JIT、完整副作用及最终 owner ACK。
原 waiter 的释放竞争须支持 pidfd，并留存真实 B owner 的 unlock 时间与 API
返回值；提前发信号不保证取消，sysfs 写成功不证明已解锁。偏置期望不符仍须
保留为失败，不能据此改写 owner/ACK/副作用判定，详见
[竞争测试](JIT_EXECUTION.md#65-原-waiter-与-b-释放的竞争)。

先停止新 workload，等待已有 workload/hook 调用者退出，确认队列/frame 无在途请求，
再停止 daemon/翻译者。执行 `python3 disassem/device_session.py retire` 成功后，
按 `klock_module`、`kdlock_km` 顺序卸载；公共测试清理函数已加入这一步。
`status` 子命令可查看 state/modules/frames/writers；`capabilities` 只读查询运行时
约定，不会开启 mutex_jit，不能代替翻译者在同一有效 lease 上的能力协商。
retire 返回 EBUSY 时保留 pins，
但新入口已关闭；继续等待旧持有者排空后重试，不要重新启动 daemon。只有重新
加载完整会话才能恢复 JIT，不能把 retire 当作可撤销的暂停。
`native-mutex-depth` 额外构建/加载可选的 `kd_depth_source`，正常路径在退休后按
`klock_module`、`kd_depth_source`、`kdlock_km` 顺序卸载，并恢复默认测试模块构建。
runner 将这个额外模块也纳入空闲检查；若仍然存在，先检查失败用例，不能忽略它
继续下一轮。模块 refcnt 同时包含静态依赖和 source pin，不能只看其中一个计数。
daemon 现在持续持有设备引用，翻译子进程也会继承。必须等待二者退出；父进程
消失不代表设备已关闭。正常卸载报告 `in use` 时检查残留进程和设备描述符，
不要强制卸载。设备引用、单独的源码模块 pin 和 hook reader 保护是不同的保证；
源码 pin 只有在全部入口失效、writer/frame 与已知队列排空后才会释放。
guest hook 没有配套 reader/drain 保护，`synchronize_rcu()` 不保证压力下热卸载。
原指针接口下，非目标线程也会先调用 selector，`exc_int3` 还读取共享 selector；
合并入口实验将 spin 的选择移入 provider，但仍保留 int3 selector 和相同的
已知调用者排空前提，不能据此推导一般 reader 已经静止。
停止 benchmark、查询不到已知 comm，只能确认已知 workload 排空，不能证明
所有 hook reader 已经静止。当前卸载流程限于可恢复实验，不是通用安全热卸载。
详细能力审查及内核修改边界见 [DESIGN 3.1](DESIGN.md#31-source-lock-and-hook-lifetimes)。
只有 daemon 已停止、执行者已排空时才可清理明确生成的 `daemon/0x*`；
不要清理未知源码、证据或用户文件。

不要在保留旧 kdlock/daemon 会话的情况下只卸载并重载源码模块。RIP 缓存不含
源码模块代际，换 TGID、重启 benchmark 或删除生成物都不使内核旧 JIT 失效。
若实验需要替换源码模块，先停止新 workload，排空旧请求、停止 daemon，按上面
顺序结束旧模块会话，再重新加载 kdlock 和测试模块、启动新的 daemon 准备翻译。
这是保留现有实验前提的整会话重建，不解决任意运行中热替换或对象释放通知。
`test_23` 的重载负例是受控例外：旧会话已经不可逆地 RETIRED、所有调用者和
writer 已排空，保留旧 provider/registry 只为证明复用地址后的原生竞争不误用
旧 JIT。它不会恢复 JIT 或并发替换源码，不能作为日常热重载操作指令。

## 虚拟机存活检查与重启

从真实宿主机进程视图检查，不把沙箱不可见误判为进程消失：

```sh
ps -aux | grep qemu-system-x86
timeout 20 ssh -o BatchMode=yes -o ConnectTimeout=5 -p 2222 root@127.0.0.1 \
  'printf VM_OK; uname -r'
```

忽略 grep 自身。进程存在且 SSH 成功才继续；SSH 无法连接或超时，按用户约定
视为 guest 崩溃/卡死，先保存串口日志，再关闭旧 VM。正常测试暂时没有日志
不等于崩溃；单纯 monitor 权限拒绝也不是 guest 故障。

```sh
tail -n 300 /tmp/qemu-serial.log
sudo pkill -9 qemu-system-x86
ps -aux | grep qemu-system-x86
```

确认旧进程完全退出后才重启，禁止两个实例共用磁盘。脚本使用相对磁盘路径，
必须先切换目录；高风险测试使用 recovery：

```sh
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

脚本前台运行 QEMU，recovery 不启用 VirtFS/VFIO，可用 savevm；normal 模式不能
假定支持快照。当前配置为 40 vCPU、28 GiB、双 NUMA，仍需每次核对实际参数。
串口在宿主机 `/tmp/qemu-serial.log`，monitor 在 `/tmp/qemu-monitor.sock`。
已有实例可能由 transient service 管理；先检查实际 QEMU/service，不另起实例。

另一宿主机终端连接 monitor：

```sh
cd /home/eric/vm/qemu-scripts
./run_vm.sh monitor
# HMP: savevm pre_kdlock_test
# HMP: info snapshots
# Ctrl-C 断开客户端；不要发送 quit（会退出 QEMU）
```

root-owned socket 可能需要 `sudo nc -U /tmp/qemu-monitor.sock`。
自动查询须让 timeout 与 nc 同权限，例如
`sudo timeout --kill-after=2s 6s nc -U /tmp/qemu-monitor.sock`；外层 timeout
只杀掉 sudo 可能遗留 root nc 并占住 monitor。
无响应时核对客户端 PID/命令，只关闭已确认由本次操作留下的连接，不杀未知
用户客户端，也不将健康 SSH 的 guest 重启。快照输出必须实际收到后才可继续。
只有 savevm 无错误且 info snapshots 列出 tag 才算确认。重启不等于 loadvm；
恢复前归档已有证据，guest /tmp 可能丢失。崩溃恢复后先检查模块与源码状态，
从低风险验证重新开始，不直接重复崩溃负载。

## 报告要求

说明实际改动、构建/测试命令和结果、是否加载模块及启用 mutex_jit、
内核错误和排空状态、未执行/失败项目、Git 版本。
本轮或历史证据必须标明来源和时间，不混用不同源码版本的通过结果。
当前批次的时间、计数和源码身份以对应 tests/bench README 链接的原始结果为准；
[VALIDATION](VALIDATION.md) 保留已有冻结版本的历史索引。
实际 JIT、上下文拒绝、纯原生对照和 JIT=0 的 RCU/ACK 探针必须分开报告；
完整矩阵通过不代表所有资源、上下文和生命周期问题已解决。

多个 native frame 的测试必须证明存活区间真实重叠，并逐 task/lock 核对 owner
与 ACK，不能仅检查 `started=completed`。`test_23` 的双队列 flow/独立 entry
边界见使用指南 6.6；它不替代全 GPR 探针或 `test_22` 的存活 RCU 读者测试。
双 frame 分支在原生 callee 中改名，两个 frame 均到达后再获取/释放各自的
原生 C；必须等两次 C 返回后才开始池压力。此时 source 仍 OPEN，C 的 owner
是 waiter 自己，A/B owner 不变且不增加 ACK；名称不能在最后 B/A ACK 前恢复。
清理包括 `kd_renamed`，不把改名 worker 误当作已退出。修改这一工作负载只选
使用指南 6.6 的相关单元和三项复杂 live；共享信号客户端未变时不重复其独立回归。
发布检查复用现有 `wait_ready()`，不要将 registry 的 `pid=0` 误当成真实 TGID。
双 frame 分支还在关闭源码准入前通过真实 mutex CALL 填满代码池，并在 CPU
8-11 的独立队列中检查新入口的未启动回退；原生 B 竞争者使用 CPU 12/13，
先核对 CPU 0-13 可用。必须保留
64 个不同块的快照、模块 ELF CALL 身份、旧镜像及后续 ACK；冷入口不算 JIT。
随后同一暂停区间还通过真实 hook 获取不同 mutex，填满 1024 个 shadow 槽；
SELFTEST 参数只控制 promotion、只读计数，不写表或改变容量。缺少 shadow 的
两个新目标请求须实际进入非目标 holder 的 Linux wait_list，并逐记录核对
原生 owner、确切 CALL 入口及回退诊断。该三人队列排空后，两个旧 frame 仍须
存活，再启动原生 B peers；它不产生额外 JIT/frame/ACK。脚本在已排空和卸载后
恢复默认 SELFTEST=0 构建，不替换加载中的镜像。该扩展仍只选相关资源/观察器
单元程序与原有三个 `mutex-parallel` 用例，具体执行流只维护在使用指南 6.6。
容量阶段与退休后重载阶段按使用指南 6.6 分开验证，不能把两轮 arrival 混计。
两名非目标 B 竞争者必须在原 frame 释放前实际进入 Linux wait_list，不以
trylock 失败或调用前标志替代排队。先核对两个单进程客户端的 pidfd/身份再发送
SIGUSR1，要求原生 interruptible 等待取消、EINTR 实际返回用户态，同一客户端
明确重试一次并再次进入 wait_list。两轮观察必须区分 phase，不能复用旧日志；
期间 source 快照保持两个 frame，原 A/B owner 不变。只取消原生 peer 的等待，
不能放弃委托 frame。共享客户端变化还须选择独立的 `native-peer-1/3`，命令在
使用指南 6.6；不再重复无取消前身。第一名竞争者完成原生 B 解锁前，第二个
frame 仍须保留自己的 B 并拒绝跨锁 trylock；四个 owner ACK 不变。脚本必须
join 原八个角色和这两名竞争者后才退休/卸载，不能忽略 `kd_native` 残留。
同一双 frame 用例还对两个原 waiter 发信号：保留 pidfd，先排空者 SIGKILL，
另一名 SIGUSR1。必须先完成前者的真实后缀和 B/A ACK，再证明该进程实际退出、
source 只剩一个 frame，才释放第二道测试门。两名 waiter 均只执行一次 ioctl；
137 只能属于先排空者，不能用预期死亡或测试 task 引用代替生命周期证据。
完整执行流及失败清理仍只维护在使用指南 6.6，不支持遗弃未完成的 frame。
`test_23` 的跨队列同 CPU 场景只应出现一个 JIT/native frame 和另一个请求的 context refusal；
检查被拒绝 entry 仍 NORMAL、没有 body，且先前 frame 保留到另一队列完成。
其命令和时间顺序见使用指南 6.7，不能当作两个 frame 的并行执行证明。
该跨队列拒绝回归使用真实满槽扩展，不先重复简单 placement。必须将
`slots=f` 的 node fallback 关联到额外请求、入口和原锁，确认它完成于原 frame
存活期间；不能以注入计数或泛化 overflow 日志代替实际节点耗尽证据。
同一复杂用例还会在观察满槽后，为另一个新请求设置已有的
`mutex_task_fail_once=1`。必须分别记录 task fallback 的身份、独立完成记录和
注入已消费，两个新请求都完成后旧 frame 才能续跑。不要将 task 的注入失败
写成真实内存耗尽，也不要将它在 A1 上尚无路由引用误写成整个 native 后缀
永远不建立其他锁的 task 记录。执行流和十个角色仍只维护在使用指南 6.7。
