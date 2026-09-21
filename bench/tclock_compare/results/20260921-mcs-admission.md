# 2026-09-21：代理准入移到 MCS 边界

> 历史实验，当前已回退。后续同期复现、候选与最终验收见 [回退调查](20260921-mcs-recovery.md)。

本报告只对应时间域迁移前的冻结源码；其后曾将 spin 时钟移到 MCS admit，
当时仅完成 [时间域功能验证](../../../tests/README.md#admission-clock-validation)。
两版的后续性能复现与撤回结论见上方回退调查。

本轮在已有未提交 ticket 优化之上调整普通与 JIT 虚拟 spin 入口。每次获取仍
记录一次热度；只有 fast/pending 失败后才判断是否代理。TCLock、guest 内核、
mutex 互斥协议、wrapper ABI 和 continuation 退休协议保持原样。

## 实现与分阶段差异

1. 基线是已有 ticket 优化版，**不是** `644f231`。顶层 pending 不占 ticket，
   claim/release guard 合并，队首返回不重复 claim；这些是之前的工作。
2. `note_spin` 只更新统计，`admit_spin` 只在 MCS 查询策略。共享 fast/pending
   helper 不检查策略/JIT/context；原生拒绝直接进入 MCS-only helper，不重新
   CAS/pending。根 ticket 仅为合格代理尝试占用，未就绪时登记后走无 ticket
   原生 MCS。普通物理嵌套/IRQ 用独立 native 计数，不覆盖外层 fast owner。
3. 虚拟 JIT 请求先校验 CALL/账本并占独立 ticket，再 fast/pending；MCS 才
   判断代理，使用父/root 翻译身份。冷/拒绝及 continuation 满时保留 ticket
   走原生 MCS，所有虚拟等待继续服务父 mailbox。既有 node/context 受检错误
   与“JIT 已开始后不重跑正文”的边界保留。
4. 首版拆分在性能对照中回退。ELF 显示 note 仍调用通用采样 helper，而 MCS
   又多一个 admit 调用。最终将通用 helper 标为 always_inline，按固定的
   kind/record/policy 参数消除分支和内部调用；没有增加站点缓存或缓存准入结果。
   此调整同时让共享 mutex 采样 API 特化，但未修改 mutex 获取/释放协议。

`spin_delegate=0` 现在只关闭代理，仍记录全部获取；旧版 off 跳过统计的数据
不能直接与本轮控制相比。内部回退、队列重试和外层重新获取不重复采样。
阈值、窗口、候选替换、重入丢样和 owner/ACK/source lease 检查保留。

具体流程、对象尺寸、分配位置及数据流见
[EXECUTION_PATHS](../../spin_cacheline/EXECUTION_PATHS.md)，
协议见 [locking](../../../docs/design/locking.md#41-native-lock-and-private-queue)。

## 测量方法

三阶段依次为 `baseline`、`optimized`（首版拆分）、`final`（固定参数内联）。
每阶段 1/16 cacheline × 1/4/20 线程 × TCLock/KD × 五轮，共 60 场；每线程
100000 次。每阶段后端正反交替，每场独立装载并排空；不拼接不同冻结输入。
所有样本都保留，未因性能低而剔除。单 CPU 48000 次预热和翻译准备不计时，
测量前停止 daemon。observe、spin_delegate=on、batch 上限 1024，JIT timing 关闭。

环境为 recovery/ext4、40 vCPU、CPU 从 0 起绑定，同 NUMA node 0；
`6.1.159-kdclobber2`、voluntary、nokaslr，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`。加载前实际确认恢复快照
`pre_static_boot_20260915`。宿主 CPU 非独占，没有 PMU 采样和单项消融。
单线程波动及阶段间环境漂移仍是限制，不能将所有变化归于某个字段或调用。

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
LC_ALL=C timeout --kill-after=10s 1800s python3 bench/tclock_compare/run.py \
  --cachelines 1 16 --threads 1 4 20 --backends tclock kdlock \
  --repeats 5 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/mcs-admission-20260921/final
```

三阶段仅换输出目录及对应已归档的源码差异；SSH 另有外层 timeout。

## 完整结果

三阶段各 **60/60** 场通过，各完成 50000000 次操作，竞争 KD 各有 **20/20**
场实际 JIT。最终源文件与冻结输入哈希一致，基线与前轮 ticket 优化版的冻结
源码逐项相同，三阶段 TCLock ELF 相同。没有将旧 HEAD 误作本轮性能基线。

以下单位为 **Mops/s**，均为五次中位数，计入 lock/body/unlock 和锁外工作。

| cacheline | 线程 | KD 基线 | 首版拆分 | 最终版 | 最终变化 | TCLock 基线 / 最终 | 最终 KD/TC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 6.255 | 7.769 | 8.025 | +28.3% | 13.685 / 13.680 | 0.587× |
| 1 | 4 | 2.025 | 1.929 | 1.973 | -2.5% | 2.992 / 2.976 | 0.663× |
| 1 | 20 | 4.989 | 4.031 | 3.995 | -19.9% | 5.022 / 5.010 | 0.797× |
| 16 | 1 | 6.073 | 7.327 | 7.376 | +21.5% | 10.921 / 11.616 | 0.635× |
| 16 | 4 | 1.717 | 1.635 | 1.646 | -4.2% | 2.221 / 2.232 | 0.737× |
| 16 | 20 | 4.771 | 3.923 | 3.918 | -17.9% | 3.379 / 3.344 | 1.171× |

**这不是全面性能提升。** 本轮实现了用户要求的准入顺序，单线程中位吞吐提高，
但四线程下降 2.5% / 4.2%，20 线程下降 19.9% / 17.9%。内联调整相对首版
改善了单线程和部分四线程结果，未消除高竞争回退；不能把额外 helper 调用认定
为完整根因，也不能宣称四线程已经优化到 TCLock 水平。

四线程最终 c1/c16 JIT 占比 51.5% / 54.2%，每批仍约 2 个正文。20 线程仍有
约 99.8% 的真实 JIT，最终平均每批正文数的五次中位数约 774 / 764，基线为
809 / 892；所有配置 `jit_not_ready=0`。因此回退不能解释为关闭了 JIT 或翻译
未就绪；批次变化本身也不是完整因果分析。竞争下的额外准入调用、代码布局及
执行成本仍需针对性定位，当前没有独立周期归因或 PMU 证据。

单线程仍有波动：最终 KD c1 五次范围 6.843–8.295，c16 为 6.325–7.588。
TCLock c16 单线程中位数也上涨约 6.4%，不能将该行所有变化都归为代码收益。
四线程和 20 线程 TCLock 同期变化较小，KD 高竞争回退应作为实际风险保留。

## 功能验证与边界

基础和直接相关 9 项单元检查最终通过；内联调整后重跑采样、入口及基础检查。
最终 plain/nested/early/关闭代理各完成 400000 次，JIT 正文分别为
216338 / 376065 / 99522 / 0；业务、IRQ/preempt 和排空通过。
具体用例、首次失败和修正后的日志索引见
[测试记录](../../../tests/README.md#mcs-admission-validation)。

未运行全量回归、8/16 线程性能、跨 NUMA、多锁性能、adaptive live、mutex JIT
或强制远端 native 并发时序。继承的 owner/ACK、借用退休和节点复用 fixture
继续检查协议，但不作为上述真实内核时序的替代。

## ELF 与证据

最终生产与观察 provider 的 guest 构建通过，保留既有换栈 objtool 告警。
三阶段 ELF 的 node 128 B / align 64、通知偏移 64/65，continuation 768 B /
align 64、frame 648 B、ticket 48 B、栈上 request 24 B 均一致。寄存器包偏移
104；最终恢复汇编的 SP/IP/BP 读取偏移为 `0x100/0xe8/0x88`，读取完成后才
标记 retired 并按 `0x300` 步长收缩存储栈顶。未改变 JIT 物理 RSP/逻辑 SP 模型。

原始证据：guest `/root/kdlock-evidence/mcs-admission-20260921/`。
`baseline/optimized/final` 各含冻结源码、ELF、哈希、records、逐场日志；
`final-functional-*` 是最终版本功能证据，`functional-*` 是首版。
`audit.json`、`layout.json`、`*-layout/`、`host-guest-verified.json` 保存审计结果。
宿主与 guest 的 17 个改动源码/fixture 文件已逐项核对哈希一致。
`stage2-mcs.patch` 与 `stage3-inline.patch` 是本轮生产差异；
`kd-four-optimization.patch` 保留已存在的 ticket 阶段，`kd-mcs-working-tree.patch`
保留工作树差异。完整对象解析使用 pahole/BTF；pyelftools 的 DWARF 解析失败
另留日志，不当作布局验收通过。所有测量结束后 worker/daemon 和模块排空。

归档 `/root/kdlock-evidence/mcs-admission-20260921.tar.gz` 已取回宿主
`bench/.tmp/mcs_admission_20260921/`，SHA256：
`8d46c2735e9c636fbca4d60968a7cd609290ad97832ed869de0bfb1b7d1411ff`。
188 份逐场内核日志未发现 BUG/Oops/WARNING/stall。没有自动提交 Git；此前
未提交的抢占配对、ticket 和文档改动均保留。
