# 2026-09-17：frame 单锁路径精简后的定向对比

4 个配置、16/16 会话通过数据、实际 JIT 和排空检查：cacheline 1/16，线程
4/20，每线程 100,000 次，每配置两对，原生/kdlock 交替顺序，CPU 0–19、NUMA 0。
这是一轮定向复测，不替代 [此前的完整扫描](20260917-stackless.md)。

生产实现为 `6ef43bf` 加本报告同次提交的 frame 精简：push/pop 不再整块清零，锁记录
只维护有效前缀，完整 context 扫描移至 SELFTEST；正常单锁路径跳过通用事件链、
combiner 快照/比较和远端完成处理，保留一进一出的独立寄存器包。其他 wrapper
出口在执行控制操作前转入原有复杂路径。执行伪代码已同步到
[EXECUTION_PATHS.md](../EXECUTION_PATHS.md)。

## 结果

单位为 Mops/s；口径仍是 kdlock 最佳有效吞吐 / 原生有效吞吐中位数，JIT 占比
取自同一个最佳会话。旧值来自上述同日完整扫描的相同配置。

| cacheline | 线程 | 原生中位 | 旧 kdlock 最佳 | 新 kdlock 最佳 | 新/旧提升 | 新 best/median | 最佳会话 JIT 占比 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 3.252 | 0.647 | 0.725 | +12.0% | 0.2229 | 55.34% |
| 1 | 20 | 3.301 | 0.572 | 0.855 | +49.5% | 0.2591 | 99.84% |
| 16 | 4 | 1.887 | 0.547 | 0.632 | +15.5% | 0.3349 | 59.67% |
| 16 | 20 | 1.955 | 0.572 | 0.850 | +48.6% | 0.4347 | 99.80% |

20 线程的两个点约提高 49%，仍慢于原生。4 线程的 JIT 占比从旧最佳样本的
85.59%/78.97% 降到 55.34%/59.67%，其总吞吐包含更多自行执行的请求，不能将
变化当成纯 JIT 单次耗时的差值。各组只有 2 个样本，且两次扫描之间重启过 VM；
内核身份和负载相同，宿主物理 CPU 独占与频率仍未控制。这组结果支持端到端
性能改善，不构成逐函数周期归因或全线程/全 cacheline 规模的结论。

共完成 19,200,000 次操作，测量期 JIT 正文 8,906,958 次；8 个原生会话、
8 个有实际 JIT 的 kdlock 会话，最长测量批次 2.365 秒。工作负载 C/h/inc 哈希
与此前扫描完全相同，仍包含相同的 4 组锁外乘加。

## 运行与验证

运行于 recovery guest `6.1.159-kdstatic2`，Build ID
`460d77502af4709a0cca794b322cedc20c2cc478`，nokaslr、voluntary，
`bench_quiet=1 jit_timing=0`。源码/build/live 身份重新校验通过，monitor 确认
`pre_static_boot_20260915` 恢复快照。provider、daemon、负载模块和客户端重新构建；
保留既有汇编路径 objtool 警告。

benchmark 期间冻结源码、二进制及 boot ID 未变，全部正常 retire/卸载，新增
内核日志无 fault。宿主独立复算全部会话的计数、CPU 放置、正文差值、聚合和
最佳值口径，核对 184 项冻结源码及 24 项生成映像哈希。61 个生产源码/头文件
与宿主当前版本一致。反汇编确认普通构建的 frame push/pop 没有整块清零或
完整 context 扫描；frame 仍为 656 字节，context 为 5264 字节。

功能验证与失败记录单独维护在 [tests/README.md](../../../tests/README.md#frame-fast-validation)：
9 项定向单元测试通过；单锁、嵌套、native 寄存器、物理 frame 链及远端 live
已验证。远端 IRQ-off 观察器修正前的失败和修正后完整重跑分别保留。七角色/双
CPU mutex mode-4 的 soft lockup 未计作通过；它发生在本轮 benchmark 之前，
随后恢复并重新核对实验内核。这些情况不混入本表的 16 个成功会话。

```sh
python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 16 --threads 4 20 --cpus 0-19 \
  --iterations 100000 --repeats 2 \
  --output /root/kdlock-evidence/spin-frame-fast-20260917
```

- [汇总 CSV](/tmp/kdlock-frame-fast-20260917/evidence/spin-frame-fast-20260917/summary.csv)、[逐会话 CSV](/tmp/kdlock-frame-fast-20260917/evidence/spin-frame-fast-20260917/raw.csv)。
- [独立复算与前次比较](/tmp/kdlock-frame-fast-20260917/audit.json)、[最终身份/排空检查](/tmp/kdlock-frame-fast-20260917/evidence/spin-frame-fast-20260917/postflight.json)。
- guest 持久证据：`/root/kdlock-evidence/frame-fast-20260917/` 和
  `/root/kdlock-evidence/spin-frame-fast-20260917/`。
- [完整归档](/tmp/kdlock-frame-fast-20260917/evidence.tar.gz)，SHA256：
  `30029f2d256562e052d1d48738e0b1fe149cf02e51f2ac9e1b62e3650562fc71`。
  宿主可读副本只提取普通文件和目录，保留原始归档中的符号链接供审计。

本结果页及导航在测量后补写；冻结的说明文件属于各次运行开始时的版本。
