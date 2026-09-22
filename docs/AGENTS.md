# kdlock 操作手册

本文只规定环境、安全边界和操作流程。执行流见
[JIT_EXECUTION.md](JIT_EXECUTION.md)，协议见 [DESIGN.md](DESIGN.md)，
测试与 benchmark 的说明、运行入口及新增结果分别维护在
[tests/README.md](../tests/README.md)、[bench/README.md](../bench/README.md)
及对应子目录 README；历史证据保留在 [VALIDATION.md](VALIDATION.md)。
根 README 只保留项目介绍和目录导航。剩余任务见 [TODO.md](TODO.md)。
主执行链、阅读顺序和手动步骤统一维护在 [PROJECT_GUIDE.md](PROJECT_GUIDE.md)，
逐文件索引维护在 [CODE_MAP.md](CODE_MAP.md)。设计及测试专题从上述入口导航，
性能优化任务统一维护在 [PERFORMANCE_PLAN.md](PERFORMANCE_PLAN.md)；不要建立平行清单。

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
   2026-09-19 用户进一步授权本轮普通 mutex caller-clobber；从 `kdclobber1`
   派生独立 `kdclobber2`，保留旧内核、基线与缓解/帧指针配置。
5. 不扩展两元素 wrapper 输入 ABI，不恢复已删除的 futex 执行入口。
6. 2026-09-22 用户授权持续管理本地 Git：效果较好的改动，以及完成相关验证的
   较大改动，应及时更新对应文档并提交，不再等待逐次提交指令。按独立、可回退
   的改动组织提交，具体流程见下方“Git 版本与回退”。提交前核对差异、测试证据
   和文档；性能收益须有实测，不能把历史结果记为本次重跑，也不能把未通过的
   主功能写成已完成。
7. 文档按职责维护单一入口。旧验收只保留关键结果与证据索引，详细调查通过
   Git 历史追溯；不要持续追加重复实现说明或保留已失效的下一步指令。
   用户于 2026-09-15 再次明确：benchmark/test 信息不写入根 README，写入
   各自目录的 README；不得把运行命令、模式表或成绩重新放回根文档。
8. 测试与 benchmark 的 Demo 内核临界区模块统一放在 `workload_modules/`，
   按负载分子目录；客户端、运行器与结果处理放在 `bench/` 或 `tests/`。
   生产 provider 的专用观察器/组件自测继续放在 `tests/kernel/`，不混入 Demo 负载。
9. 用户于 2026-09-16 明确：测试代码按用途放入子目录，每次修改只测试基础
   简单功能及直接相关功能，不运行全量测试。`make -C tests/unit run` 默认只跑
   两个基础 C 程序；用 `PY_TESTS` 增加受影响项，`run-all` 只在用户明确要求时用。
   不因目录整理或共享文件改动自动扩大到完整单元套件、复杂 live 矩阵。
   本条取代此前首次全量验收及默认复杂用例优先的约定。
10. 用户于 2026-09-17 明确：能复用的状态不复制。一次请求的 waiter 与 combiner
    共用寄存器包和执行 frame，通过指针/索引及状态交接使用权；优先预分配，
    不以整包复制、整对象清零或新增全局锁解决生命周期问题。初始寄存器保存、
    最终 CPU 恢复及必须同时保留的独立状态另行说明。共享对象必须存活到最后
    一个使用者结束；node 可复用、waiter 被唤醒均不等于 frame 可回收。
    这是后续实现约束，当前剩余复制及改造边界见
    [共享请求设计](design/frames.md#911-reuse-before-copy-contract)。

2026-09-22 用户明确：当前 KD spin API 采用普通 `raw_spin_lock` 语义，
不默认保存、关闭或恢复 IRQ/BH；保留获取所需抢占保护与最终退休顺序。
irqsave/bh 属于另行选择的调用语义，不能默认加在普通锁路径上。

## Git 版本与回退

1. 完成一个有明确收益或较大规模的改动后，先完成基础及直接相关验证，再将
   代码、匹配测试和当前行为文档一起提交；不要连续叠加多个未经提交的有效改动。
   执行路径/协议写入对应设计文档，测试与性能证据写入各自 README 和结果报告。
   提交说明记录改动目的、验证结果和限制；交付时报告提交哈希。
2. 开始下一项较大或性能实验前，确认当前已验证状态有可定位的提交；必要时
   使用独立分支保留实验。较大实验需要中途保存时可提交明确标注的实验版本，
   注明尚未验证的内容，不将其标为已验证基线。原始日志、大型构建产物继续按
   现有忽略/归档规则保存，在文档中记录路径及哈希。
3. 用户已授权的本地提交、分支/标签管理和任务范围内回退可直接执行，无需逐次
   确认。提交前查看工作树及暂存区，只纳入已核对的本次文件，保留无关用户改动。
4. 回退优先使用 Git：已提交的独立改动使用 `git revert <commit>` 保留历史；
   只需恢复局部实现时，先核对差异，再用 `git restore --source=<good-commit> -- <paths>`
   恢复指定代码及匹配测试/文档，并创建新的回退提交。不要用全树重置覆盖未知
   改动，不为回退改写已有历史。切换运行输入前仍须遵守用例停止与排空顺序。
5. 回退后记录原因、来源提交和恢复范围，保留失败实验及其成绩；按受影响范围
   验证并提交恢复状态。Git 只恢复仓库内容，guest ext4 副本、已加载模块和
   忽略目录中的产物仍须按现有同步、构建、退休流程处理。不能把旧版成绩记为
   回退后的新测结果，也不因提交或回退自动扩大到全量测试/性能矩阵。

## 环境边界

| 操作 | 位置 |
| --- | --- |
| 读写源码、静态格式检查、Git、归档、控制 VM | 宿主机 `/home/eric/vm/vm-shared/kdlock` |
| 只读离线归档校验 | 宿主机或 guest；不执行用例或访问 JIT 设备 |
| 编译、单元测试、模块、daemon、benchmark | guest `/root/host_fs/kdlock` |
| SSH | `root@127.0.0.1:2222` |
| 当前默认内核源码/build | `/root/linux-6.1.159-kdclobber2`；原 `/root/linux-6.1.159` 和 `kdstatic2` 基线保留 |
| QEMU 脚本 | 宿主机 `/home/eric/vm/qemu-scripts/run_vm.sh` |

不要在宿主机执行 make、模块加载、daemon 或 benchmark。
当前 provider 要求 spin 与 mutex 两组 clobber v1 接口，不再自动支持旧内核；旧树仅用于恢复和
对应历史源码的重现。普通 mutex 的接入在独立 `kdclobber2` 中构建和验证，`kdclobber1` 及其捕获基线保留。
新 build 实际位于 `/mnt/kdlock-builds/` 辅助盘，`/root/linux-6.1.159-kdclobber2` 为链接。
2026-09-21 按用户要求清理四套旧树的可重建编译中间文件，源码、启动文件和
捕获基线保留；当前 build 与全部测试证据未清理，范围和核验见
[存储清理记录](PROJECT_GUIDE.md#36-2026-09-21-存储清理记录)。
normal 模式用 9p 共享源码，不需要同步；recovery 模式同一路径是 guest ext4，
不会自动同步。比较单文件 SHA256，只 scp 变化文件，必要时先建对应子目录。
禁止移动、递归覆盖或清空 `/root/host_fs`；避免两侧同时编辑。

现有 baseline 不是新内核修改。不能只凭 `uname -r` 判断兼容性；
只读核对命令在 guest 执行：

```sh
cd /root/host_fs/kdlock
python3 bench/spin_cacheline/kernel_identity.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

按实际运行内核选择对应 source/build/baseline；原 `6.1.159` 的核验命令见
[手动指南 3.2](PROJECT_GUIDE.md#32-进入-guest-并检查基线)。上述命令核对所选
捕获材料、源码/接口文件、配置、构建文件及 live Build ID，
不代替完整源码扫描或运行配置检查。另查 `nokaslr`、voluntary 动态抢占、
CPU/NUMA 拓扑和挂载类型。具体身份与重建限制见
[baseline](../kernel_baseline/README.md)。不匹配时先查原因，不能自动改内核。

## 验证顺序

1. 宿主机检查 Git 和 VM，核对并按需同步源码哈希。
2. guest 确认没有在跑的 benchmark、daemon、旧模块及在途请求。
3. 新环境按 [手动指南 3.3](PROJECT_GUIDE.md#33-检查依赖与空闲状态) 安装固定版本
   的 Python 运行依赖，将 venv/bin 放到 PATH 首位供测试和 daemon 继承；不升级
   全局 pip 包。运行 `make -C tests/unit run` 的基础检查，用 `PY_TESTS` 增加
   直接受影响的单元测试。修改分析器时按需选择独立 admission audit。
   必需依赖缺失、SKIP 或编译失败不能作为通过。
4. 只有改动需要内核运行验证时才构建并选择相关 live 用例；先用基础简单
   功能定位，复杂场景按本次改动需要选取，不默认执行整套。
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
验证范围以基础简单功能和本次受影响功能为限；共享代码或内核基线变化也先
选择相关检查，不自动触发全量回归。全量需用户明确要求，未重跑项标明历史结果。

当前步骤见 [PROJECT_GUIDE](PROJECT_GUIDE.md)，选择入口见 [tests](../tests/README.md)。
`tests/run_all.sh` 无参数只列出；当前仅 provider/device 生命周期 case，JIT=0。
实际 JIT 使用 [直接 API 运行器](../bench/tclock_compare/README.md)的
plain/nested/early，按修改选择，不自动跑性能矩阵。旧 hook 套件及操作专题已删除。
保留的日志 oracle/生产代码 fixture 不等于实际 JIT 验证。

### 验收与清理

发布 NORMAL 不等于实际执行。JIT 正例必须取得 wrapper 返回后的正文证据，
核对入口/锁身份、业务数据、IRQ/preempt、队列、ACK 和退休。拒绝、JIT=0 原生
对照和真实 JIT 分开报告；observe 的竞争正例不得以不代理完成代替。
保留命令、环境、退出码、源码/ELF 哈希、内核身份和 dmesg。失败且排空也归档；
未排空时明确证据不完整，不读取仍在变化的目录。历史归档仅做离线一致性校验，
不执行其中代码，也不因日志自洽而宣称本次重跑或来源真实。

先停新 workload，等待已有调用及翻译者结束，再执行 source retire。retire
返回 EBUSY 时保留 pins，继续排查在途请求，不强制卸载或重新开放入口。
成功后先卸载 workload，再卸载后端/provider。不要在旧 provider/JIT 会话中
只换载源码模块；RIP key 没有代码代际，改进程名或删除生成物也不会让旧 JIT 失效。
来源 pin、设备引用、实际物理 owner、最后 ACK 和 frame 退休是不同生命周期。
禁止把热表淘汰、node 复用或 waiter 唤醒当成 owner/frame 已消失。
全局 hook 安装目前停用；未来恢复它仍需单独的 reader/drain 契约。

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

2026-09-21 用户明确：后续性能测试对象固定为 Linux 原生、TCLock 和当前 kdlock，
不再运行旧版 kdlock 对照。2026-09-22 用户进一步指定：后续性能每配置默认两轮，
三方各取有效样本中的最大吞吐，ns/op 使用同一获选会话；比值按各自最大值计算。
保留全部原始样本、有效性/排空检查与获选会话身份，历史五轮中位数不重写。
使用三方直接 API 入口；旧 O/N 脚本与采样器组件对照入口已删除，
只从固定 Git 版本或冻结归档追溯历史。已有报告不改写为新成绩，具体参数与统计口径见 [bench](../bench/README.md)。

说明实际改动、构建/测试命令和结果、是否加载模块及启用 mutex_jit、
内核错误和排空状态、未执行/失败项目、Git 版本。
本轮或历史证据必须标明来源和时间，不混用不同源码版本的通过结果。
当前批次的时间、计数和源码身份以对应 tests/bench README 链接的原始结果为准；
[VALIDATION](VALIDATION.md) 保留已有冻结版本的历史索引。
实际 JIT、上下文拒绝、纯原生对照和 JIT=0 的 RCU/ACK 探针必须分开报告；
完整矩阵通过不代表所有资源、上下文和生命周期问题已解决。

多个 native frame 的证据必须证明存活区间真实重叠，按 task/lock 核对 owner 与 ACK；
不能只看 started=completed。真实耗尽与注入失败分开，信号/退出不能遗弃未完成
frame。旧测试操作细节仅见匹配 Git 历史，不是当前 live 的运行指令。

2026-09-22 用户授权性能回退：本轮为定位约20%竞争退化允许隔离热表候选，
正式成绩仍是 Linux/TCLock/当前KD、两轮取最大值。热表已局部恢复到最佳已测
分类型256槽实现（本地busy、复用已有pin）；普通spin的IRQ语义和正确性修复保留。
宿主QEMU vCPU已按编号一对一固定到CPU0..39，前20个对应宿主NUMA0；重启后
必须重新核对映射，不能只凭guest绑核声称物理同节点。证据见[回归报告](../bench/tclock_compare/results/20260922-performance-recovery.md)。

2026-09-22 后续512槽直接映射实验因性能下降再次按用户要求撤回；
当前代码恢复 `bf16b10` 的256桶/256记录实现。实验结果仅保留为历史，
见[记录](../bench/tclock_compare/results/20260922-directhash-v2-performance.md)。
