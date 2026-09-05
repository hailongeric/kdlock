# kdlock AI 操作手册

本文档是后续 AI/自动化工具操作本仓库时的首要运行说明。项目设计细节见
`README.md` 和 `docs/DESIGN.md`，最新实测证据见 `docs/VALIDATION.md`；本文只规定
环境边界、安全约束和可复现的操作流程。

## 1. 环境边界

### 宿主机

- 源码工作区：`/home/eric/vm/vm-shared/kdlock`
- QEMU 启动脚本：`/home/eric/vm/qemu-scripts/run_vm.sh`
- 共享目录源：`/home/eric/vm/vm-shared`
- 在宿主机执行：阅读和修改源码、`git status`、`git diff`、`git diff --check`。
- **不要在宿主机编译、加载或运行内核模块。** 宿主机只承担编辑和控制虚拟机的职责。

### QEMU 虚拟机

- SSH：`ssh -p 2222 root@127.0.0.1`
- 已配置 SSH key，正常情况下不需要密码。
- 共享目录目标：`/root/host_fs`
- 虚拟机内项目路径：`/root/host_fs/kdlock`
- 编译、单元测试、模块加载、daemon 和 benchmark 全部在虚拟机内执行。
- 当前已验证环境（2026-09-05）：定制内核 `6.1.159`，内核构建目录
  `/root/linux-6.1.159`，`/lib/modules/$(uname -r)/build` 指向该目录。每次会话
  仍须重新检查，不能假定虚拟机状态未变化。

normal mode 下，宿主机和虚拟机通过 9p 看到同一份源码，不需要同步文件。recovery mode
下 `/root/host_fs/kdlock` 是 guest ext4 上已有的本地目录，路径相同但内容不会自动同步。
不要移动或整目录复制仓库；先比较宿主机/guest 对应文件的哈希，只对确实变化的单个文件
使用 `scp`。避免同时从两侧修改同一文件。

## 2. 系统流程

```text
bench/klock_test（用户态，多线程 ioctl /dev/lock_dev）
        |
        v
klock_module/klock_module.ko（构造 spinlock/mutex 临界区）
        |
        v
定制 Linux 6.1.159 的 lock hook
        |
        v
kernel_module/kdlock_km.ko
  - kd_lock.c：hook、hot-lock 判断和原始锁 fallback
  - kd_hotlock.c：有界 hot-lock 状态表
  - kd_spinlock.c / kd_mutex.c：排队、combiner、委托协议
  - kd_exec.c / exe.c：嵌套 frame、JIT 执行、hostcall 和动态补全
        ^                         |
        | /dev/kd_dev             | JIT sandbox
        v                         v
daemon/daemon  -> disassem/*.py -> 汇编/链接 -> jit.bin 回写内核
```

`kdlock_km.ko` 依赖定制内核导出的 hook 和符号，不能在普通发行版内核上正确加载。
`klock_module.ko` 只是测试负载模块，创建 `/dev/lock_dev`。daemon 轮询
`/dev/kd_dev`，调用 miasm 翻译器并把生成的 JIT 二进制写回 `kdlock_km.ko`。

本项目仍是受限研究原型。`target_process` 只按 task comm 筛选，不能保证同一把
真实内核锁的所有使用者都走相同协议；`mutex_jit=0` 也仍使用独立 shadow mutex。
不要将测试锁上的通过结论推广到生产内核锁。JIT 失败只清理锁/frame 和恢复入口寄存器，
不会撤销内存写入；一般指令、flags、代码版本生命周期和 per-CPU 并发语义的缺口见
`docs/TODO.md`，不能称为通用的安全 sandbox 或事务恢复。
恢复的目标是保留已完成效果并从精确退出点继续 native 执行，不是要求内存回滚。
BCD 对比和仍需实现的调用栈/锁所有权协议见 `docs/DESIGN.md` 9.6。

Benchmark 参数为：

```text
./bench/klock_test <threads> <loops> <workload> <sys_count> <mode>
```

模式 `0/1/2` 分别是 spinlock contention、nested，以及 JIT 临界区通过白名单
hostcall 执行原生 API 后恢复；模式 `3/4/5` 是对应的 mutex 测试；模式 `6/7/8/9`
分别验证 spinlock 深层嵌套、OOO unlock、独立 A/B 竞争和 nested-JIT abort
recovery；模式 `10/11` 分别验证 nested spin/mutex 代理时翻译后的
waiter kernel GS、per-CPU 读写/RMW 和 logical `current`。

## 3. 强制安全规则

1. 修改代码前先在宿主机运行 `git status --short` 和 `git diff`，保留用户已有改动；
   未经要求不要 commit、reset、checkout 或清理未知文件。
2. 所有编译和执行命令必须通过 SSH 在虚拟机中运行。不要因宿主机也能看到源码而在宿主机
   执行 `make`、`insmod`、daemon 或 benchmark。
3. 验证必须逐级升级：静态检查/单元测试 -> 编译 -> 模块加载 -> 小负载 -> 相关集成测试。
   不要把 `tests/run_all.sh` 当作第一次验证。
4. 所有可能阻塞的 benchmark 必须使用 `timeout`。远程连接也应使用
   `-o BatchMode=yes -o ConnectTimeout=5`，避免无限等待。
5. 默认保持 `mutex_jit=0`。`mutex_jit=1` 仍是高风险 opt-in，只能在用户明确要求、
   且已经确认可用恢复手段后启用。
6. 加载前先卸载旧模块；先停止并等待 benchmark/所有 hook 调用者退出，确认队列和 frame
   无在途执行，再停止 daemon，按 `klock_module`、`kdlock_km` 顺序卸载。当前 hook
   调用者没有配套的 RCU reader/drain 保护，不能在压力负载运行时直接 `rmmod`。
7. 不要修改、编译或安装 `/root/linux-6.1.159` 中的内核。此类操作必须由用户
   明确授权。
8. 不要启动第二个 QEMU 实例。先执行 `ps -aux | grep qemu-system-x86` 检查
   QEMU 进程，再使用带超时的 SSH 检查 guest；如果 SSH 无法连接，按虚拟机已经崩溃
   处理，使用 `sudo pkill -9 qemu-system-x86` 强制关闭旧虚拟机后再重新启动。
9. 不要在 guest 中对 `/root/host_fs` 执行递归删除，也不要为同步源码而移动或覆盖整个目录。
   normal mode 不需要同步；recovery mode 先比较单文件哈希，再只同步变化文件。
10. 测试后检查 `dmesg` 中的 `BUG:`, `panic`, `double fault`, `soft lockup`,
    `unable to handle`。进程退出码为 0 不代表内核路径安全。

## 4. 每次操作的标准流程

### 4.1 宿主机预检

```bash
cd /home/eric/vm/vm-shared/kdlock
git status --short
git diff --check
```

确认虚拟机可连接：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 -p 2222 root@127.0.0.1 \
  'uname -r; findmnt -T /root/host_fs; readlink -f /lib/modules/$(uname -r)/build'
```

预期看到 `6.1.159` 和有效的内核 build 目录。normal mode 的 `/root/host_fs` 应为
9p；recovery mode 的同一路径应位于 guest ext4。先根据 QEMU 启动模式解释挂载类型，
不要因为 recovery mode 不是 9p 而移动目录。

### 4.2 低风险验证

在虚拟机中显式构建各组件，以保留真实错误输出：

```bash
ssh -p 2222 root@127.0.0.1 '
  set -e
  cd /root/host_fs/kdlock
  python3 -c "import miasm"
  make -C tests/unit clean
  make -C tests/unit run
  python3 -m py_compile disassem/*.py
  make -C kernel_module W=1 -j$(nproc)
  make -C klock_module W=1 -j$(nproc)
  make -C daemon CFLAGS="-O2 -Wall -Wextra -Werror"
  gcc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c \
    -o bench/klock_test -lpthread
'
```

说明：`tests/common.sh` 的 `build_all` 为保持测试输出简洁会隐藏构建日志，但任一组件
失败都会终止测试。排查编译问题时仍应先执行上面的显式构建，以获得完整诊断。
两项 Python codegen 测试在 miasm 缺失时会打印 `SKIP` 并返回 0，必须确认没有跳过，
才能报告 11/11 实际执行。九项 C 测试是算法模型，不能替代内核集成测试。

### 4.3 最小模块加载验证

显式构建成功后，优先运行只验证加载/卸载的测试：

```bash
ssh -p 2222 root@127.0.0.1 '
  cd /root/host_fs/kdlock
  timeout 60 bash tests/test_01_module_load.sh
'
```

需要手动操作时，先确认 benchmark/调用者已退出且没有在途代理，再使用以下顺序
（guest 已是 root，不使用 `sudo`）：

```bash
cd /root/host_fs/kdlock
pkill -x daemon 2>/dev/null || true
rmmod klock_module 2>/dev/null || true
rmmod kdlock_km 2>/dev/null || true
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
dmesg -C
insmod kernel_module/kdlock_km.ko target_process=klock_test mutex_jit=0
insmod klock_module/klock_module.ko
```

`kernel.randomize_va_space=0` 仅控制用户态 ASLR。内核 KASLR 必须已通过启动参数
`nokaslr` 禁用，不能用上述 sysctl 代替。

### 4.4 相关功能验证

只运行与改动相关的最小测试：

```bash
# JIT 初始化/回写
timeout 90 bash tests/test_02_jit_engine.sh

# hot-lock 状态机
timeout 60 bash tests/test_03_hotlock.sh

# spinlock 默认模式 0/1/2/6/7/8
timeout 180 bash tests/test_04_spinlock.sh

# mutex 模式 3-5；默认 mutex_jit=0
timeout 180 bash tests/test_05_mutex.sh
```

若验收目标明确要求 modes 0/1/2/3/4/5/10/11 都实际执行翻译后的指令，不能只运行
`tests/run_all.sh`；后者的 mode 3/4/5 使用 `mutex_jit=0`。确认 recovery 快照后运行：

```bash
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5 10 11
```

该入口对 mode 0/1/2/10 检查 spin JIT，对 mode 3 运行重复/压力 mutex JIT，
对 mode 4/11 运行 nested-mutex sandbox，对 mode 5 运行重复/压力 mutex hostcall。
所有模式均要求完整 artifact、daemon 回写、真实 `jit_success`、精确 counter 和干净的
`dmesg`。此外，artifact 的可执行部分必须包含复杂临界区特有的条件分支、`ROL`、
`IMUL` 和动态索引访存；卸载时必须报告
`kd_cs integrity: operations=<精确值> active_states=<预期值> failures=0`。该状态按锁隔离并由原生代码重放，
用于发现部分执行、重复执行和错误续点，不能只检查原有单一 counter。
mode 7 的 OOO 路径会让外锁记录的最大 frame depth 为 2；应联合检查非零
`jit_success`、`ooo_unlock` 和 nested lock/unlock，不要将外锁 depth 硬编码为 1。
mode 2/5 还要求 `ktime_get` 生成 hostcall stub、服务地址不进入
`callee_table.txt`、运行期不重编译，并且 `exits == executed == resumed > 0`；mode 5
还要求这些值等于 mutex `jit_success` 和 `jit_resume`。mode 1 的 B 在同一个 A 翻译
流中通过 known-call 执行；mode 4 则必须让 A/B 两个独立入口都进入 JIT。完整判定
和最近一次结果见 `docs/VALIDATION.md`。mode 10/11 还必须证明相关 artifact
加载 `Stack_RGS` 和 `Stack_RCT`、不保留硬件 segment 操作数，且运行时
`attempts == successes > 0` 、`failures == 0`。

注意：`install JIT chunk: ... status=0` 在 payload 拷贝前打印，只是回写请求记录。
需要结合 daemon 写入结果和运行期 JIT 成功证据，不能只凭日志认定完整发布。
mode 1/10 的测试不要求每个生成产物都执行；mode 4/11 才对 A/B 两个入口逐一检查。
每轮测试会清空 dmesg，保留整套结果时必须逐 mode 保存日志和产物标识。

仅在用户明确要求并接受 guest 崩溃风险时，运行独立的 mutex JIT 确认测试：

```bash
timeout 300 bash tests/test_07_mutex_jit.sh
```

该测试故意不属于 `tests/run_all.sh`。它执行 32 轮确定性 owner/waiter 队列和 8 线程
连续竞争。通过必须同时满足：daemon 已回写 JIT、重复出现
`mutex JIT delegation ok`、`jit_resume == jit_success`、最终 counter 精确匹配，
所有 JIT/frame/node/waiter/slot 失败指标为 0，且 `dmesg` 无内核错误。测试还要求
CPU 0 holder 后面的四个 CPU 1 waiter 产生 `multi_slot > 0`。

`tests/test_08_mutex_jit_modes.sh` 是 recovery-only 的 mode 4/5/11 验证。mode 4
使用 7 个分别绑定 CPU 的角色，在 A、B 上都强制形成 holder -> direct waiter ->
nested target -> trailing waiter 队列。通过条件包括至少两次真实 JIT completion、
`nested_queued >= 1`、`nested_remote >= 1`、最终 counter `12008`，以及所有
readiness/JIT/frame/context/node/waiter/slot 失败或泄漏指标为 0。mode 5 执行 16 轮
owner/waiter、CPU-pinned queue 和 8 线程连续竞争，要求 hostcall/JIT/waiter resume
严格一一对应、API observation 与最终 counter 精确相等且运行期不重编译。mode 11
复用 mode 4 队列拓扑，并额外校验 translated GS/current artifact 与运行时一致性。除非
recovery VM 正常且恢复快照已确认，否则不要运行该测试。

spin nested-JIT 的故障恢复同样只在 recovery VM 中运行：

```bash
KD_SPIN_ABORT_INJECT=1 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=1 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=2 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=3 bash tests/test_04_spinlock.sh 9
KD_MODE8_NOT_READY=1 KD_SPIN_ABORT_INJECT=1 bash tests/test_04_spinlock.sh 8
```

单独 `bash tests/test_04_spinlock.sh 9` 不会打开这些故障开关。必须记录实际环境变量，
区分普通拓扑通过、特定故障清理通过和仍未实现的副作用后精确续跑；不能将它们混写。

全部相关测试稳定后，必要时才运行：

```bash
timeout 600 bash tests/run_all.sh
```

测试失败或超时后，若 SSH 仍可用，立即收集信息并清理：

```bash
dmesg -T | tail -n 300
dmesg -T | grep -Ei 'BUG:|panic|double fault|soft lockup|unable to handle|kdlock|delegation'
```

确认工作线程已退出且队列/frame 已排空后，才执行卸载；若无法确认，不要强制卸载，
保留证据并按 recovery 流程恢复 guest。

```bash
pkill -x daemon 2>/dev/null || true
rmmod klock_module 2>/dev/null || true
rmmod kdlock_km 2>/dev/null || true
```

不要在收集日志前清空 `dmesg`。

## 5. QEMU 启动与崩溃恢复的实际情况

当前 `run_vm.sh`：

- 使用相对磁盘路径，因此只能先 `cd /home/eric/vm/qemu-scripts` 再启动；
- 前台运行 `sudo qemu-system-x86_64`，使用 `-nographic`，并把 guest 串口写入
  宿主机 `/tmp/qemu-serial.log`；
- 转发宿主机 `2222` 到 guest `22`；
- normal mode 以 9p 共享 `/home/eric/vm/vm-shared`，并配置 VFIO PCI 设备；
- `recovery` mode 同样配置 40 vCPU、28 GiB、双 NUMA 节点和 KVM，但不配置
  VirtFS/VFIO，以允许 QEMU `savevm`；
- 磁盘为 qcow2，并配置 Unix monitor socket `/tmp/qemu-monitor.sock`；`-s`
  只打开 GDB stub，不是 QEMU monitor。

因此必须注意：

- normal mode 的 VirtFS 会明确阻止 migration/savevm，VFIO 也可能阻止迁移；
  高风险测试必须使用 `./run_vm.sh recovery`。
- recovery mode 使用 guest 根磁盘上的 `/root/host_fs/kdlock` 既有本地目录；宿主机
  修改不会自动同步。测试前逐个比较相关文件哈希，只 `scp` 内容不同的单个文件，禁止
  搬移或递归覆盖目录，然后在 guest 重新构建。
- guest 内的 `/tmp` 不是宿主机 `/tmp`；宿主机 monitor socket 仍应由宿主机侧
  流程控制。guest 内脚本只能把是否成功连接作为提示。
- monitor socket 由启动用户拥有。使用 `./run_vm.sh monitor` 连接，使用 `Ctrl-C`
  断开客户端；绝对不要发送 HMP `quit`，该命令会退出 QEMU。
- 只有 `savevm` 无错误返回且 `info snapshots` 列出目标 tag，才能认为快照存在。
- guest 崩溃或 SSH 消失后先读取宿主机 `/tmp/qemu-serial.log`，再决定是否 `loadvm`。

### 5.1 虚拟机存活检查与重启

```bash
ps -aux | grep qemu-system-x86
```

检查输出时忽略 `grep qemu-system-x86` 自身；只有存在
`qemu-system-x86_64` 进程时，才认为 QEMU 进程存在。随后必须用 SSH 检查 guest：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 -p 2222 root@127.0.0.1 \
  'printf VM_OK; uname -r; findmnt -T /root/host_fs; readlink -f /lib/modules/$(uname -r)/build'
```

判断规则：

- `ps` 中没有 `qemu-system-x86_64`：虚拟机未运行，可以启动。
- QEMU 进程存在但 SSH 连接失败、超时或无法完成 banner：认为 guest 已崩溃或卡死。
- SSH 检查成功：虚拟机存活，继续检查内核版本、挂载点和内核 build 目录。

当 SSH 无法连接时，先保留宿主机串口日志，然后强制关闭旧 QEMU：

```bash
tail -n 300 /tmp/qemu-serial.log
sudo pkill -9 qemu-system-x86
```

确认旧进程已经消失后，再启动，不能在旧进程仍存在时启动第二个实例：

```bash
ps -aux | grep qemu-system-x86
cd /home/eric/vm/qemu-scripts
./run_vm.sh
```

高风险测试应启动 recovery VM：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

`run_vm.sh recovery` 前台运行，启动后在另一个宿主机终端连接 monitor：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh monitor
# HMP: savevm pre_mutex_jit
# HMP: info snapshots
# Ctrl-C 断开 monitor 客户端
```

如果加载模块后 SSH 消失：

1. 将其视为 guest hang/panic，不要继续发送测试命令。
2. 按 5.1 执行 `ps -aux | grep qemu-system-x86` 和带超时的 SSH 检查。
3. 读取 `/tmp/qemu-serial.log`，必要时保存已有 crash evidence。
4. SSH 失败时执行 `sudo pkill -9 qemu-system-x86`，确认旧进程退出后重新启动
   QEMU；不要在旧进程仍存在时启动第二个 VM。
5. 重启后先检查上一轮的构建改动和模块状态，从低风险验证重新开始，不直接重跑崩溃负载。

## 6. 仓库脚本的使用边界

- `tests/run_all.sh` 是真实内核集成测试，不是无风险单元测试。
- `tests/test_07_mutex_jit.sh` 是显式启用 `mutex_jit=1` 的高风险、非默认测试。
- `tests/test_08_mutex_jit_modes.sh` 是 high-risk mode 4/5/11 recovery-only 验证，
  不得加入默认测试或在无新快照时运行。
- `tests/test_09_jit_execution_modes.sh` 的严格 selector 包括 0/1/2/3/4/5/10/11；其中
  selector 2/5 分别验证 spin/mutex sandbox hostcall 的退出、原生执行和续点恢复。
  selector 10/11 验证 spin/mutex 的 waiter GS 和 logical `current` 代理语义。
- `daemon/0x*` 是翻译工作目录；只能在确认 daemon 已停止后清理。

## 7. 完成工作的报告要求

后续 AI 完成修改后应明确报告：

- 修改了哪些宿主机源码文件；
- 本次是文档/静态核对还是实际运行；不要把历史验证日期、计数器和日志写成新结果；
- 在 guest 中执行了哪些构建/测试及其结果；
- 是否加载过内核模块、是否启用 `mutex_jit`；
- `dmesg` 是否出现内核错误；
- 如果因快照/monitor 不可用而没有运行高风险测试，必须明确说明，不能声称已完整验证。
