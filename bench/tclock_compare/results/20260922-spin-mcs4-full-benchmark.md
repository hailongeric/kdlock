# 2026-09-22：MCS4 / 40亿CPU窗口完整三方单轮 bench

按用户要求运行一遍默认完整 bench：c1/c16 × 1/4/8/16/20线程 × Linux/TCLock/KD，
每配置一轮。**30/30场通过，2940万次计时操作全部完成并排空，8/8竞争KD有实际JIT。**

测量当前工作区：基于`383249f`，spin CPU每4次实际MCS入队检查，spin/mutex CPU
共用40亿TSC ticks窗口；单锁阈值32（第33次检查）、25亿单锁窗口、task-only统计、
已移除busy/barrier及已有CPU pin继续保留。运行前328个跟踪文件与guest哈希一致，
运行期间输入未变；基础提交及完整工作区差异随`preflight/`归档。本报告与实测版本一起提交。

## 三方结果

plain/cacheline、observe、spin_delegate=on；每线程100000次，每配置仅第0轮。
单CPU48000次预热及JIT准备不计时。以下为 **Mops/s / ns/op**，包含完整操作、
锁外四组乘加和循环；并非独立获取锁延迟。`best_*`兼容字段对应唯一有效样本。
observe固定准入，结果反映该模式的完整路径开销，不是adaptive准入效果的测量。

| cacheline | 线程 | Linux | TCLock | KD | KD/Linux | KD/TCLock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 18.105 / 55.23 | 13.643 / 73.30 | 6.650 / 150.37 | 0.367× | 0.487× |
| 1 | 4 | 3.435 / 291.12 | 2.962 / 337.65 | 1.875 / 533.41 | 0.546× | 0.633× |
| 1 | 8 | 3.715 / 269.14 | 4.339 / 230.45 | 4.063 / 246.09 | 1.094× | 0.936× |
| 1 | 16 | 3.857 / 259.29 | 5.042 / 198.34 | 4.981 / 200.75 | 1.292× | 0.988× |
| 1 | 20 | 4.264 / 234.52 | 4.919 / 203.28 | 5.009 / 199.65 | 1.175× | 1.018× |
| 16 | 1 | 13.159 / 75.99 | 11.243 / 88.95 | 7.019 / 142.47 | 0.533× | 0.624× |
| 16 | 4 | 2.167 / 461.43 | 2.194 / 455.74 | 1.603 / 623.96 | 0.740× | 0.730× |
| 16 | 8 | 2.228 / 448.83 | 3.086 / 324.06 | 4.024 / 248.48 | 1.806× | 1.304× |
| 16 | 16 | 2.344 / 426.62 | 3.285 / 304.40 | 4.788 / 208.86 | 2.043× | 1.457× |
| 16 | 20 | 2.672 / 374.25 | 3.261 / 306.67 | 4.768 / 209.74 | 1.784× | 1.462× |

20线程KD c1/c16为5.009/4.768 Mops/s，分别为TCLock的1.018×/1.462×。
c1在16线程与TCLock接近，c16在8/16/20线程均高于两组对照；单线程和四线程仍落后。

相对[上一轮MCS1/400亿窗口](20260922-spin-mcs1-lock32.md)，KD在c1/c16的变化为：

| 线程 | c1 | c16 |
| --- | ---: | ---: |
| 1 | -10.16% | -1.38% |
| 4 | -0.32% | -1.03% |
| 20 | -0.05% | -0.71% |

上述是跨批次单轮比较，Linux/TCLock也有波动，不能据此确定稳定收益或将差值归因于
阈值调整。上一轮未测8/16线程，不将更早版本补入同一比较。没有新增旧KD测量臂。

## 环境与核验

- recovery guest `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；ext4、nokaslr、voluntary。
  既有内核源码/build及捕获基线通过运行器核验，固定Python依赖检查通过。
- monitor确认快照`pre_static_boot_20260915`。运行前后40个vCPU保持一对一绑定宿主
  CPU0..39，前20个同物理插槽；guest工作线程使用对应编号的CPU。
- 本轮构建normal provider、daemon、三方workload及对照后端；保留Perl locale等构建告警。
  实际加载normal模块，provider默认`mutex_jit=1`，负载仅spin，不构成mutex JIT验证。
- 30场业务数据、CPU亲和性、IRQ/preempt、内核日志、退休及排空检查通过。
  8场竞争KD有实际JIT，2场单线程KD为NO_JIT，单线程卸载日志没有spin热表记录。
  TCLock代理计数仍为UNMEASURED，不能把未知写为零。
- 最终无worker、daemon、workload或provider残留；248份冻结输入与8份二进制哈希一致。
  结果文档在运行结束后更新，执行源码与冻结版本一致。
- 本轮只运行完整observe性能矩阵，未追加单元、SELFTEST、adaptive功能、nested/early、
  mutex、RCUHT或PMU。阈值修改的此前独立单元/构建记录见[测试入口](../../../tests/README.md)，
  不计作本次重跑。

## 命令与证据

完整命令、环境、退出码、源文件、ELF、生成物和日志位于guest：
`/root/kdlock-evidence/spinbench-mcs4-20260922T102755Z/`。

```sh
python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --workload cacheline --cachelines 1 16 \
  --threads 1 4 8 16 20 --repeats 1 --iterations 100000 \
  --scenario plain --hotlock-mode observe --spin-delegate on \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/spinbench-mcs4-20260922T102755Z/observe
```

固定venv、恢复快照标记及内外层timeout见归档`validation/kdlock-bench-mcs4-run.sh`。

- [三方汇总](../../.tmp/spinbench-mcs4-20260922T102755Z/observe/summary.csv)
- [全部性能样本](../../.tmp/spinbench-mcs4-20260922T102755Z/observe/records.json)
- [运行后审计](../../.tmp/spinbench-mcs4-20260922T102755Z/post-run-audit.json)
- [完整归档](../../.tmp/spinbench-mcs4-20260922T102755Z/spinbench-mcs4-20260922T102755Z.tar.gz)
- [离线归档核验](../../.tmp/spinbench-mcs4-20260922T102755Z/archive-audit.json)

证据位于忽略目录，新checkout不自带原始产物。完整归档SHA256：
`707daaa0340e0e9cc355caf5aca1dfde1e65e477db1513d41694f123ebef117a`。
