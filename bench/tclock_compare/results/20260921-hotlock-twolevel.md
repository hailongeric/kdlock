# 2026-09-21：CPU / 单锁两级 1024 次热度确认

基于 `175d73b` 工作树，保留此前文档和性能报告。改动只涉及热锁采样、相关测试和
文档；获取/解锁协议、ticket、continuation、TCLock 和 guest 内核均未修改。

## 算法与成本

- CPU/type 批次从 10240 降至 1024，保留 40000000000 TSC ticks 窗口。
  单锁使用独立的 1024 次批次与 2500000000 ticks 窗口；等于窗口或时间倒退均冷。
- 模块初始化预分配并建立时间起点，调用者保证锁字有效；删除逐次地址/表有效性
  检查和首次采样初始化分支。CPU 冷时只记录 CPU 计数，不查候选哈希表。
- CPU 持续热保留单锁批次，不遍历六条候选检查过期。CPU 冷却/重新变热重置候选
  统计和缓存热值；替换地址重置独立单锁计数/热值，score/error 只用于淘汰。
- 同次到期共享一次 TSC；query 不采时或计数，observe 固定准入但记录同样统计。
  正常单热锁批次错开时，两种采时分别发生，不能声称每 1024 次至多一次 TSC。
- 新字段利用原有填充，candidate/table/cpu 仍为 40/288/576 字节，CPU 对齐 64。
  无获取时分配，也未增加每 CPU 预分配空间。

时钟窗口不随次数缩小，所以频率门槛也放宽。单热锁从冷状态自然确认最快在
第 2047 次 record；初始化至首批的空闲计入 CPU 窗口，缓存热值只在各自下次
定时检查时更新。这是策略语义变化，不是只改一个轮询周期。
实现流程和所有对象的数据流见 [EXECUTION_PATHS](../../spin_cacheline/EXECUTION_PATHS.md#51-准备热度与快速获取)。

## 验证方法

仅在 recovery guest `6.1.159-kdclobber2` 构建和运行，保留
`pre_static_boot_20260915` 快照，NUMA=0，CPU 从 0 绑定前 T 个、同 NUMA node 0。
内核 Build ID、依赖、冻结源码和二进制均由运行器核验。普通及 SELFTEST 构建
使用 W=1；SELFTEST 仅构建，本轮未装载专用生命周期探针。

定向单元入口：

```sh
make -C tests/unit run PY_TESTS='infrastructure/test_hotlock_sampling.py spin/test_spin_preempt.py'
```

覆盖初始化/有效地址契约、1023/1024 边界、独立批次、同次复用时钟、零时间、
等于窗口及倒退、CPU 冷热转换、query、哈希冲突/摘链/替换不继承热度、CPU/type
隔离、抢占复用及重入。10 个错误变体都必须被 oracle 拒绝，不能用编译失败代替。
fixture 使用替代内核原语，真实 JIT 另用 functional 入口验收。

新旧 provider 独立构建，共用同一 workload/客户端/翻译器；每场加载全新会话并排空。
O 为本次修改前，N 为两级采样。分别跑 observe 和 adaptive，各包含
c1/c16 × t1/4/20 × O/N × 五轮 = 60 场，每线程 100000 次，奇数轮反序。
沿用相同单 CPU 48000 次预热、测量前静置及数据/IRQ/preempt/JIT/排空 oracle。
固定准入用于观察采样开销，adaptive 包含自然积累热度的策略影响；不把 NO_JIT
算作实际 JIT 通过，也不以 observe 的成绩代替 adaptive 效果。未重新运行 TCLock，
本轮只比较同一 KD 实现修改前后。

## 功能与布局结果

- 基础及直接相关单元 4/4 通过，10/10 错误变体被拒绝。
- 普通与 SELFTEST provider 的 W=1 构建通过，ELF 实测大小为 40/288/576 字节，
  `hot`/`samples` 偏移为 33/34，CPU 对齐 64 字节。新旧观察版构建均保留相同的
  11 条已有手写恢复/调用汇编 objtool 警告；没有新增采样器编译诊断。
- adaptive/plain/c1/t4 功能入口完成 400000 次操作，实际 JIT 正文 205399 次；
  业务、IRQ/preempt、队列和退休检查通过，正常排空。
- 初次布局核查先后遇到 gdb 未安装、旧 pyelftools 无法解读 DWARF 和脚本对齐
  文本匹配错误；改用已安装的 pahole 并修正匹配后通过，失败脚本/日志保留。

## 同期性能结果

**120/120 场通过，共 100000000 次操作，全部排空，无内核错误。** 两种模式各有
40/40 场竞争会话取得实际 JIT；各 20 场单线程为 NO_JIT，作为正确的自执行
性能样本保留。所有源码/二进制冻结哈希通过最终核对，未删除慢样本或补测择优。
下表为五轮完整操作吞吐中位数，单位 Mops/s；变化以 O 为分母。

| 模式 | cacheline | 线程 | 修改前 O | 两级采样 N | 变化 |
| --- | ---: | ---: | ---: | ---: | ---: |
| observe | 1 | 1 | 6.224 | 5.827 | -6.38% |
| observe | 1 | 4 | 2.034 | 2.014 | -1.02% |
| observe | 1 | 20 | 5.008 | 4.997 | -0.21% |
| observe | 16 | 1 | 5.862 | 5.773 | -1.52% |
| observe | 16 | 4 | 1.731 | 1.716 | -0.82% |
| observe | 16 | 20 | 4.756 | 4.766 | +0.20% |
| adaptive | 1 | 1 | 6.469 | 6.198 | -4.19% |
| adaptive | 1 | 4 | 2.123 | 2.046 | -3.61% |
| adaptive | 1 | 20 | 4.492 | 4.945 | +10.09% |
| adaptive | 16 | 1 | 6.078 | 5.849 | -3.77% |
| adaptive | 16 | 4 | 1.722 | 1.722 | -0.02% |
| adaptive | 16 | 20 | 3.888 | 4.600 | +18.32% |

observe 二十线程接近持平，四线程约下降 1%，单线程 c1/c16 下降 6.38%/1.52%。
采时频率上升及独立单锁计数有成本；本轮没有逐指令采样，不能把差异精确归因于
某条指令，也不能仅凭删去检查就宣称更快。

adaptive 二十线程 c1/c16 提升 10.09%/18.32%，实际 JIT 比例中位数从
79.65%/79.64% 升至 97.79%/97.78%。这与冷 CPU 更早完成两级确认相符；由于
改变了准入时机和频率门槛，不能当作纯采样器开销改善。四线程 JIT 比例约从
40.2%/41.4% 升至 47.3%/48.3%，吞吐却为 −3.61%/−0.02%；单线程下降
4.19%/3.77%。保留用户选择的 1024 次语义，如实记录低竞争代价，不宣称全面提速。

## 未覆盖边界

本轮未运行全量协议/组件矩阵、mutex 实际 JIT、嵌套/提前释放专项、远端 native
续跑或无锁 relay 的强制时序。这些协议没有修改，历史通过仍仅对应历史版本。
单元中的重入和时间控制是替代原语，不能代替真实 NMI/多锁并发覆盖。
仅有五轮短批次、1/4/20 线程及单 NUMA guest 数据，不据此推断长期稳态、跨 NUMA
或所有业务负载的收益。更低的计数阈值本身不代表频率判定更严格或代理净收益更高。

## 证据与复现

原始 guest 目录：`/root/kdlock-evidence/hotlock-twolevel-20260921/`。
[完整归档](../../.tmp/hotlock_twolevel_20260921/hotlock-twolevel-20260921.tar.gz)
SHA256：`eb5f6f0ecdfd82b313147dcd3ef9d864bea77f2948ed4b2c403d02e6f3dfb91b`。

归档包含修改前源码/差异、独立 O/N 源码与 provider、共同 workload/客户端、
普通/SELFTEST ELF 与布局、单元/变异结果、工具失败日志、functional、两组完整
records/summary/kernel 日志，以及 `audit.json`、`implementation.patch`、`tests.patch`。
O/N 的源码快照记录构建时输入；本报告和更新后的说明文档在当前工作树维护。
最终核对宿主实现/测试哈希与已测 N 一致；只读归档核验见同目录 `offline-audit.json`。

本次冻结脚本用法（只供核对原始 argv；复现须选择新证据目录并重新核验环境）：

```sh
python3 /root/kdlock-evidence/hotlock-twolevel-20260921/compare.py \
  --name observe --hotlock-mode observe --versions O N \
  --cachelines 1 16 --threads 1 4 20 --repeats 5 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
# 第二组使用 --name adaptive --hotlock-mode adaptive；其他条件不变。
```

归档脚本不在宿主运行，离线校验不加载其中任何代码。当前性能结论只适用于表中
这批冻结输入，已有 `175d73b` 三方完整报告继续作为修改前历史基线保留。
