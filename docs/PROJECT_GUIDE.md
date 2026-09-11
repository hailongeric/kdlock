# 代码阅读与手动运行指南

本文面向第一次逐文件阅读、手动操作当前 checkout 的读者。协议细节仍以
[DESIGN](DESIGN.md)、[寄存器 ABI](JIT_REGISTER_ABI.md) 为准；每个复杂测试的
执行流和判定条件见 [JIT_EXECUTION](JIT_EXECUTION.md)，历史证据只维护在
[VALIDATION](VALIDATION.md)。不要把本文的操作示例当作新测试结果。

## 1. 当前进展

截至 **2026-09-11**：

- 已实现 x86-64 spin/mutex 的原生锁互斥、私有代理队列、JIT 执行、嵌套控制、
  allowlist hostcall，以及普通 CALL miss 后原 waiter 从当前状态原生完成后缀。
- mutex 正例要求 `mutex_jit=1`。真实 owner 保留原锁，waiter 通过 unlock/ACK
  完成；没有 owner handoff、入口重放或内存事务回滚。
- 最近完整矩阵是 **9 月 9 日的 67/67**；最近局部 live 是 **9 月 10 日的
  24/24**，其中 12 个实际 JIT 正例、12 个 native-only 负例。各自有独立源码冻结。
- 静态 core/module per-CPU 地址筛查已实现。动态指针、并发改写、任意上下文
  对象生命周期仍不完整，不能声称所有不适合代理的临界区都会被拒绝。
- 新增访问时检查及其原生出口尚未实现，等待局部条件码保存/恢复的范围确认。
  通用 flags/特殊指令语义及不可变 JIT 版本继续延期；详见 [TODO](TODO.md)。
- 9 月 11 日的注释整理未改变可执行语句，guest 构建和六个相关单元程序通过，
  没有加载模块或重跑 live。各轮结果见 [验证记录](VALIDATION.md#reading-handoff)。
  已有模式仍可按实验前提运行；新功能的阻塞不等于当前模块不能启动。

## 2. 先认识执行链

推荐先按这条链读代码，再查第 5 节的完整文件索引：

```text
bench/klock_test.c                      用户线程 -> ioctl
  -> klock_module/klock_module.c        按 mode 进入真实原生锁临界区
  -> guest 已有 hook                    不在本仓库重新实现 Linux 锁
  -> kernel_module/kd_main.c            判断新目标或仍有在途引用的任务
  -> kernel_module/kd_lock.c            原锁、私有 gate、hotlock/entry 路由
  -> kd_spinlock.c / kd_mutex.c         排队、持有原锁、选择 combiner
  -> exe.c + kd_exec.c                  就绪检查、frame、寄存器与锁记录
  -> include/wrapper.S + asm/jit.S      执行翻译指令
  -> 控制调用 / hostcall / native 后缀  依据出口协议继续
  -> 真实 owner unlock + ACK            排空并恢复 waiter

翻译侧：sys.c /dev/kd_dev -> daemon/daemon.c
  -> disassem/device_session.py         同一设备 lease、source pins、CAPS
  -> memread.py + disassem.py           读取、解码、补齐 CFG、选择 JIT 范围
  -> context_policy.py                  上下文/地址/锁边界准入
  -> translation.py + 各 lowerer        虚拟寄存器/栈到实际汇编
  -> wrapper.S + jit.S -> jit.bin       组装、上传，未来请求才可使用
```

阅读时区分四个身份：**waiter** 是原调用线程；**combiner/executor** 是实际执行
代理的线程；**physical owner** 是 Linux 原锁的持有者；**logical task** 是 frame
记录的 waiter。后两者不能混为同一 `current`。`kd_exec_frame.parent` 表示本 CPU
的物理 frame 嵌套，远端逻辑关系还要看 `resume_target`。

代码注释重点说明文件用途、入口/出口、引用和 ACK 的最后访问，已有充分注释不重复
添加。C/Python/汇编中的英文名称与符号保持一致，中文解释集中在本文和协议文档。
`tests/kernel/` 中的 C 多为 include 片段，不是可以单独 `insmod` 的模块。

## 3. 一步一步运行

### 3.1 确认宿主机与 guest

宿主机 checkout 是 `/home/eric/vm/vm-shared/kdlock`；guest checkout 是
`/root/host_fs/kdlock`。**模块编译、单元测试、daemon、benchmark 均只在 guest
执行**。不要因宿主机也能看到源码就在那里运行 `make` 或 `insmod`。

宿主机先执行：

```bash
cd /home/eric/vm/vm-shared/kdlock
ps -aux | grep '[q]emu-system-x86'
timeout --kill-after=5s 20s ssh -o BatchMode=yes -o ConnectTimeout=5 \
  -p 2222 root@127.0.0.1 'uname -r'
```

进程存在且 SSH 正常时使用现有 VM。确认没有旧 QEMU，才在另一个宿主机终端启动：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

该脚本确实支持 `recovery`，以前台方式运行 QEMU，使用相对磁盘路径；不要从其他
目录调用，不要同时启动两个实例。它不自动恢复某个快照。SSH 超时的日志保留、
强制关闭旧 VM 和重新启动步骤见 [VM 故障处理](AGENTS.md#虚拟机存活检查与重启)。
权限错误或宿主机沙箱看不到进程，不等于 guest 崩溃。

宿主机另开 monitor，或在 socket 为 root 所有时用 `sudo nc -U /tmp/qemu-monitor.sock`：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh monitor
```

在 monitor 中输入 `info snapshots`，确认真实可用的 tag；没有快照时，在 guest
空闲、没有测试模块的状态下执行 `savevm pre_kdlock_manual`，再次查询确认成功。
使用 Ctrl-C 断开 monitor 客户端，**不要输入 `quit`**，否则会关闭 VM。

### 3.2 进入 guest 并检查基线

```bash
ssh -p 2222 root@127.0.0.1
bash
cd /root/host_fs/kdlock
findmnt -T /root/host_fs/kdlock
python3 kernel_baseline/verify.py --source /root/linux-6.1.159 --build --running
cat /proc/cmdline
cat /sys/kernel/debug/sched/preempt
lscpu -e=CPU,NODE,ONLINE
```

后续 guest 示例使用 **Bash**，每一步失败都应先停下排查。期望基线是 Linux
`6.1.159`、Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`，启动参数含
`nokaslr`，动态抢占选择为 `(voluntary)`；现有用例按 40 个 CPU、两个 NUMA 节点
布置角色。缺少文件、CPU 不足或基线不匹配不是 SKIP/PASS，不要自行重建 guest 内核。

normal 的 9p 源码是共享的，不需要搬动。recovery 同名路径是 ext4，修改后要比较
两侧 SHA256，只传输变化文件。例如宿主机比较并按需同步一个文件：

```bash
cd /home/eric/vm/vm-shared/kdlock
sha256sum kernel_module/kd_main.c
timeout --kill-after=5s 20s ssh -o BatchMode=yes -o ConnectTimeout=5 \
  -p 2222 root@127.0.0.1 'sha256sum /root/host_fs/kdlock/kernel_module/kd_main.c'
# 仅在哈希不同且 guest 没有运行测试时执行：
scp -P 2222 kernel_module/kd_main.c root@127.0.0.1:/root/host_fs/kdlock/kernel_module/
```

不要递归覆盖/清空 `/root/host_fs`，也不要依赖旧 `/tmp` 辅助脚本才能操作项目。

### 3.3 检查依赖与空闲状态

在 guest 项目根目录执行：

```bash
command -v gcc make objcopy objdump readelf timeout taskset python3
python3 -c 'import miasm, elftools; from importlib.metadata import version; print(version("miasm"), version("pyelftools"))'
python3 -c 'import sys; sys.path.insert(0, "tests"); import regression; regression.check_idle(); print("guest idle")'
bash tests/run_all.sh --list
```

当前验证使用 miasm `0.1.5`。依赖以 guest 的已验证环境为准，不需要在宿主机装
翻译器。`check_idle` 报错时先查已存在的进程/模块，不要直接强卸载。
无参数或 `--list` 只列清单，不会启动负载。测试脚本可能调整 guest 的
`kernel.randomize_va_space`、`kernel.numa_balancing` 并清理生成目录，因此只用实验 VM。

### 3.4 构建

```bash
make -C kernel_module W=1
make -C klock_module W=1
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
```

得到 `kernel_module/kdlock_km.ko`、`klock_module/klock_module.ko`、`daemon/daemon`、
`bench/klock_test`。先构建 provider，再构建依赖它导出符号的 workload。
默认不启用 `KDLOCK_SELFTEST`、`KDLOCK_NUMA` 或第二源码模块；相关复杂驱动会自行
选择并在结束后恢复默认构建。不要任意沿用另一个实验的编译开关。
当前 `W=1` 构建仍有手写恢复/切栈汇编及测试 CLD 的 objtool warning，构建成功
不表示这些语义已经修复。若出现新的 error 或不同 warning，先保留日志排查。

首次环境验收可以运行以下两条；基础已验收且环境没有改变时不必每轮重跑：

```bash
make -C tests/unit run
python3 tests/audit_context_spills.py
```

只改某类代码时，按 [增量回归选择](JIT_EXECUTION.md#7-分层与增量回归) 选相关
unit 和复杂 live。单元测试中的用户态机器码执行也留在 guest，不计为内核 JIT。

### 3.5 按用例手动运行（推荐）

先预览，不执行：

```bash
bash tests/run_all.sh --suite core --dry-run
bash tests/run_all.sh --case mode-4 --dry-run
```

确认上面的恢复快照后，才在 guest 设置变量并一次运行一项：

```bash
export KDLOCK_RECOVERY_CONFIRMED=1
RUN_DIR="$(mktemp -d /tmp/kdlock-manual-case.XXXXXX)/run"
bash tests/run_all.sh --case mode-4 --timeout 300 --output "$RUN_DIR"
```

该命令执行真实的 mutex 嵌套竞争，显式启用并读回 `mutex_jit=1`，处理构建、模块、
daemon、角色启动、实际 JIT 判定和排空。退出非零就查看它打印的证据目录，先不要
接着运行下一项。不是只生成 `jit.bin` 就结束。

根据想看的机制，**选择**下列入口，不要求全部连续运行：

| 目的 | guest 命令参数，接在 `bash tests/run_all.sh` 后 |
| --- | --- |
| spin 的 service 出入 | `--case mode-2` |
| mutex 的 service 出入 | `--case mode-5` |
| 嵌套 B 的独立竞争 | `--case mode-8` |
| mutex CALL miss 后寄存器续跑 | `--case registers-4-3` |
| 学习两层、跨模块 helper 后 JIT 及容量续跑 | `--case native-mutex-depth` |
| 两个 mutex native frame 同时存活 | `--suite mutex-parallel` |
| 上下文不适合代理时的原生拒绝 | `--suite admission` |
| 五个不重复的日常主用例 | `--suite core` |
| 特意观察单锁基本流程 | `--case mode-0` 或 `--case mode-3` |

`core` 是 mode 2/7/8/4/5，不是 0 到 8 的全模式扫描。mode 0/1/3 等被覆盖诊断
仍可显式点选，默认不会再附加；`extended` 也不重复这十一项已登记的被覆盖诊断。
mode 6 的单 frame 三锁等独立协议仍保留。不要直接运行 mode 9 故障路径来学习启动。

运行器输出目录内执行离线校验：

```bash
# 沿用上面设置的 RUN_DIR；换终端后需重新赋值为本次运行器目录。
python3 tests/verify_evidence.py "$RUN_DIR"
```

这是检查已保存证据，不会重跑 JIT，也不证明日志来源可信。原生负例、纯原生对照
和实际 JIT 正例是三类不同结果。

### 3.6 拆开观察模块、daemon 和负载（可选）

本节只用于理解组件，展示 **mode 3** 的一条简单人工流程，不替代上一节完整用例
的协议 oracle，也不是日常新增 smoke。不要与 `run_all.sh` 或其他实验同时运行。
所有命令在同一 guest Bash 会话中执行；开始前必须完成 3.1-3.4 的检查。
不要直接在交互 shell `source tests/common.sh`：它依赖驱动的 `$0` 并安装卸载 trap。

保存日志，确认全新会话后加载 provider 和 workload：

```bash
cd /root/host_fs/kdlock
RUN_DIR=$(mktemp -d /tmp/kdlock-manual.XXXXXX)
dmesg > "$RUN_DIR/dmesg.before.log"
dmesg -C
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
insmod kernel_module/kdlock_km.ko target_process=klock_test mutex_jit=1
insmod klock_module/klock_module.ko
cat /sys/module/kdlock_km/parameters/mutex_jit
python3 disassem/device_session.py status
python3 disassem/device_session.py capabilities
```

应读到 `mutex_jit=1`、source `state=0`，能力包含 `mutex_stack_bytes=256` 和
`percpu_module_bytes=8192`。`state=1/2` 的旧会话不能重新启动 daemon 使用。
两条 `insmod` 应逐条执行并检查返回值；provider 加载失败时不要加载 workload。
这些值证明配置/能力，不证明执行。启动 daemon 会替换其管理的生成工作区，先保留旧证据。

```bash
cd daemon
set +m
KD_JIT_BODY_WITNESS=1 setsid ./daemon --mode 2 --verbose > "$RUN_DIR/daemon.log" 2>&1 &
DAEMON_PID=$!
cd ..
timeout --kill-after=5s 10s bench/klock_test 1 1 1 1 3
sleep 1
timeout --kill-after=5s 20s bench/klock_test 1 12000 10 1 3
```

`set +m` 关闭当前 Bash 的交互 job control，使后台 `setsid` 不因进程组首领身份
另行 fork，后面的 `$!` 才对应 daemon 的会话/进程组。第一波跨过 hotlock 启动窗口，
第二波是单线程采样/注册/翻译准备，不应作为 JIT
竞争验收。查看 daemon 日志，等待它完成本条目的翻译。随后选取唯一产物：

```bash
find daemon -type f -path '*/asm/jit.bin'
mapfile -t IMAGES < <(find daemon -type f -path '*/asm/jit.bin')
test "${#IMAGES[@]}" -eq 1
ASM_DIR=$(dirname "${IMAGES[0]}")
python3 tests/mutex_signal_protocol.py ready --artifact "$ASM_DIR" \
  --output "$RUN_DIR/published.json"
```

若还没有产物，先看日志并等待翻译完成后重新执行本段；若多个产物，不要任取第一项，
应排查旧会话或意外 workload。`test`、翻译或 `ready` 失败时不要进入下一步。
`ready` 有界等待对应 RIP/TGID 的 mutex NORMAL 状态，避免文件生成早于上传。

在负载之间的空闲边界停止 daemon 进程组并等待翻译子进程退出，再进行竞争，避免
本人工观察过程中并发重编译。先确认 PID/进程组确实属于刚启动的 daemon：

```bash
ps -p "$DAEMON_PID" -o pid,pgid,args
if test "$(ps -p "$DAEMON_PID" -o pgid= | tr -d ' ')" = "$DAEMON_PID"; then
    kill -TERM -- "-$DAEMON_PID"
    wait "$DAEMON_PID"
else
    printf 'STOP: inspect daemon identity before cleanup\n' >&2
fi
python3 disassem/device_session.py status
```

daemon 被 SIGTERM 结束时 `wait` 可返回 143；这与后续 benchmark 失败不同。
必须确认没有翻译子进程、status 的 `writers=0`；**此时不要 retire**，因为还要执行
已经发布的 JIT。随后运行已编译条目的竞争：

```bash
timeout --kill-after=5s 30s bench/klock_test 8 1 1000000 1 3 > "$RUN_DIR/workload.log" 2>&1
dmesg > "$RUN_DIR/dmesg.execution.log"
grep 'JIT body witness:' "$RUN_DIR/dmesg.execution.log"
grep 'mutex JIT delegation ok' "$RUN_DIR/dmesg.execution.log"
cp -a "$ASM_DIR" "$RUN_DIR/asm"
```

必须核对 marker 的 entry/lock 是本次条目，且 `body=1`。没有 marker 就不能声称
动态翻译指令执行了；仅有 `begin delegate`、`install JIT chunk`、普通返回码也不够。
此观察仍需结合保护数据、失败计数和卸载时的最终统计；严谨验收使用 3.5 的驱动。

### 3.7 排空、保存和卸载

人工流程结束时，先等待所有自己启动的 benchmark 正常返回、daemon/翻译者退出。
检查 `pgrep -af 'klock_test|daemon|disassem.py'` 的真实身份，不能凭匹配字符串就杀掉
未知进程。停止一个持锁或借锁 waiter 可能使 owner 无法收到 ACK，不能以强杀代替排空。

```bash
python3 disassem/device_session.py status
(
    set -e
    python3 disassem/device_session.py retire
    rmmod klock_module
    rmmod kdlock_km
)
dmesg > "$RUN_DIR/dmesg.final.log"
grep -E 'final counter:|kd_exec|kd_native stats:|jit_success|cs_state' "$RUN_DIR/dmesg.final.log"
python3 -c 'import sys; sys.path.insert(0, "tests"); import regression; regression.check_idle(); print("guest idle")'
```

`retire` 失败（例如 EBUSY）就停在该步骤，继续查 writer/frame/队列持有者，不执行
后面的 `rmmod`。上面的子 shell 用 `set -e` 保证失败即停止卸载链，不退出当前
交互会话；不要去掉这个保护。retire 不可撤销；成功后新实验需要完整卸载/重新加载会话。
仅重启 daemon、只重载 workload 或删除生成物都不能重置旧 JIT 会话。
若通过复杂驱动加载了 `kd_depth_source`，卸载顺序是 workload、helper、provider；
用相应驱动完成清理，不在本 mode 3 示例里手工添加它。

核对 protected-state 完整性、owner/ACK、失败计数及 `BUG:`、panic、lockup 等错误。
上例在每条负载恰好运行一次的前提下，最终 counter 是 `1 + 12000 + 8 = 12009`；
它单独正确也不是 JIT 证据。当前卸载流程仅适用于可恢复、已排空的实验，不是通用
安全热卸载。人工目录没有自动运行器的完整 manifest，不要用离线 verifier 冒充完整归档。

## 4. 产物与参数怎么读

| 对象 | 含义和用法 |
| --- | --- |
| `/dev/lock_dev` | benchmark ioctl 入口，不接收 JIT 二进制。 |
| `/dev/kd_dev` | 注册表快照、代码上传、source/CAPS 控制；不要手写任意 payload。 |
| `target_process=klock_test` | 新目标按 task comm 匹配；改进程名可能使新请求不再代理。 |
| `mutex_jit=1` | 显式启用 mutex JIT，默认 0；不代表代码已翻译或已执行。 |
| `KD_JIT_BODY_WITNESS=1` | 翻译时加入返回后可观测的 body 标记；不能追溯修改旧产物。 |
| daemon `--mode 1/2` | 分别是 `daemon/<RIP>/`、`daemon/<RIP>/<tgid>/` 工作区布局。 |
| benchmark 参数 | `线程数 每次ioctl的CS循环数 CS工作量 每线程ioctl次数 mode [role-base]`。 |
| `callee_table.txt` / `ij_table.txt` | 学习的 CALL/IJ 目标；由 daemon 维护，不是随意开放的白名单。 |
| `asm/jit.S` / `jit.bin` / `bin.txt` | 生成汇编、机器码、反汇编；存在不等于已上传或执行。 |
| `.ko`、`.o`、`.mod*`、`Module.symvers`、`modules.order` | guest Kbuild 产物，不手工加注释或同步回宿主机覆盖源码。 |
| `daemon/daemon`、`bench/klock_test`、unit 可执行文件 | 本地构建产物，不是要修改的 C 源文件。 |
| `__pycache__`、`.ruff_cache` | 工具缓存；不是项目实现或验收证据。 |
| `/tmp/kdlock-*` | 每次运行的外部证据/临时目录；不要将其他 freeze 的 PASS 混入本次。 |

常见停点：找不到设备先检查加载；无翻译先查目标名、promotion、daemon、CAPS 和
source 错误；`CONTEXT_NATIVE_ONLY` 是拒绝，不是翻译成功；
`CONTEXT_SCREENING_ONLY` 是已知缺口告警，不是访问时保护；`in use`/EBUSY 先查引用，
不强卸载。手动直接调用翻译器的参数及设备 lease 边界见 [daemon 文档](../daemon/README.md)，
通常由 daemon 发起翻译，避免漏掉布局、lock kind 或 source session。

## 5. 完整目录与文件索引

以下覆盖当前维护的源码、脚本、构建入口和基线材料。生成文件按第 4 节分类，不逐个
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
| [TODO.md](TODO.md) | 已完成部分、未完成轨道、延期与阻塞。 |
| [VALIDATION.md](VALIDATION.md) | 按时间和源码冻结记录真实结果，不替代运行指南。 |
| [PROJECT_GUIDE.md](PROJECT_GUIDE.md) | 本文：逐步操作、阅读顺序和文件索引。 |

### 5.2 生产模块 `kernel_module/`

| 文件 | 阅读用途 |
| --- | --- |
| [Makefile](../kernel_module/Makefile) | provider 对象组成、SELFTEST/NUMA 开关、guest Kbuild。 |
| [kd_main.c](../kernel_module/kd_main.c) | 初始化/逆序退出，目标与在途任务 selector，hook 发布。 |
| [kd_lock.c](../kernel_module/kd_lock.c) | hook 路由、原生操作适配、mutex shadow 查找。 |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | 有界采样与 promotion，尚不代表 JIT 就绪。 |
| [sys.c](../kernel_module/sys.c) | 设备 open/read/write/ioctl、CAPS、退休协议。 |
| [exe.c](../kernel_module/exe.c) | RIP 注册、代码池、wrapper 退出分派、控制/服务处理。 |
| [kd_exec.c](../kernel_module/kd_exec.c) | frame/锁 ledger、远端关系、native 请求与 owner ACK。 |
| [kd_source.c](../kernel_module/kd_source.c) | source pin、writer/frame lease、终止式退休。 |
| [kd_spinlock.c](../kernel_module/kd_spinlock.c) | spin 排队、嵌套代理、物理 shadow 栈与恢复桩。 |
| [kd_spin_gate.c](../kernel_module/kd_spin_gate.c) | 原锁 L 与私有调度 S 分离，真实 owner/hold。 |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c) | origin ticket、代际、task/CPU 引用与借用生命周期。 |
| [kd_mutex.c](../kernel_module/kd_mutex.c) | mutex 节点池、combiner、原生 owner、waiter 续跑。 |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | acquisition task 引用、rename 后路由及 RCU 回收。 |

### 5.3 共享接口 `include/`

| 文件 | 阅读用途 |
| --- | --- |
| [exe_info.h](../include/exe_info.h) | daemon/kernel 共用 entry、状态、代码块和上传布局。 |
| [exe.h](../include/exe.h) | C 执行器接口及返回值；区别于 wire/wrapper 状态。 |
| [kd_exec.h](../include/kd_exec.h) | frame、ledger、远端状态及不变量辅助 API。 |
| [kd_call.h](../include/kd_call.h) | PENDING/已完成控制 CALL 的目标、SP、返回 token 校验。 |
| [kd_lock.h](../include/kd_lock.h) | hook 和原生锁辅助声明。 |
| [kd_hotlock.h](../include/kd_hotlock.h) | 采样状态与 promotion 接口。 |
| [kd_mutex.h](../include/kd_mutex.h) | 私有 mutex gate/node 布局和容量。 |
| [kd_spinlock.h](../include/kd_spinlock.h) | spin node/队列与 JIT 上下文布局。 |
| [kd_spin_gate.h](../include/kd_spin_gate.h) | 原锁 gate 与物理 hold 的代际约束。 |
| [kd_spin_entry.h](../include/kd_spin_entry.h) | hook/virtual ticket 与 origin ref。 |
| [qspinlock_i.h](../include/qspinlock_i.h) | 私有调度字的 qspinlock 风格位布局/辅助宏。 |
| [kd_segment.h](../include/kd_segment.h) | 在 origin CPU 记录 kernel GS base。 |
| [kd_source.h](../include/kd_source.h) | source 生命周期内部接口。 |
| [kd_source_api.h](../include/kd_source_api.h) | source/CAPS ioctl 常量和固定布局。 |
| [kd_hostcall.h](../include/kd_hostcall.h) | 服务 ID 和安全属性定义。 |
| [kd_hostcalls.def](../include/kd_hostcalls.def) | 唯一服务清单，目前为两个 ktime 服务，不是任意 printk。 |
| [asm_head.h](../include/asm_head.h) | pt_regs 与 wrapper 私有槽的汇编偏移。 |
| [wrapper.S](../include/wrapper.S) | 装载/回写寄存器，包含生成的 jit.S；flags 不持久化。 |
| [sys.h](../include/sys.h) | 设备初始化/退出接口。 |
| [utils.h](../include/utils.h) | 日志辅助，不是成功判定器。 |

### 5.4 翻译器 `disassem/`

| 文件 | 阅读用途 |
| --- | --- |
| [disassem.py](../disassem/disassem.py) | CLI 和翻译总流程；解码、准入、发射、组装。 |
| [device_session.py](../disassem/device_session.py) | lease/source pin/CAPS；可直接执行 status/capabilities/retire。 |
| [memread.py](../disassem/memread.py) | 从 kcore 的 ELF 映射读取固定窗口和冷分支。 |
| [context_policy.py](../disassem/context_policy.py) | 符号/静态 per-CPU 范围、数据流、JIT 范围与锁深度。 |
| [context_memory.py](../disassem/context_memory.py) | 有界顺序 byte/word 事实、别名、clobber；不是实时内存快照。 |
| [context_guards.py](../disassem/context_guards.py) | 正文前的入口 disjointness 条件，不是访问时 guard。 |
| [translation.py](../disassem/translation.py) | 单条指令在普通/特殊 lowerer 间分派。 |
| [normal.py](../disassem/normal.py) | 普通 operand、地址和寄存器映射。 |
| [special_inst.py](../disassem/special_inst.py) | CALL/RET/虚拟 PUSH/POP/控制指令。 |
| [conflict.py](../disassem/conflict.py) | 虚拟特殊寄存器到物理 scratch/spill 的映射。 |
| [indirect_jump.py](../disassem/indirect_jump.py) | 有界返回图与 learned IJ 分发表。 |
| [hostcall.py](../disassem/hostcall.py) | 读取共享清单并产生服务出口。 |
| [assist.py](../disassem/assist.py) | 指令名、branch 分类、operand/汇编格式辅助。 |
| [miasm_compat.py](../disassem/miasm_compat.py) | 已支持 miasm 表达式接口差异的适配。 |
| [solve_bug.py](../disassem/solve_bug.py) | LEA 解码和 LOCK 相关输出的局部修正，不是通用语义保证。 |
| [diagnostics.py](../disassem/diagnostics.py) | 每次翻译的定位、分级和去重日志。 |

### 5.5 桥接、负载与基线

| 文件 | 使用方式 |
| --- | --- |
| [daemon/daemon.c](../daemon/daemon.c) | 唯一常驻用户态桥接进程，维护目标学习和发布。 |
| [daemon/Makefile](../daemon/Makefile) / [README](../daemon/README.md) | daemon 构建、参数、会话和诊断说明。 |
| [bench/klock_test.c](../bench/klock_test.c) | pthread ioctl 驱动，参数含义见第 4 节。 |
| [klock_module/Makefile](../klock_module/Makefile) | workload 构建与可选第二源码模块开关。 |
| [klock_module.c](../klock_module/klock_module.c) | mode 分派、复杂 CS 记录、独立完整性检查和测试片段宿主。 |
| [kd_depth_source.c](../klock_module/kd_depth_source.c) / [头文件](../klock_module/kd_depth_source.h) | 两模块 learned-depth 实验的外部七锁 helper；普通启动不用加载。 |
| [kernel_baseline/README.md](../kernel_baseline/README.md) | 已捕获内核身份、已有 hook 差异和重建边界。 |
| [verify.py](../kernel_baseline/verify.py) | 只读检查 source/build/running；不是安装脚本。 |
| [manifest.json](../kernel_baseline/manifest.json) | 源码、构建文件和运行身份的基线哈希。 |
| [guest.config](../kernel_baseline/guest.config) | 捕获的内核配置，不是要求立即应用的新配置。 |
| [linux-6.1.159-guest.patch](../kernel_baseline/linux-6.1.159-guest.patch) | 已有改动证据；字节和旧注释保持原样，不作阅读性重写。 |

### 5.6 测试入口 `tests/`

测试入口通过 `run_all.sh --case/--suite` 选择，下面列原始驱动便于阅读。不要把
每个 `.sh` 都依次运行。复杂驱动管理角色和超时，直接以默认参数运行也可能加载模块。

| 文件 | 覆盖/用途 |
| --- | --- |
| [run_all.sh](../tests/run_all.sh) / [regression.py](../tests/regression.py) | 统一选择、去重、空闲门禁、执行和证据。 |
| [common.sh](../tests/common.sh) | 驱动共享的构建、JIT 检查、daemon/清理函数；不交互 source。 |
| [regression_evidence.py](../tests/regression_evidence.py) / [verify_evidence.py](../tests/verify_evidence.py) | 捕获冻结输入与输出；离线一致性校验。 |
| [test_01_module_load.sh](../tests/test_01_module_load.sh) | 基础模块/设备显式诊断。 |
| [test_02_jit_engine.sh](../tests/test_02_jit_engine.sh) | promotion/翻译/上传管线诊断，不执行 JIT。 |
| [test_04_spinlock.sh](../tests/test_04_spinlock.sh) | spin 主模式、复杂记录及生成体证据。 |
| [test_05_mutex.sh](../tests/test_05_mutex.sh) | mutex_jit=0 的原生互斥对照。 |
| [test_07_mutex_jit.sh](../tests/test_07_mutex_jit.sh) | mode 3 的发布门禁、重复/same-CPU 竞争。 |
| [test_08_mutex_jit_modes.sh](../tests/test_08_mutex_jit_modes.sh) | mode 4 嵌套、mode 5 服务、多角色竞争。 |
| [test_09_jit_execution_modes.sh](../tests/test_09_jit_execution_modes.sh) | 显式 mode 兼容入口；无参只列清单。 |
| [test_10_native_resume.sh](../tests/test_10_native_resume.sh) | CALL/native 后缀、寄存器、资源、信号和受检边界的主驱动。 |
| [test_11_mutex_native_protocol.sh](../tests/test_11_mutex_native_protocol.sh) | 目标/非目标共享 Linux mutex。 |
| [test_12_context_native_only.sh](../tests/test_12_context_native_only.sh) | 上下文拒绝负例，必须没有实际 JIT。 |
| [test_13_spin_shadow_capacity.sh](../tests/test_13_spin_shadow_capacity.sh) | 显式 full-shadow 队首诊断。 |
| [test_14_spin_frame_depth.sh](../tests/test_14_spin_frame_depth.sh) | 自然物理 frame 链和继承的锁容量。 |
| [test_15_spin_native_gate.sh](../tests/test_15_spin_native_gate.sh) | 原锁 L/私有 S 内核组件检查。 |
| [test_16_spin_entry.sh](../tests/test_16_spin_entry.sh) | origin ticket/task/CPU 原生引用组件检查。 |
| [test_17_spin_native_protocol.sh](../tests/test_17_spin_native_protocol.sh) | spin 与非目标原生 API 的 Linux 互斥。 |
| [test_18_spin_routing.sh](../tests/test_18_spin_routing.sh) | 真实 hook 路由，刻意不执行 JIT。 |
| [test_19_mutex_signals.sh](../tests/test_19_mutex_signals.sh) | 非目标原生 mutex peer 的信号取消。 |
| [test_20_remote_outer.sh](../tests/test_20_remote_outer.sh) | 远端祖先提前释放和 owner 依赖。 |
| [test_21_remote_depth.sh](../tests/test_21_remote_depth.sh) | 四至八层、多请求、跨 NUMA/deferred 组合。 |
| [test_22_mutex_task_lifecycle.sh](../tests/test_22_mutex_task_lifecycle.sh) | 真实 task/RCU/final ACK，不计 JIT。 |
| [test_23_mutex_parallel_native.sh](../tests/test_23_mutex_parallel_native.sh) | 双队列 frame、资源压力、rename、peer、source 退休。 |

### 5.7 测试控制器和 oracle

这组文件由驱动调用；部分会控制真实进程/sysfs，不应当作全部只读工具。名字带
`protocol` 表示检查器/协调器，而不是生产锁协议实现。

| 文件 | 用途 |
| --- | --- |
| [cpu_placement.py](../tests/cpu_placement.py) | 采集真实 CPU/NUMA 拓扑。 |
| [audit_context_spills.py](../tests/audit_context_spills.py) | 独立静态准入 corpus，不执行危险指令。 |
| [audit_spin_native.py](../tests/audit_spin_native.py) | 历史 shared-word 审计，当前协议故意不满足其旧前提；不作日常入口。 |
| [mutex_signal_client.c](../tests/mutex_signal_client.c) | pidfd/信号实验的 ioctl 客户端和显式重试。 |
| [mutex_signal_protocol.py](../tests/mutex_signal_protocol.py) | 就绪检查及真实 signal peer 控制/判定。 |
| [mutex_parallel_protocol.py](../tests/mutex_parallel_protocol.py) | 双 frame、共享 CPU 和资源组合协调。 |
| [mutex_shadow_protocol.py](../tests/mutex_shadow_protocol.py) | 双 frame 内真实 shadow map 压力。 |
| [mutex_stack_protocol.py](../tests/mutex_stack_protocol.py) | 共享栈变化后的 post-control 续跑判定。 |
| [native_only_protocol.py](../tests/native_only_protocol.py) | 真实设备拒绝协议，不执行代码。 |
| [native_ooo_protocol.py](../tests/native_ooo_protocol.py) | 原 waiter 的 A-before-B 完成顺序。 |
| [native_register_protocol.py](../tests/native_register_protocol.py) | CALL-entry GPR/SP/IP 样本与 native frame 关联。 |
| [native_waiter_signal_protocol.py](../tests/native_waiter_signal_protocol.py) | 原 waiter 的信号、B 获取/取消和最终 A ACK。 |
| [native_waiter_signal_race.py](../tests/native_waiter_signal_race.py) | pidfd signal 与真实 B release 竞争。 |
| [readmission_protocol.py](../tests/readmission_protocol.py) | 两次尝试的真实队列重入契约。 |
| [remote_depth_protocol.py](../tests/remote_depth_protocol.py) | 深层远端 chain 和请求证据。 |
| [remote_outer_protocol.py](../tests/remote_outer_protocol.py) | 远端祖先/原生依赖证据。 |
| [spin_acquired_protocol.py](../tests/spin_acquired_protocol.py) | 本地已获取 B 的受检 post-CALL native。 |
| [spin_frame_protocol.py](../tests/spin_frame_protocol.py) | 物理 shadow-stack frame 及 watermark 判定。 |
| [spin_gate_protocol.py](../tests/spin_gate_protocol.py) | 保留 native 后缀期间的 gate map 饱和。 |
| [spin_node_protocol.py](../tests/spin_node_protocol.py) | 排空后的节点 reservation 检查。 |
| [source_depth_protocol.py](../tests/source_depth_protocol.py) | 两层/两模块学习及 loader ref 与 source pin 区分。 |
| [source_retirement.py](../tests/source_retirement.py) | dual-frame 的 busy/finish/reuse source 阶段。 |
| [source_session_driver.c](../tests/source_session_driver.c) / [source_session_child.py](../tests/source_session_child.py) | 实际 fork/exec 设备 lease 存活探针，不是假装翻译成功。 |

### 5.8 内核测试片段 `tests/kernel/`

workload 片段被 `klock_module.c` 或另一个 workload include；观察器/组件自测在
`KDLOCK_SELFTEST` 下被 provider include。具体 include 点可用
`rg 'tests/kernel|workload.c' kernel_module klock_module tests/kernel` 查找。

| 文件 | 用途 |
| --- | --- |
| [context_lock_workload.c](../tests/kernel/context_lock_workload.c) | IRQ/BH/per-CPU 原生拒绝源码。 |
| [native_register_probe.h](../tests/kernel/native_register_probe.h) / [native_register_workload.c](../tests/kernel/native_register_workload.c) | 无 C prologue 的 GPR 样本和可翻译前缀。 |
| [native_ooo_workload.c](../tests/kernel/native_ooo_workload.c) | A 提前解锁的本地 native/JIT 场景。 |
| [native_waiter_signal_workload.c](../tests/kernel/native_waiter_signal_workload.c) | 原 waiter 信号后仍保留副作用和 A ACK。 |
| [mutex_signal_workload.c](../tests/kernel/mutex_signal_workload.c) | 原生 peer 的 interruptible/killable 等等待。 |
| [mutex_parallel_workload.c](../tests/kernel/mutex_parallel_workload.c) | 两独立队列的真实 native frame。 |
| [mutex_parallel_peers.c](../tests/kernel/mutex_parallel_peers.c) | 双 B 原生 peer 的取消/重排和 owner 观察。 |
| [mutex_code_pool_workload.c](../tests/kernel/mutex_code_pool_workload.c) | 64 个真实 cold CALL site 消耗代码池，不计 JIT。 |
| [mutex_shadow_workload.c](../tests/kernel/mutex_shadow_workload.c) | 原 hook 获取造成 shadow map 耗尽。 |
| [mutex_stack_workload.c](../tests/kernel/mutex_stack_workload.c) | B owner 改写共享栈字，触发受检 native 后继。 |
| [spin_native_workload.c](../tests/kernel/spin_native_workload.c) | 原生 L 排斥和 alternate API 数据 oracle。 |
| [spin_routing_workload.c](../tests/kernel/spin_routing_workload.c) | 可控目标/非目标 hook 路由。 |
| [spin_chain_workload.c](../tests/kernel/spin_chain_workload.c) | 八层物理 queue/combiner 链。 |
| [remote_depth_workload.c](../tests/kernel/remote_depth_workload.c) | 一个 logical waiter 的多物理执行者和 deferred 请求。 |
| [remote_outer_workload.c](../tests/kernel/remote_outer_workload.c) | 远端祖先解锁及独立 owner 依赖。 |
| [spin_ticket_workload.c](../tests/kernel/spin_ticket_workload.c) | 真实获取填满 32 个 ticket。 |
| [spin_gate_workload.c](../tests/kernel/spin_gate_workload.c) | 旧后缀存活时填满原生 gate map。 |
| [spin_acquired_workload.c](../tests/kernel/spin_acquired_workload.c) | B 私有队首、后继竞争者与已提交 A 前缀。 |
| [mutex_shadow_trace.c](../tests/kernel/mutex_shadow_trace.c) | 只观察真实 shadow 表，不填造成员。 |
| [spin_node_trace.c](../tests/kernel/spin_node_trace.c) | node reservation 排空记录。 |
| [spin_frame_trace.c](../tests/kernel/spin_frame_trace.c) | frame 栈深度/watermark，深栈上不打印。 |
| [spin_refusal_trace.c](../tests/kernel/spin_refusal_trace.c) | 拒绝包、owner/ledger 的只读快照。 |
| [spin_readmission_trace.c](../tests/kernel/spin_readmission_trace.c) | bounded readmission 观察。 |
| [spin_deferred_trace.c](../tests/kernel/spin_deferred_trace.c) | 真实 deferred 队列选择/接链观察。 |
| [exec_capacity_probe.c](../tests/kernel/exec_capacity_probe.c) | 固定 frame 容量拒绝及包不变观察。 |
| [exec_relay_exit_probe.c](../tests/kernel/exec_relay_exit_probe.c) | 无锁 root 等待原 waiter TID 脱离，不加 task ref。 |
| [spin_gate_selftest.c](../tests/kernel/spin_gate_selftest.c) | hook 发布前的原生 L/私有 S 组件测试。 |
| [spin_entry_selftest.c](../tests/kernel/spin_entry_selftest.c) | task/CPU pins、tickets 与原生锁组件。 |
| [spin_shadow_selftest.c](../tests/kernel/spin_shadow_selftest.c) | full-shadow 队首路径。 |
| [spin_virtual_selftest.c](../tests/kernel/spin_virtual_selftest.c) | virtual 请求资源拒绝/取消检查。 |
| [mutex_task_selftest.c](../tests/kernel/mutex_task_selftest.c) | task 路由删除、跨 reader RCU 与 final ACK。 |

### 5.9 单元测试 `tests/unit/`

`Makefile` 中的程序才是通常运行入口；`*_fixture.c` 多由对应 Python 程序生成
生产代码头后编译，不能脱离该驱动直接编译。模型、替代原语和 log mutation
不证明 Linux 并发正确；程序自身标明何处执行真实生成机器码。

| 文件 | 用途 |
| --- | --- |
| [Makefile](../tests/unit/Makefile) | 7 个 C 程序与 Python unit 列表；支持 TESTS/PY_TESTS 显式选择。 |
| [mock_kernel.h](../tests/unit/mock_kernel.h) / [test_harness.h](../tests/unit/test_harness.h) | 模型所需类型和断言宏。 |
| [spin_gate_mock.h](../tests/unit/spin_gate_mock.h) | 提取式 C fixture 共用的 CPU/lock/atomic 替代原语。 |
| [test_tail_encoding.c](../tests/unit/test_tail_encoding.c) | tail 编解码模型。 |
| [test_mutex_transition.c](../tests/unit/test_mutex_transition.c) | 原生 owner/串行 executor 模型。 |
| [test_jit_call_policy.c](../tests/unit/test_jit_call_policy.c) | CALL/hostcall/outer-unlock 出口模型。 |
| [test_exec_frame.c](../tests/unit/test_exec_frame.c) | frame/ledger 不变量模型。 |
| [test_spin_node_count.c](../tests/unit/test_spin_node_count.c) | 有界 node 满的模型。 |
| [test_control_call.c](../tests/unit/test_control_call.c) | 直接使用生产 kd_call 规则。 |
| [test_daemon_policy.c](../tests/unit/test_daemon_policy.c) | 编译生产 daemon，测试结果缓存、子进程 lease 和 wire。 |
| [test_context_policy.py](../tests/unit/test_context_policy.py) | 上下文/CFG/静态范围/有界分析 corpus。 |
| [test_context_memory.py](../tests/unit/test_context_memory.py) | byte/word、alias、RMW、clobber 顺序事实。 |
| [test_context_guards.py](../tests/unit/test_context_guards.py) | 实际运行入口谓词及有界 CALL/RET 生成体。 |
| [test_context_spill_audit.py](../tests/unit/test_context_spill_audit.py) | 独立 spill audit 的错误分类。 |
| [test_hostcall_codegen.py](../tests/unit/test_hostcall_codegen.py) | manifest 与服务出口生成一致性。 |
| [test_segment_codegen.py](../tests/unit/test_segment_codegen.py) | segment lowering 与 wrapper 偏移。 |
| [test_text_regions.py](../tests/unit/test_text_regions.py) | cold text、CFG 扩展、设备 session/CAPS。 |
| [test_jit_diagnostics.py](../tests/unit/test_jit_diagnostics.py) | 可复用 mocked-text harness 和定位/告警判定。 |
| [test_jit_body_witness.py](../tests/unit/test_jit_body_witness.py) | guest 用户态运行真实 wrapper 和生成体 marker。 |
| [test_jit_entry_scope.py](../tests/unit/test_jit_entry_scope.py) / [jit_entry_scope_fixture.c](../tests/unit/jit_entry_scope_fixture.c) | 生产入口校验/未开始拒绝包。 |
| [test_exe_registry.py](../tests/unit/test_exe_registry.py) / [exe_registry_fixture.c](../tests/unit/exe_registry_fixture.c) | 生产 registry、代码池及上传边界。 |
| [test_exec_capacity.py](../tests/unit/test_exec_capacity.py) / [exec_capacity_fixture.c](../tests/unit/exec_capacity_fixture.c) | 生产 frame 分配/拒绝不变性。 |
| [test_hotlock_sampling.py](../tests/unit/test_hotlock_sampling.py) / [hotlock_sampling_fixture.c](../tests/unit/hotlock_sampling_fixture.c) | 替代 TSC 下的生产采样逻辑。 |
| [test_mutex_resources.py](../tests/unit/test_mutex_resources.py) / [mutex_resources_fixture.c](../tests/unit/mutex_resources_fixture.c) | 生产 node/shadow/hook 资源及完整 packet。 |
| [test_mutex_outer_progress.py](../tests/unit/test_mutex_outer_progress.py) / [mutex_outer_progress_fixture.c](../tests/unit/mutex_outer_progress_fixture.c) | 生产 mutex combiner 和 outer-event。 |
| [test_native_after_outer.py](../tests/unit/test_native_after_outer.py) / [native_after_outer_fixture.c](../tests/unit/native_after_outer_fixture.c) | 生产 native/control 边界，原语为替代实现。 |
| [test_native_registers.py](../tests/unit/test_native_registers.py) / [native_register_fixture.c](../tests/unit/native_register_fixture.c) | 实际用户态汇编 probe 与 GPR oracle。 |
| [test_spin_gate.py](../tests/unit/test_spin_gate.py) / [spin_gate_fixture.c](../tests/unit/spin_gate_fixture.c) | 生产 gate/hold map 与过期代际。 |
| [test_spin_entry.py](../tests/unit/test_spin_entry.py) / [spin_entry_fixture.c](../tests/unit/spin_entry_fixture.c) | 生产 origin ticket/ref 生命周期。 |
| [test_spin_routing.py](../tests/unit/test_spin_routing.py) / [spin_routing_fixture.c](../tests/unit/spin_routing_fixture.c) | 生产 hook/selector 路由。 |
| [test_spin_shadow.py](../tests/unit/test_spin_shadow.py) / [spin_shadow_fixture.c](../tests/unit/spin_shadow_fixture.c) | 提取实际队首和 combiner 路径。 |
| [spin_node_pool_fixture.c](../tests/unit/spin_node_pool_fixture.c) / [spin_queue_return_fixture.c](../tests/unit/spin_queue_return_fixture.c) | 上述 fixture include 的真实 producer、容量和嵌套返回。 |
| [spin_native_fixture.c](../tests/unit/spin_native_fixture.c) | 历史 spin 审计 witness，不是新的 qspinlock。 |
| [test_spin_outer_progress.py](../tests/unit/test_spin_outer_progress.py) / [spin_outer_progress_fixture.c](../tests/unit/spin_outer_progress_fixture.c) | 生产 spin batch/frame/outer-release。 |
| [test_remote_outer.py](../tests/unit/test_remote_outer.py) / [remote_outer_fixture.c](../tests/unit/remote_outer_fixture.c) | 生产远端/祖先解锁，CPU 切换为替代。 |
| [test_remote_deferred_protocol.py](../tests/unit/test_remote_deferred_protocol.py) / [deferred_trace_fixture.c](../tests/unit/deferred_trace_fixture.c) | deferred oracle 与实际选队/trace 代码。 |
| [test_spin_frame_protocol.py](../tests/unit/test_spin_frame_protocol.py) / [spin_refusal_trace_fixture.c](../tests/unit/spin_refusal_trace_fixture.c) | frame/refusal 日志与提取的观察器。 |
| [test_source_lifetime.py](../tests/unit/test_source_lifetime.py) / [source_lifetime_fixture.c](../tests/unit/source_lifetime_fixture.c) | 生产 source/CAPS/retire，内核原语替代。 |
| [test_source_depth_protocol.py](../tests/unit/test_source_depth_protocol.py) | 破坏 source/loader-ref 记录，确认 oracle 拒绝。 |
| [test_mutex_parallel_protocol.py](../tests/unit/test_mutex_parallel_protocol.py) / [mutex_parallel_client_fixture.c](../tests/unit/mutex_parallel_client_fixture.c) | 双 frame oracle、实际客户端参数/两次 ioctl 路由。 |
| [test_mutex_stack_protocol.py](../tests/unit/test_mutex_stack_protocol.py) | 拒绝伪造的栈变化/post-control 日志。 |
| [test_mutex_signal_protocol.py](../tests/unit/test_mutex_signal_protocol.py) | signal/peer/原 waiter 的坏日志和参数。 |
| [test_native_ooo_protocol.py](../tests/unit/test_native_ooo_protocol.py) | A-before-B 日志 oracle。 |
| [test_remote_outer_protocol.py](../tests/unit/test_remote_outer_protocol.py) | 远端祖先依赖坏日志。 |
| [test_remote_depth_protocol.py](../tests/unit/test_remote_depth_protocol.py) | 深链记录及真实 workload wait predicate。 |
| [test_spin_node_protocol.py](../tests/unit/test_spin_node_protocol.py) | reservation/drain 坏记录。 |
| [test_cs_oracle.py](../tests/unit/test_cs_oracle.py) | 实际 workload 状态更新与完整性函数。 |
| [test_kernel_baseline.py](../tests/unit/test_kernel_baseline.py) | 基线 reader 的损坏/伪造输入，不读取 live kernel。 |
| [test_regression.py](../tests/unit/test_regression.py) | 用例选择去重、停止边界、证据捕获和离线 verifier。 |

## 6. 阅读完以后改哪里

先从自己要改的行为回到第 2 节的执行链：JIT 范围改 analyzer，机器码 lowering 改
普通/特殊 lowerer，出口分类改 `exe.c`，锁/ACK 生命周期改 backend 与 `kd_exec.c`，
学习/发布改 daemon/device。不要在 workload 或 oracle 中放宽判定来绕过生产缺口。

新增功能必须注明目的和约束，选择覆盖该行为的复杂用例；基础已通过时不再默认重复。
涉及 flags 新出口、guest hook reader 或版本隔离时先查 TODO 的授权边界。
阅读与操作文档的完善不代表这些未完成功能已经实现。
