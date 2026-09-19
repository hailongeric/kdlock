# Spinlock cacheline microbenchmark

独立比较同一 `spinlock_t` 临界区的原生执行与 kdlock 动态翻译执行。
多线程在一次 ioctl 内连续争抢共享锁，增加锁竞争等待和线程间交接的机会；
每次 `sc_body_N()` 返回后，执行少量仅用局部寄存器的无业务意义计算，再抢下一次锁。
负载热循环不插入主动调度、延时或额外等待。单线程档用于无竞争基线。
内核临界区驱动和共享 ioctl 头文件统一位于
[`workload_modules/spin_cacheline/`](../../workload_modules/spin_cacheline/)。
本目录保留客户端、运行器、测试和专用 provider 观测代码。
`run.py` 负责 CLI 与扫描，`bench_runtime.py` 提供计划/校验/环境工具，
`bench_session.py` 管理单会话准备、测量和排空；职责索引见
[bench/README.md](../README.md#代码组织)。源码冻结也包含内核的 `.inc` 实现。
生产锁实现仍位于 `include/`、`kernel_module/`；运行器不修改 guest 内核。
可显式选择已经构建、启动并验证的独立实验内核，见下文的内核身份参数。
环境准备与恢复快照遵循 [操作手册](../../docs/AGENTS.md)；编译、单元测试及
模块运行都只在 recovery guest `/root/host_fs/kdlock` 中进行。

## 冻结性能结果

当前本地发现版本仅有[36 场采样组件对照](../hotlock_record/results/20260919-local-discovery.md)，
尚未重测完整 spinlock 吞吐及 JIT 比例。以下完整操作数据属于此前冻结版本。

[热锁批量采样](../hotlock_record/results/20260919-batched.md)完成 90 场采样函数
和 40 场完整操作对照：20 线程稳态 −0.41%/+1.14%，JIT 约 99.7%；主要收益
在热锁发现和未晋升路径，不能将组件降本折算为完整 spinlock 加速比。

上一轮 [node/gate 缓存行隔离](results/20260919-cacheline-isolation.md)把 node 通知
分至第二行、gate 步长改为 64B。40 场旧/新交替对照全部通过：20 线程提高
6.55%/7.56%，4 线程下降 6.49%/5.91%（1/16 cacheline），没有重测三方倍率。

[9/19 五档线程三方对照](../tclock_compare/results/20260919-thread-scaling.md)
是隔离前最后一次完整三方基线：clobber ABI、1/4/8/16/20 线程的 150 场全部正确排空。
20 线程、1/16 cacheline 的 kdlock 中位吞吐为 2.990/2.894 Mops/s；16/20 线程
实际 JIT 超过 99%，4 线程仍明显落后。三方共用 caller，分别报告吞吐、代理
比例和波动；结果页同时给出批长与 node/gate 等对象的伪共享审计。
此前[长批次单线程成本](../tclock_compare/results/20260919-state-access.md#单线程长批次)
保留独立证据，本轮未重测。

| 历史对照 | 用途 |
| --- | --- |
| [状态访问五阶段](results/20260918-state-access.md) | 诊断引用、布局及普通准入/完成合并；100 场竞争和 20 场长批次 |
| [后继预取](results/20260918-prefetch.md) | 同镜像 `spin_prefetch=0/1/2` 与旧布局分开比较；默认 2 |
| [获取入口与缓存](results/20260918-spin-entry.md) | 首次 CAS 前移、缓存重复查询消除；无缓存试验退化，默认保留 `spin_native_cache=1` |
| [PT/Stack 共用](results/20260918-shared-reg-bank.md) | 24 场定向测量；减少搬运未证明一致提速 |
| [首次 TCLock 三方矩阵](../tclock_compare/results/20260918-native-stack.md) | 两种 ABI、180 场稳态、独立采样，保留并发冷晋升失败 |
| [统一 C 循环](results/20260918-unified-context.md)、[clobber 初版](results/20260918-clobber-v1.md) | 不同冻结版本的四臂比较，均非当前三方成绩 |
| [9/15–9/17 历史索引](results/HISTORY.md) | 已被替代的阶段报告、关键结果、固定 Git 版本和证据哈希 |

当前保存/恢复、TCLock 对照和成本分类见 [执行路径](EXECUTION_PATHS.md)。
旧扫描 `run.py` 仍报告 best/median；`clobber_compare.py` 和三方运行器使用五轮
中位数。以下保留运行方法及有独立证据的历史章节；不同口径和冻结输入不可混用。

<a id="source-organization"></a>

旧阶段的代码整理回归（2026-09-15）已收录在[历史索引](results/HISTORY.md#source-organization)；
当时的内核和源码冻结不适用于当前运行命令。

## 默认实验

| 项目 | 值 |
| --- | --- |
| 有效负载 | 1、2、4、8、16 条 64B cacheline |
| 一次操作 | 持有同一把锁，对每条有效 cacheline 上的一个 64 位计数器读改写一次 |
| 锁外间隔 | 每次正文返回后，4 组依赖前一结果的 64 位乘加；两组完全相同 |
| 主要对比 | 同一配置下，kdlock 最高有效吞吐 / 原生有效吞吐中位数 |
| 线程 | 1、4、8、12、16、20、24；每线程固定一个不同 guest CPU |
| CPU | 默认 0–23，使用列表的前 T 个；实际核对在线、亲和性、NUMA 节点及 64B line |
| 测量迭代 | 每线程 10,000 次，一个 ioctl 完成全部迭代 |
| 重复 | 每配置两对：原生→kdlock、kdlock→原生 |
| 扫描 | 35 个配置、70 对、140 个独立测量会话 |

当前 guest 的 CPU 0–19 位于节点 0，20–39 位于节点 1。按默认 CPU 顺序，
1–20 线程各档在节点 0，24 线程档使用节点 0 的 20 个 CPU 和节点 1 的 4 个 CPU。
运行器保存实际每线程 CPU/节点映射，CSV 和终端表标明 `single_node` 或
`cross_node`；24 线程结果同时包含跨节点放置的影响。可用 `--cpus` 指定顺序，
脚本不推断宿主机物理核关系，也不改变 guest 拓扑或内存分配策略。

N 只计有效负载 cacheline，不含锁、控制状态、栈或框架访问。数据槽的大小和
对齐均为 64B，包含 8B 计数器和 56B 填充；锁和控制状态另行对齐。
五个临界区固定展开，使用 `READ_ONCE/WRITE_ONCE`；规模选择和循环控制均在锁外。
热循环包含调用临界区、4 组局部乘加、更新完成次数和循环判断，没有 `cond_resched()`、
sleep/yield、额外自旋等待或定期信号轮询。进入循环后执行完整批次，再返回 ioctl。
临界区内不读时钟、不打印、不调用服务。每阶段核对所有 16 个计数器的前后
差值；未访问的槽必须不变。模块重载初始化新会话，不在测量中重置数据。

## 编译和运行

已有 guest 内核必须通过只读基线检查，使用 `nokaslr`、voluntary preemption
及 [固定 Python 运行依赖](../../disassem/requirements.txt)。如果使用 venv，
把该环境的 `bin` 放在 PATH 首位，使 daemon 子进程使用同一解释器。

```sh
cd /root/host_fs/kdlock
export LC_ALL=C
export KDIR=/root/linux-6.1.159-kdclobber2
make -C bench/spin_cacheline all test

# 只预览参数和配对顺序；不构建、不加载、不创建结果目录。
python3 bench/spin_cacheline/run.py --dry-run

# 从宿主机 monitor 实际确认 recovery 快照后才设置。
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915
timeout 3600s python3 bench/spin_cacheline/run.py \
  --kernel-source "$KDIR" \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spin-cacheline-new
```

快照 tag 是当前环境的示例，填写实际确认的 tag；环境变量不是快照证明。
宿主机发起 SSH 时也加总时限，例如 `timeout 3700s ssh ...`，不能只依靠
`ConnectTimeout`。脚本核对空闲状态和拓扑、构建本目录的专用 provider、daemon
和 benchmark，保留构建日志；普通 `kernel_module/` 的源码和构建产物不会被覆盖。

<a id="rerun-100k-no24"></a>

旧阶段的十万次重跑与百万次失败记录已收录在[历史索引](results/HISTORY.md#rerun-100k-no24)；
当时的内核和源码冻结不适用于当前运行命令。

### 构建产物和单点选择

`make all` 包含 `provider`、`module` 和 `client`。只构建原生负载可执行
`make -C bench/spin_cacheline module client`；`module` 委托给
`workload_modules/spin_cacheline/Makefile`，输出同目录的 `spin_cacheline.ko`。
`provider/prepare.py` 将当前项目的
provider 源码和头文件复制到 `.build/provider/`，只在副本应用
`provider/observation.patch` 并加入 `provider/kd_bench.c`、`provider/kd_bench.h`，
再按 `KDLOCK_SELFTEST=0 KDLOCK_NUMA=0` 构建。补丁仅包含常规日志开关和
wrapper 返回后的正文计数接入，不改变锁协议、准入检查或 wrapper ABI。
wrapper 入口和复杂 spin 执行的观察补丁分别跟随
`execution/wrapper_entry.inc` 与 `spin/execute.inc`，同时保留 dispatcher 的拒绝观测。
不维护另一份完整 kdlock 源码；项目更新导致补丁上下文不匹配时构建直接失败，
需要先检查并更新观测补丁，不能用模糊匹配绕过。

测试模块输出为 `.build/provider/kernel_module/kdlock_km.ko`，模块名仍为
`kdlock_km`，以复用现有 daemon/设备接口，因此不能与普通 provider 同时加载。
普通 `make -C kernel_module` 不包含这些 benchmark 参数或计数开销。
`manifest.json` 记录原始输入、观测层及最终副本的哈希；扫描结果同时冻结这些
文件和实际加载的模块。`make clean` 只清理本 benchmark 的构建产物。

缩小参数示例（仍按两对执行，四个会话）：

```sh
timeout 600s python3 bench/spin_cacheline/run.py \
  --cachelines 4 --threads 8 --iterations 10000 --repeats 2 \
  --cpus 0-7 --output /tmp/spin-cacheline-c4-t8
```

`--cachelines`、`--threads` 接受空格分隔的多个值；`--cpus` 接受逗号或区间，
保持输入顺序且拒绝重复。`--repeats` 指每配置的**配对数**，必须是正偶数。
`--iterations I` 是**每个线程在一次 `SC_RUN` ioctl 内执行的抢锁次数**，范围
1–100,000,000，默认 10,000。需要更长的批次时，例如指定
`--iterations 1000000`，每线程仍只提交一次 RUN；不要在用户态循环调用 ioctl。
结果目录须在源码树外且不存在，拒绝覆盖。扫描期间不要改源码或二进制；
脚本会在会话边界比对输入哈希。需要有序提前停止时创建结果目录下的 `STOP`
文件，当前会话排空后停止，保留后续 `NOT_RUN`。

单独试用原生模块不需要 kdlock 符号（同样遵守恢复环境和外层时限）：

```sh
insmod workload_modules/spin_cacheline/spin_cacheline.ko
bench/spin_cacheline/client --layout
timeout 120s bench/spin_cacheline/client \
  --cachelines 4 --iterations 10000 --cpus 0,1,2,3
bench/spin_cacheline/client --counts
# 确认客户端退出、计数查询成功且 active=0 后：
rmmod spin_cacheline
```

这只是组件运行方法，不替代配对扫描；超时之后不要继续执行卸载命令。

## 两组执行流

每个会话先加载独立源模块、查询布局并确认初始计数为零。原生组整个会话
都不加载 kdlock。kdlock 组装载本目录生成的专用 provider
`.build/provider/kernel_module/kdlock_km.ko`，装载参数为：
`target_process=sc_worker bench_quiet=1 bench_lock_addr=<被测锁地址> jit_timing=0`，
启动现有 daemon，继承 `KD_JIT_BODY_WITNESS=1`。

两组均由 T 个绑核线程先执行每线程 1 次、等待 1 秒，再执行每线程 12,000 次。
这是预热和现有热锁频率采样的自然准备；不调用强制晋升接口、不增加竞争线程。
kdlock 组等待对应 `sc_body_N` 的唯一 spin 条目 NORMAL，检查非空生成物及正文
标记、成功的翻译子进程结果，并等待翻译者退出。随后停止 daemon、确认无
writer/frame；两组均再等待 2 秒。发布失败或准备超时不能冒充 NO_JIT。

客户端使用 C11 原子变量 `ready/go/abort` 起跑，不使用 mutex 或条件变量。
每个线程完成绑核后发布 ready，再用 `pause` 等待 go；主线程等所有已创建线程
ready 后读取 wall 时钟，用 release store 放行，worker 用 acquire load 接收。
任一创建/绑核失败会发布 abort，并放行、回收已创建线程，不执行负载。
ready 和 go 分开对齐到 cacheline；编译时要求这些原子类型始终 lock-free。
原子起跑等待只在 ioctl 前发生，批次内不设同步屏障或交接等待。
起跑前的自旋不计入 worker CPU 时间；wall 区间从主线程放行前的时间戳，到
最后一个 worker 在 ioctl 返回后取得的时间戳，worker CPU 时间分别取线程
CPU 时钟。准备阶段不计入测量。
kdlock 测量前后分别读取只读 `bench_jit_bodies`，并核对条目和生成物哈希未变。

驱动的执行登记和计数快照也使用原子状态：非负值表示在途 worker 数，-1
表示快照独占。读取快照必须成功将 0 改为 -1；期间新 RUN 返回 EBUSY。存在
worker 或其他快照时，计数查询返回 EBUSY。最后一个 worker 的 release 退出
与快照的 acquire 进入配对，避免仅检查 active=0 后与新写入发生竞争。这些
操作每个 ioctl 只在循环前后执行，被测临界区仍使用同一把 `spinlock_t`。

专用 provider 的 `bench_quiet` 默认 false，`bench_lock_addr` 默认 0（不计数），
均仅能在装载时指定。quiet 关闭常规逐次日志，保留 warning/error、拒绝诊断、汇总和全部协议
检查。实际 wrapper 返回且正文标记为 1 时，匹配锁按一次逻辑 dispatcher 调用
计数；同一调用的多个 wrapper continuation 不重复计数。计数采用 per-CPU 槽，
不增加全局原子更新；只读 getter 求和包括 offline CPU。**只能在调用者和 frame
排空后解读精确累计值**，执行中读取只是近似快照。两元素 wrapper ABI 不变。

## 临界区与测试伪代码

kdlock 内部的首次发现/注册、已发布原生快路径、排队代理、wrapper/JIT 正文及
waiter 恢复，另见 [执行路径与开销伪代码](EXECUTION_PATHS.md)。该文展开本地发现、达标后的共享发布、
原子操作、frame 校验和复制，并区分准备期开销与测量期每次执行的成本。
发生代理时，锁外乘加由原 waiter 恢复后执行；combiner 连续代理多个正文期间
仍持有原锁，不在相邻 JIT 正文之间执行这段乘加。

所有线程更新模块全局的同一个 `sc_data` 数组，并争用同一把 `sc_lock`。
例如 N=4 时，[payload.h](../../workload_modules/spin_cacheline/payload.h)
展开的临界区如下；N=1/2/8/16 只改变显式更新的槽数，每次获取锁完成一次 op。
每槽只读改写一个 64 位值，64B
表示槽的占用与间距，不表示每次操作从内存读取完整的 64B。

```c
static void sc_body_4(void)
{
    spin_lock(&sc_lock);
    WRITE_ONCE(sc_data[0].value, READ_ONCE(sc_data[0].value) + 1);
    WRITE_ONCE(sc_data[1].value, READ_ONCE(sc_data[1].value) + 1);
    WRITE_ONCE(sc_data[2].value, READ_ONCE(sc_data[2].value) + 1);
    WRITE_ONCE(sc_data[3].value, READ_ONCE(sc_data[3].value) + 1);
    spin_unlock(&sc_lock);
}
```

增大 `--iterations` 只增加获取锁的次数，不增加单次持锁的工作量：
**每次持锁仍只执行 N 次计数器自增**。锁内没有重复执行这组更新的循环，
也不主动刷新缓存或强制每次更新产生 cache miss。

以下是一次测量的成功路径，对应 [client.c](client.c) 与
[module.c](../../workload_modules/spin_cacheline/module.c)。
N 是数据 cacheline 数，T 是线程数，I 是每线程迭代数；`now()` 返回纳秒数。
外层运行器在每个配置依次执行原生→kdlock、kdlock→原生，
两组各自重建会话并完成前述准备。
kdlock 的 JIT 计数在客户端测量前、返回且排空后分别读取；预热不计入差值。

```text
client_main(N, T, I):
    fd = open(device)
    layout = ioctl(fd, SC_LAYOUT)             // 检查共享锁与数据槽布局
    before = ioctl(fd, SC_COUNTS)             // 此时无 worker
    atomic ready = 0; atomic go = false; atomic abort = false
    创建 T 个 worker，各自指定一个不同的 guest CPU
    while load_acquire(ready) != T: pause()
    t0_ns = now(CLOCK_MONOTONIC)
    store_release(go, true)
    join 所有 worker
    t1_ns = max(worker.finished_ns)           // 使用已记录时间，不在 join 后重新计时
    after = ioctl(fd, SC_COUNTS)              // 在测量区间之后
    completed = sum(worker.completed)
    assert 所有 worker 成功且各自 completed == I
    assert completed == T * I
    assert after[j] - before[j] == (completed if j < N else 0), 对所有 16 个槽
    wall_ns = t1_ns - t0_ns
    throughput = completed * 1e9 / wall_ns
    amortized_ns_op = wall_ns / completed
    worker_cpu_ns = sum(worker.cpu_ns)
    close(fd)

worker(cpu, N, I):
    request = {cachelines: N, iterations: I}
    绑定并核对 CPU，设置线程名             // 全部在 ready 之前
    fetch_add_acq_rel(ready, 1)
    while !load_acquire(go): pause()
    if load_relaxed(abort): return
    cpu_start_ns = now(CLOCK_THREAD_CPUTIME_ID)
    ioctl(fd, SC_RUN, &request)               // 仅一次；结果写回 request.completed
    finished_ns = now(CLOCK_MONOTONIC)
    cpu_ns = now(CLOCK_THREAD_CPUTIME_ID) - cpu_start_ns
    返回 request.completed、finished_ns、cpu_ns

kernel_SC_RUN(request):
    copy_from_user(request)                   // 整批只复制一次输入
    校验 N、I；选择已展开的 sc_body_N          // 选择在循环外
    原子登记在途 worker；快照独占时返回 EBUSY
    completed = 0
    local_state = 1                          // 每个 ioctl 私有，跨迭代保留
    while completed < I:                     // 整个循环都在一次 ioctl 的内核调用中
        sc_body_N()                          // lock → N 次读改写 → unlock
        repeat 4 times:                      // 锁已释放，仅为下一次抢锁留一个小间隔
            local_state = (local_state * 1664525 + 1013904223) mod 2^64
        completed += 1
    原子注销在途 worker
    request.completed = completed
    copy_to_user(request)                    // 整批只复制一次输出
    return 0
```

锁外计算实现在 [post_work.h](../../workload_modules/spin_cacheline/post_work.h)。
实际代码固定展开为 4 条 `imulq` 和 4 条 `addq`，用 `asm volatile` 保证最终结果
即使不被业务使用也不会被删除；操作数只在寄存器中，不更新共享 sink 或计数器。
它在正文函数返回后执行，不进入 JIT 临界区，也不增加每次 op 的 syscall。
两组执行完全相同的计算，wall 时间和线程 CPU 时间都包含其开销；不扣减估算值。
这个短间隔增加其他线程在下一次申请前获取锁的机会，**不保证公平交接**。

创建或绑核失败时，实际代码设置原子 abort、放行并回收已创建线程，负载不执行。
ioctl 失败、迭代不完整或数据校验失败都不能生成有效性能比。
RUN 循环不再轮询信号并返回部分完成的 EINTR；停止和卸载仍须等待固定批次完成并排空。

## 时钟与 syscall 开销

`clock_ns` 这类读时钟函数**会影响性能**。本实现的函数名是 `now(clockid_t)`，
它调用 `clock_gettime` 并将结果换算成 ns；只在整批操作边界调用，内核循环
和临界区内均没有计时。下面统计的是一次成功的**测量客户端调用**，不含
运行器的预热、布局辅助查询、JIT 观测及排空检查：

| 调用 | 次数 | 位置 |
| --- | --- | --- |
| `SC_RUN` ioctl | T | 每个 worker 一次，每次执行 I 次抢锁 |
| `SC_LAYOUT` / `SC_COUNTS` ioctl | 1 / 2 | 测量开始前 / 测量前后 |
| `clock_gettime(CLOCK_MONOTONIC)` | T+1 | 主线程放行前一次，每个 worker 返回后一次 |
| `clock_gettime(CLOCK_THREAD_CPUTIME_ID)` | 2T | 每个 worker 的整批操作前后各一次 |

因此执行 T×I 次临界区只需要 T 次 RUN，总 ioctl 数为 T+3，读时钟共 3T+1 次。
例如 T=16、I=10,000 时，160,000 次抢锁对应 16 次 RUN、3 次布局/计数 ioctl
和 49 次读时钟；增大 I 不增加这些调用次数。定向客户端测试在不同批次大小
下检查这一调用预算，观测只存在于测试夹具，不加入性能测量程序。

函数调用次数不等于实际 syscall 次数：`CLOCK_MONOTONIC` 可走 vDSO，仍可能
回退到 syscall；当前 guest 内核的 `CLOCK_THREAD_CPUTIME_ID` 走 syscall
回退。无论采用哪条时钟路径，都有执行成本，不能把 vDSO 当作零开销。

固定成本没有从结果中扣除。放行后的线程 CPU 时钟读取、ioctl 进出与返回后
的 wall 时间戳都影响测量边界；某个 worker 最后的 CPU 时钟读取虽晚于它自己
的结束时间戳，也可能与其他 worker 的测量区间重叠。增大 I 可以摊薄批次边界
成本，但本测试没有单独量化时钟开销，不能据此给出误差百分比。

热循环没有用户态发起的 syscall，也不主动调度或等待；每次解锁返回后完成
局部乘加再开始下一轮抢锁。中断和 guest/宿主调度仍可能影响执行，每次 `sc_body_N()` 调用、
循环控制、已有 hook 和 kdlock 观测也有成本。因此这里报告的是包含框架成本的
整批临界区吞吐。连续抢锁不保证每次解锁都换一个持有线程；当前没有记录原生
获取锁失败次数、等待时间、持锁时间或持有线程切换次数，不能由这些结果量化
竞争程度；总吞吐随线程数增长也不能证明没有竞争或锁已经饱和。

## 结果解释

主表以吞吐为选择指标，这里的 medium 按 **median（中位数）**处理：

```text
native_median = median(所有有效原生会话的 completed / wall_seconds)
kdlock_best   = max(所有有效 kdlock 会话的 completed / wall_seconds)
best_ratio    = kdlock_best / native_median
```

只在同一 cacheline 数、线程数、迭代数、CPU 放置和同一冻结运行输入内选择。
这是**本次样本中 kdlock 的最佳观测表现对原生中位数**，不等于理论极限或典型性能；
取样次数增多会影响最大值，因此表中同时显示两组有效样本数。默认每组 2 个样本，
需要更多观察时显式增大正偶数 `--repeats`。不跨配置挑原生较慢的一组，
也不取逐对比值的最大值。所有原始样本与原有配对比值仍保留供检查。

kdlock 最佳吞吐对应的会话名、摊销 ns/op、JIT 次数/占比/状态来自**同一个会话**。
最快样本若是 NO_JIT，仍显示 NO_JIT。准备失败、数据错误、未排空和未运行样本
均不参与选择；任一组没有有效样本时比值留空。两组分别取有效样本，未完成配对
仍在 `pairs.csv` 留空，主表通过有效样本数明确展示这种情况。

结果目录包含 `environment.json`、CPU 拓扑、内核基线与构建身份、输入和二进制
SHA256、源码/二进制副本、payload 反汇编；每会话保留 `session.json`、各阶段
客户端 JSON、命令/PID、布局、翻译指标、生成物、kernel 日志及 retirement 状态。
构建或准备失败也保留已取得的证据。

| 输出 | 含义 |
| --- | --- |
| `raw.csv` | 每会话 CPU/NUMA 放置、完成次数、wall ns、吞吐、摊销 ns/op、线程 CPU ns、实际 JIT 次数/占比、数据校验与状态 |
| `pairs.csv` | 每对 NUMA 放置、kdlock/原生吞吐比及先后顺序；无效或缺失组为留空 |
| `summary.csv` / 终端表 | 原生吞吐中位数、kdlock 最高吞吐、best/median、有效样本数及最佳会话的 JIT 信息；CSV 另保留原有中位数和配对汇总 |
| `summary.json` | `comparison_policy=best_kdlock_over_median_native`、完整度、各配置汇总及测量期实际 JIT 覆盖 |

一次 op 是一次完整临界区，包含 N 次计数器更新。吞吐为完成 op / wall 时间，
`amortized_ns_op` 为 wall 时间 / 全体线程完成 op；不是单次获取锁的延迟。
线程 CPU 时间包含锁外乘加、ioctl/框架成本，也不等同于锁内成本。主表比值
大于 1 表示 kdlock 最佳观测吞吐高于原生中位数，小于 1 表示更低。
`best_kdlock_over_median_native` 是新主指标；`median_kdlock_over_native` 仍是
旧的逐对吞吐比中位数。两者不可互换，不据最佳值宣称统计显著性。
缺少每会话节点映射的历史结果重汇总时，NUMA 放置标为 `unknown`，不根据 CPU 编号推断。
此前含每 256 次调度点、2/4/8/16 线程的结果属于旧负载，不能作为当前连续抢锁版本的结果。
增加锁外乘加前的结果也属于另一负载版本；其历史成绩保持原标注。

`NO_JIT` 表示发布准备成功、测量完成且数据正确，但**测量期间**返回的 JIT
正文数为零；JIT 占比记 0，保留性能和配对比值，不能记为实际 JIT 验收通过。
预热曾执行 JIT 不改变此分类。每种 N 至少一个线程配置出现有效的测量期正文，
才验证该规模的 JIT 对比；否则明确列为 UNVERIFIED。正常排空的 NO_JIT 可继续
扫描；准备失败、数据错误不计算有效性能比。离线重生成汇总：

```sh
python3 bench/spin_cacheline/summarize.py /tmp/spin-cacheline-scan-20260914
```

<a id="assembly-inspection"></a>

### 汇编查看目录

`run.py` 和 `profile.py` 在每个 kdlock 会话成功完成测量、排空、停止翻译者及
正常卸载后，按临界区归类汇编。不同线程数、不同 repeat 的相同汇编只保存一份：

```text
bench/.tmp/spin_cacheline/<结果目录名>-<随机后缀>/
  README.md                      # 按临界区列出的查看索引
  index.json                     # schema=2，临界区和合并的来源记录
  sc_body_1/
    native.S                     # 翻译前的 sc_body_1，模块反汇编及重定位注释
    JIT.S                        # 生成器 asm/jit.S 原样复制，仅改文件名大小写
    bin.txt                      # JIT 机器码（含 wrapper）的 objdump 反汇编
    metadata.json                # 临界区、文件 SHA256、来源路径及入口/TGID
  sc_body_2/                     # 同样的三种汇编与元数据
  sc_body_4/
  sc_body_8/
  sc_body_16/
```

去重键为临界区规模及三种文件的内容哈希，不包含线程数、CPU 或重复轮次。
同一内容再次出现时，仅向 `metadata.json` 的 `sources` 追加来源，不重新复制代码。
如同一规模确实生成不同字节内容，则增加 `sc_body_N-<内容哈希>` 目录保留差异，
不擅自忽略指令或重定位地址的变化。查看索引不列线程数和 repeat；这些运行参数
仍在原始 `session.json` 中。每次扫描和补导出各自使用新目录，不混合不同运行。

**`bin.txt` 来自 `objdump ... asm/jit.bin`，是 JIT 之后的代码。** 翻译前请查看
`native.S`，它从该次运行的 `payload-disassembly.txt` 提取对应完整 `sc_body_N`，
保留锁调用和重定位信息；其中地址是模块 ELF 节内偏移，不是 guest 运行地址。
`JIT.S` 中还保留了生成器的原指令注释，实际运行入口和代码地址见 `metadata.json`。

运行器输出 `Assembly: ...`，并在原始结果目录写入 `assembly-export.json`，指向
本次查看目录，同时记录 `exported_critical_sections` 和 `source_sessions`。
只有新增代码组时打印 `Assembly:`；各组文件完整写入后才公开目录。复制和哈希
核对都位于计时区间之外，热循环不增加文件操作、时钟调用或 syscall。
每次扫描、每次补导出均创建新目录，不覆盖已有副本；目录由 Git 忽略且不进入
源码冻结。原始 workspace、生成器命名和测量结果保留不变。

导出按记录的 RIP/TGID 定位生成物，核对测量前后的发布记录与 SHA256。
新会话同时记录 `jit.bin`、`jit.S`、`bin.txt` 的测量前后哈希；旧结果只记录前两者，
补导出时将 `bin_txt_hashed_during_measurement` 标为 `false`，另存复制时哈希。
NO_JIT 和实际 JIT 会话若生成相同代码，共用一组文件，各自在来源记录中保留
真实正文计数；不能把一个会话的 JIT 证据归到另一个会话。
原生组没有 JIT 生成物；失败、未完成或未排空的会话不读取 workspace、不导出。
应有的文件缺失或已记录的哈希不符时停止导出，原始证据不覆盖。

对已保存的结果补导出（只处理文件，不加载模块、不执行 workload）：

```sh
python3 bench/spin_cacheline/assembly.py /tmp/spin-cacheline-best-post-work-20260915
```

该命令只在 `bench/.tmp/` 新建副本和索引，不向历史结果目录补写文件。它也可以
读取宿主机已解压的证据目录。recovery guest 使用 ext4，guest 内的查看目录
不会自动出现在宿主机共享源码；在宿主机将终端给出的准确目录复制回来：

```sh
mkdir -p bench/.tmp/spin_cacheline
# 将 <本次目录名> 替换为 Assembly 输出中的完整目录名，先确认本地同名目录不存在。
timeout 60s scp -r -P 2222 \
  'root@127.0.0.1:/root/host_fs/kdlock/bench/.tmp/spin_cacheline/<本次目录名>' \
  bench/.tmp/spin_cacheline/
```

这些副本供查看，不替代原始证据归档。需要清理时，仅删除已经查看完毕的那一个
临时结果目录；`make clean` 不删除它们，也不清理原始结果。

<a id="assembly-validation"></a>

旧阶段的按临界区去重的验证已收录在[历史索引](results/HISTORY.md#assembly-validation)；
当时的内核和源码冻结不适用于当前运行命令。

### 单线程为什么仍有 kdlock 开销

热锁发现按访问频率晋升，并不要求出现锁等待；单线程预热也能达到阈值。
当前生产实现为已登记、已发布的 spin 入口增加了
[原生快路径](../../include/kd_spin_fast.h)：每 CPU 缓存最近的锁地址、入口 RIP
和 gate。来源仍 OPEN、根调用没有已有抢占 pin/IRQ/迁移限制、缓存匹配且整个
私有调度字 S 为零时，直接尝试获取原生锁 L。成功后执行原临界区，解锁时释放
L 并清除 per-CPU 持有记录。这条路径不注册入口、不分配 ticket、不获取 S，也
不执行 JIT；与原生参与者的互斥仍完全由 L 提供。

缓存未命中或原锁获取失败、S 已有持有者/排队请求时，进入原有发现、登记与
委托路径。缓存仅在正常来源 pin 和 NORMAL 发布之后建立，不用线程数判断
是否关闭 JIT，也不改变本 benchmark 的准备和正文计数标准。即使检查 S 为空
之后另一线程进入委托，双方仍须获取 L，不能同时执行临界区。持有记录在 L
释放后、恢复抢占前清除，参与关闭准入后的路由和退休忙检查；快路径持有期间
的嵌套 hook 保持原生执行。

spin selector 的目标名比较使用装载时准备的掩码，仍匹配到 NUL，忽略终止符后
的旧字节，长于 task comm 的目标不会匹配。来源 OPEN 读取已内联；一般路径
的 ticket 栈对象移到独立 helper，减少原生返回时的栈保存和检查。

旧接口下 NO_JIT 仍有独立 selector、回调调用和快路径判断成本。合并入口实验
先尝试缓存中的纯原生获取，解锁先匹配保留的 owner；只有未命中才进行目标
选择。临时抢占 pin 的释放和选择逻辑移到慢路径，减少成功路径的寄存器保存。
它仍要检查原锁、S、来源和 CPU 上下文，并保留 owner 记录，不能视为零开销。
单线程没有其他请求可合并，不能把 NO_JIT 自动解读为原生基线开销。旧版本
每次经过登记、三遍 32-slot 扫描和 12 对内部 irqsave 锁的分析见
[历史调查](../../docs/VALIDATION.md#single-thread-investigation)，优化后配对数据、
同批次 hook 对照与剩余差距见
[先前优化](../../docs/VALIDATION.md#native-fast-path-optimization) 与
[直接调用及热点验证](../../docs/VALIDATION.md#spin-static-dispatch-profiling)。

### 单独测量 hook 调用成本

[`dispatch_floor/`](dispatch_floor/) 是独立诊断 provider，沿用同一负载驱动和
客户端，依次测量无 provider、selector 固定返回原生、selector 加最小原生
lock/unlock 回调三种情况。回调只调用 Linux 原锁 API，没有 kdlock 发现、
ticket、私有队列或 JIT。**这些是调用成本对照，不是 kdlock 成绩，也不计入
实际 JIT 验收。** 不加入默认扫描；常规扫描会拒绝残留的诊断 provider。

```sh
# 仍要求 recovery guest、已确认快照和外层 SSH timeout。
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 timeout 390s \
  python3 bench/spin_cacheline/dispatch_floor/run.py \
  --iterations 100000 --repeats 4 --output /tmp/spin-dispatch-floor-new
```

每轮三组，交替正序/倒序；每样本重载模块，并复用批次时钟、数据检查、内核
错误扫描和正常清理。结果、冻结输入和二进制单独归档。它测量当前 VM/内核的
最小回调对照，不能据此宣称通用硬件下界或改名为标准原生基线。
支持合并入口的实验内核会增加第四组 `combined`：一次直接分派到无条件原生
lock/unlock 回调，不做 selector、缓存或 JIT。旧三组仍使用原安装接口；第四组
才对应合并入口的最小回调成本。具体组别由构建产物导入的接口决定并记录。

### 独立内核实验与热点采样

脚本默认参数已指向 `kdclobber2` 源码和独立捕获基线；普通扫描、调用成本
对照和采样入口也可显式传入以下参数，仍执行相同的身份校验。原
[spin_static](../../kernel_experiments/spin_static/README.md) 基线保留作历史对照。

```sh
--kernel-source /root/linux-6.1.159-kdclobber2 \
--kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

检查仍覆盖配置、命名源码、构建产物及 live Build ID。每份输出保存所选基线；
不同内核的结果分别记录，各自以同内核原生组配对，不能合并为一批。

[`profile.py`](profile.py) 在正常准备和发布后，用 `perf record` 对实际 worker
做低频内核 IP 采样。每线程仍只有一个 RUN ioctl，不在锁循环中增加时钟或探针。
先用正常扫描构建并验证二进制，再单独采样，例如在当前 clobber 内核上：

```sh
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 timeout 240s \
  python3 bench/spin_cacheline/profile.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --perf /root/kdlock-tools/perf-6.1.159/perf \
  --arm kdlock --threads 1 --cachelines 1 --iterations 100000000 \
  --output /tmp/spin-profile-new
```

实验内核额外传入上面的两个身份参数。四线程诊断选 `--threads 4`，建议
`--iterations 1000000`，避免等待开销使会话超时。默认事件为 `cycles:k`、
频率 499 Hz；禁用 callchain，要求 ftrace/function profiling 保持关闭。
perf 需要在 guest 从对应源码构建并确认事件可用；不在宿主执行。

输出包括原始 `perf.data`、IP/period 样本、符号及大小、实际 JIT 正文差值、
数据检查和排空记录。[`profile_summary.py`](profile_summary.py) 可离线重新汇总，
按样本 period 加权，使用冻结 ELF 和确切生成代码范围；未解析地址保留为
`unresolved`。符号占比表示采到的执行位置，受采样误差和指令归属偏移影响，
不是独立函数计时，也不是锁竞争概率或单次等待延迟。采样会话明确标注
`performance_result=false`，不加入正式性能比值。当前测量与解释见
[验证记录](../../docs/VALIDATION.md)。

## 排空与限制

顺序是停止新 workload → 等全部 ioctl/pthread/客户端退出 → 确认计数查询无
active、provider 无 frame → 等翻译者退出并停止 daemon → 确认无 writer →
`device_session.py retire` 成功（含既有 queue/task/origin 检查）→ 卸载源模块 →
卸载 kdlock。脚本执行此顺序，不强制卸载。`SC_COUNTS` 遇 active 返回 EBUSY。

内核故障、超时、日志丢失或排空不明时立即停止，不自动重试、取消请求或卸载。
检查记录的 PID 和串口，遵循操作手册恢复 guest。超时进程可能仍在内核中，父
进程消失不能证明队列为空；保留的运行中生成目录不能视为完整证据。

这是虚拟机结果，CPU 固定只保证 guest CPU 亲和性，不宣称宿主物理核独占；
模块内存也不额外施加 NUMA 分配策略。原生基线仍使用既有 hook 补丁内核。
quiet 保留必要诊断、原有运行时计数和生成代码正文标记，不是零观测开销。
静态准入、原地发布与 hook reader 生命周期的现有限制继续适用。本实验不扩展
mutex、NUMA 策略、访问时 guard、flags 修复或其他延期正确性功能。

## Caller-clobber 对照入口

`clobber_compare.py` 在同一 `kdclobber2` 内核上构建两份 workload：默认新调用者
和 `KCFLAGS=-DKD_SPIN_LEGACY_CALLER` 旧调用者。每份分别运行 native/kdlock，
每配置五轮，奇数轮逆序；默认覆盖 1/16 cacheline × 1/4/20 线程。
单线程 native 两组用于观察新增调用者保存及桥接成本，不能把该差值解释为纯
spill 周期。每组保存调用者反汇编，保持原 payload、锁外运算和编译选项。

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 3600s python3 bench/spin_cacheline/clobber_compare.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/clobber-new/compare
```

沿用既有实际正文计数、数据检查、退休和排空要求。`summary.csv/json` 报告完整
操作吞吐中位数、ns/op、JIT 比例、NO_JIT 数；`comparisons.json` 比较两种调用者
同后端的中位数；`records.json` 保留所有计划项及未运行/失败记录。NO_JIT 可以
保留性能结果，但不算代理验收，不用更低代理覆盖率解释提速。
`STOP` 文件只在排空后的会话边界生效。新内核操作见
[实验说明](../../kernel_experiments/spin_clobber/README.md)。

该四臂入口的历史 120 会话及调用者成本见[统一 combiner 现场结果](results/20260918-unified-context.md)；
改造前的[caller-clobber v1 对照](results/20260918-clobber-v1.md)保留为历史数据。
两轮采用相同五轮中位数口径，但没有交替执行两个 provider 版本，不能据此独立
归因。结构性状态搬运减少不等于完整操作必然提速。

当前热锁采样按 CPU 独立发现，准备阶段已改为单 CPU 连续 48000 次；其余
测量 CPU 仍可能在测量中建立自己的频率和锁历史。旧冻结版本的成绩保留为
历史结果。本轮没有重新验证完整操作吞吐或 99% JIT，后续对照必须同时报告
实际 JIT 比例，不能将减少代理覆盖误当作提速。
