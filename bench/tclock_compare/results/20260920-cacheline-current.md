# 2026-09-20：当前版本切回 cacheline 的三方性能对比

**正式 150/150 场全部通过，完成 147000000 次操作。** 本轮仅以
`--workload cacheline` 切换构建负载，锁协议、JIT 分析器和临界区源码没有修改。
沿用上一轮哈希表 JIT 修复后的版本，比较 Linux 原生锁、TCLock、kdlock 的直接 API。

20 线程下，1 cacheline 的 kdlock 吞吐为 Linux 的 **0.905×**、TCLock 的
**0.744×**；16 cacheline 则为 Linux 的 **1.501×**、TCLock 的 **1.094×**。
较大的 cacheline 负载在高竞争时出现 kdlock 优势，四线程的差距仍然存在。
本轮没有阶段计时或硬件事件采样，不能据此确定某个步骤的具体成本。

## 临界区与配置

所有线程竞争同一把锁。每个数据槽 64 字节对齐、步长 64 字节，只有开头的
64 位计数器参与读改写。N 为 1 或 16，**不是读写每条 cacheline 的全部 64 字节**。
实际代码见 [payload.h](../../../workload_modules/spin_cacheline/payload.h)，正文由
宏固定展开，下面循环仅表达语义：

```c
SC_LOCK(N);
for (i = 0; i < N; i++)
    WRITE_ONCE(sc_data[i].value, READ_ONCE(sc_data[i].value) + 1);
SC_UNLOCK();
```

- 1/16 cacheline × 1/4/8/16/20 线程 × 三后端 × 五轮；每线程 100000 次。
  每个线程绑定一个 guest CPU，使用 CPU 0 起的前 T 个，全部位于 NUMA node 0。
- 后端顺序逐轮正反交替。显式准备及单 CPU 48000 次预热不计时，daemon 和
  翻译进程在正式计时前已退出。计时包含完整锁操作、正文、锁外四组乘加及循环。
  摊销 ns/op 是 wall 时间除以总完成数，不是单次 lock 延迟。
- TCLock 保留 C 内联汇编换栈、批次上限 1024、关闭 IRQ 检查和无新增执行计数。
  不恢复 `need_resched()` 批次截断或 `cond_resched()` 调度点；正常抢占配对仍保留。
- TCLock 后端和三个 direct workload 均关闭模块 UBSAN；内核内部配置不变。
  统一 API/hotlock 筛选不进入被测路径，kdlock 的实际 JIT 完成计数仍有观测成本。
- 内核 `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，nokaslr、voluntary。
  没有重建内核，不宣称 guest CPU 与宿主物理核独占对应。

## 五轮中位数

吞吐单位为 **Mops/s**，越大越好；JIT 占比同样取五轮中位数。

| cacheline | 线程 | Linux | TCLock | kdlock | kd / Linux | kd / TCLock | kd JIT 占比 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 16.889 | 13.676 | 5.571 | 0.330× | 0.407× | 0.00% |
| 1 | 4 | 3.757 | 2.971 | 1.490 | 0.397× | 0.501× | 55.78% |
| 1 | 8 | 3.839 | 4.300 | 2.399 | 0.625× | 0.558× | 90.16% |
| 1 | 16 | 3.888 | 5.041 | 3.685 | 0.948× | 0.731× | 99.74% |
| 1 | 20 | 4.106 | 4.992 | 3.715 | 0.905× | 0.744× | 99.83% |
| 16 | 1 | 13.507 | 11.213 | 5.225 | 0.387× | 0.466× | 0.00% |
| 16 | 4 | 2.100 | 2.232 | 1.298 | 0.618× | 0.581× | 52.47% |
| 16 | 8 | 2.283 | 3.181 | 2.344 | 1.027× | 0.737× | 91.37% |
| 16 | 16 | 2.419 | 3.469 | 3.596 | 1.487× | 1.037× | 99.79% |
| 16 | 20 | 2.434 | 3.341 | 3.654 | 1.501× | 1.094× | 99.81% |

kdlock 全部 **40/40 场竞争测量**都有实际 JIT 正文增长。单线程无竞争，正文
原生执行、JIT 为零，入口仍成功生成并发布；不将这些场次记为实际 JIT 通过。
TCLock 的额外代理计数已删除，本轮代理量仍为 `UNMEASURED`，不推断其批次长度。

样本全部保留，没有剔除异常高值。1 cacheline 单线程 Linux 的一轮为
48.373 Mops/s，其余四轮为 16.650–16.919；16 cacheline、20 线程 Linux
有一轮为 3.002，其余为 2.321–2.443。上表使用五轮中位数，原始波动见逐场记录。
这些数据属于当前设置，不能与 9/19 仍带检查/额外计数的成绩拼成同一组。

## 验证与证据

编译、基础测试及模块运行全部在 recovery guest；加载前从 monitor 确认
`pre_static_boot_20260915`。基础两个 C 测试和运行器六项检查通过。
先跑 1/16 cacheline × 1/4 线程的 **12 场样例、300000 次操作**，全部通过；
随后运行完整 150 场，没有失败、未执行项或中途重试。

每场核对所有 16 个槽的增量、有效/未访问槽、完成数、CPU 亲和性、IRQ/preempt
状态及排空。kdlock 核对生成物、发布身份、测量前后 JIT 正文计数及最终退休；
TCLock 核对实际换栈机器码、额外计数符号缺失及队列/上下文静止状态。
逐场内核日志未发现故障，最终 worker/daemon 退出、测试模块全部卸载。
源码和二进制哈希已离线复核；相对上一轮正式哈希表基线，执行源码没有变化，
冻结文件差异仅为两份结果索引文档。

没有运行全量回归或 mutex 负载；provider 保留默认 `mutex_jit=1` 参数，
本轮只验证 spin。构建日志保留现有 objtool 告警。未提交 Git，工作树基于
`b4b16ca09d4b2833196b265e93bac934583fa3ef`，实际测试版本以冻结哈希为准。

正式命令（另有宿主 SSH 外层 timeout，使用固定依赖 venv）：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
LC_ALL=C timeout --kill-after=10s 3600s python3 bench/tclock_compare/run.py \
  --workload cacheline --cachelines 1 16 --backends native tclock kdlock \
  --threads 1 4 8 16 20 --repeats 5 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/cacheline-current-20260920-compare01
```

[汇总 CSV](../../.tmp/cacheline_current/cacheline-current-20260920-compare01/summary.csv)、
[逐场记录](../../.tmp/cacheline_current/cacheline-current-20260920-compare01/records.json)、
[离线校验及样本分布](../../.tmp/cacheline_current/comparison-audit.json)、
[完整归档](../../.tmp/cacheline_current/cacheline-current-20260920-all.tar.gz)。
归档包含样例、正式测量、冻结源码/二进制、JIT 生成物、基础验证和恢复快照证据。
SHA256：`09ac875cbdd75038133b5988629ca2c155b2fffa306bce74809e0bb8ec6874c2`。
