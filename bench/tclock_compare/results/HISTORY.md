# 性能实验历史索引（2026-09-21 至 09-23）

当前完整结果见[168场三轮矩阵](20260923-spin-default-heat-full3.md)；布局优化、长单线程对照和因果边界见[性能调查](20260923-spin-single-hot-balance.md)。昨日[恢复基线](20260922-performance-recovery.md)、[普通spin IRQ/wrapper验证](20260922-plain-spin.md)和[统一解锁ABI验证](20260923-spin-generic-unlock.md)单独保留。更早阶段见[9月15日至21日索引](../../spin_cacheline/results/HISTORY.md)。

本页合并30份过时阶段报告，其中9份在整理前已删除。仅整理文档，没有重跑实验或删除原始证据。固定Git原文保留完整表格、旧命令、失败尝试和未覆盖边界；下列“原文”提交是文档保存点，测量输入身份单独列出，二者不能混用。已有工作树修改以各归档patch/source manifest为准。

所有原文链接固定到整理前 `39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43`，本地可用 `git show <提交>:<原路径>` 读取。原始证据位于忽略目录，新checkout不自带；SHA256沿用原报告记录，本次未重新认证全部历史归档。不同采样策略、ABI、预热及统计口径不得跨批次取优。

<a id="20260921-current-benchmark"></a>
## 2026-09-21：当前版本完整三方 benchmark

输入：`175d73b`。150场五轮中位数，旧三方基线。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260921-current-benchmark.md)；[完整归档](../../.tmp/benchmark_175d73b/benchmark-175d73b-20260921.tar.gz)、[汇总 CSV](../../.tmp/benchmark_175d73b/summary.csv)、[审计与全部样本](../../.tmp/benchmark_175d73b/audit.json)。
归档SHA256：`a9ff4efde17cbaa824318aa1ba359c560f7ccbb608a315205aa45158e6c08155`。

<a id="20260921-fast-path-optimization"></a>
## 2026-09-21：精简 KD 无竞争入口

输入：`1b2c320 + 冻结修改`。延后request/ref和合并context的历史优化；其成绩不代表后续采样版本。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260921-fast-path-optimization.md)；[完整归档](../../.tmp/fastopt_20260921/fastopt-20260921.tar.gz)、[宿主离线复核](../../.tmp/fastopt_20260921/offline-audit.json)。
归档SHA256：`81bea3201778582923a869fb686cab4dc6a86951d5828326a88e449a090b1153`。

<a id="20260921-hotlock-direct"></a>
## 2026-09-21：去除热锁候选后的同期性能对照

输入：`当时两级候选与直接哈希冻结输入`。直接哈希对照，未证明整体提升；后续表结构和采样均有变化。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260921-hotlock-direct.md)；[完整归档](../../.tmp/hotlock_direct_benchmark_20260921/hotlock-direct-benchmark-20260921.tar.gz)。
归档SHA256：`69559e28449a58e8c5f10a2aed6968a70d7c2f34b08734b1453b8bf9fb458e7c`。

<a id="20260921-hotlock-twolevel"></a>
## 2026-09-21：CPU / 单锁两级 1024 次热度确认

输入：`175d73b + 冻结修改`。两级候选实验，已由精确地址计数替代；保留首次失败和全部样本。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260921-hotlock-twolevel.md)；[完整归档](../../.tmp/hotlock_twolevel_20260921/hotlock-twolevel-20260921.tar.gz)。
归档SHA256：`eb5f6f0ecdfd82b313147dcd3ef9d864bea77f2948ed4b2c403d02e6f3dfb91b`。

<a id="20260921-single-thread-profile"></a>
## 2026-09-21：单线程执行路径与 PMU profiling

输入：`优化前冻结输入`。单线程PMU诊断，不能当成当前指令数。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260921-single-thread-profile.md)；[完整归档](../../.tmp/single_thread_profile_20260921/single-thread-diagnosis-20260921.tar.gz)、[离线核验](../../.tmp/single_thread_profile_20260921/offline-audit.json)。
归档SHA256：`e5a1441d7a00d5d45ce4199481bea240d5b45cae81653ccfc2eeeb74e8fa8368`。

<a id="20260921-threeway-current"></a>
## 2026-09-21：Linux / TCLock / 当前 kdlock 三方实测

输入：`1b2c320 + 文档修改`。150场五轮中位数，不能与后续单轮/最大值直接拼接。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260921-threeway-current.md)；[完整归档](../../.tmp/threeway_current_20260921/threeway-current-20260921-2253.tar.gz)、[宿主离线核验](../../.tmp/threeway_current_20260921/offline-audit.json)。
kd_hotlock.c SHA256：`f415fe99263ef63dd74544167528df4b8c61dd40e51182b519ff6c701e1f3d92`；完整归档 SHA256：`949d9e02523626e72cf441b7a51b1de1d02d5148fc882a10a9774980f79820b8`。

<a id="20260922-adaptive-quick"></a>
## 2026-09-22：默认双准入模式与 adaptive 快速三方结果

输入：`4081b09 + 运行器修改`。18场、单轮adaptive；20线程5.048/4.818 Mops/s。默认轮次现已改为3。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-adaptive-quick.md)；[完整归档](../../.tmp/adaptive-quick-20260922T110215Z.tar.gz)、[三方汇总](../../.tmp/adaptive-quick-20260922T110215Z/adaptive/summary.csv)、[运行后审计](../../.tmp/adaptive-quick-20260922T110215Z/post-run-audit.json)。
归档SHA256：`466f6aaefa4d74f70dfd5c057fe841852c60bb9dac03c844f0ff3c32f14d14ea`。

<a id="20260922-direct-mapped-performance"></a>
## 2026-09-22：1024 槽直接映射热表的三方性能

输入：`1b2c320 + 当时工作树`。1024槽共享直接映射，150场五轮中位数；竞争退化，随后回退。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-direct-mapped-performance.md)；[完整归档](../../.tmp/directperf_20260922/directperf-20260922.tar.gz)、[宿主离线复核](../../.tmp/directperf_20260922/offline-audit.json)。
kd_hotlock.c SHA256：`bec257168bb51291e35d6e00f653f70cb1c4312670920991ef954e36606f6e07`；完整归档 SHA256：`5ddf8bc91757e3188d72cd4448c99a2d4c7d8ead32473a12cc20d65f4ac034e1`。

<a id="20260922-directhash-v2-performance"></a>
## 2026-09-22：512槽直接映射 spinlock 三方性能

输入：`bf16b10 + 512槽修改`。两轮性能，20线程3.916/3.831 Mops/s；按用户要求撤回。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-directhash-v2-performance.md)；[完整归档](../../.tmp/spinbench_directhash_20260922/spinbench-directhash-20260922.tar.gz)、[原始两轮和汇总](../../.tmp/spinbench_directhash_20260922/summary.csv)。
归档SHA256：`e82c805eca223b27c688fa4bce183d0dddf415c0ce8a96451b61ee545a8f454a`。

<a id="20260922-directhash-v2-rollback"></a>
## 2026-09-22：撤回512槽直接映射并复核性能

输入：`生产恢复bf16b10`。定向12场，20线程5.002/4.771；保留原统计口径。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-directhash-v2-rollback.md)；[本地归档](../../.tmp/rollback_v2_20260922/rollback-v2-20260922.tar.gz)。
归档SHA256：`b1c6f1caf981300323862e828c67a908ca2de3f0b1c26097fd2403b25cc39134`。

<a id="20260922-directhash-v2"></a>
## 2026-09-22：分类型热表改用直接映射槽

输入：`bf16b10 + 512槽修改`。功能实验通过，未做性能；随后因独立性能退化撤回。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-directhash-v2.md)；[本地证据目录](../../.tmp/directhash_v2_20260922/)。
原报告未给归档SHA256；输入清单及首次测试匹配失败保留在证据目录与原文中。

<a id="20260922-hotlock-core"></a>
## 2026-09-22：无抢占检查、无 busy 门的热表核心

输入：`1b2c320 + 当时工作树`。删除busy/核心pin检查的功能阶段；此批未做性能，后续发现竞争退化。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-hotlock-core.md)；[完整归档](../../.tmp/hotcore_20260922/hotcore-20260922.tar.gz)、[宿主离线复核](../../.tmp/hotcore_20260922/offline-audit.json)。
归档SHA256：`c2b1063f29dfacdd61919e78f153921a08f589963180955ba6fe812e71faf06b`。

<a id="20260922-hotlock-direct-mapped"></a>
## 2026-09-22：热表改为 1024 槽直接映射

输入：`1b2c320 + 当时工作树`。1024槽共享直接映射功能阶段，已回退。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-hotlock-direct-mapped.md)；[完整归档](../../.tmp/hotdirect_20260922/hotdirect-20260922.tar.gz)、[宿主离线复核](../../.tmp/hotdirect_20260922/offline-audit.json)。
归档SHA256：`881e70add4caa4e632b487a5d1eac9a9e748e2ef072cf06567f192b02785be42`。

<a id="20260922-hotlock-shared-table"></a>
## 2026-09-22：spin/mutex 共用 per-CPU 热表

输入：`1b2c320 + 当时工作树`。spin/mutex共享类型表功能阶段，已回退。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-hotlock-shared-table.md)；[完整归档](../../.tmp/hotshared_20260922/hotshared-20260922.tar.gz)、[宿主离线复核](../../.tmp/hotshared_20260922/offline-audit.json)。
归档SHA256：`54fd38c7f43f6cc107fce0ab169938767203765ae6acbe147fb5c74d6676a3ff`。

<a id="20260922-restored-full-benchmark"></a>
## 2026-09-22：恢复256桶版本后的完整三方benchmark

输入：`生产与bf16b10一致`。60场两轮最大值；20线程4.969/4.788 Mops/s。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-restored-full-benchmark.md)；[原始归档](../../.tmp/spinbench_restored_20260922/spinbench-restored-20260922.tar.gz)、[汇总CSV](../../.tmp/spinbench_restored_20260922/summary.csv)。
归档SHA256：`72824b02cc049b11de5c3c7c5c864aa82783deed3cb18995bef1e0b2836ec5e8`。

<a id="20260922-single-round-baseline"></a>
## 2026-09-22：当前版本完整三方单轮基线

输入：`1928434`。30场单轮；20线程4.974/4.760 Mops/s。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-single-round-baseline.md)；[完整归档](../../.tmp/spinbench-baseline-20260922T082523Z/spinbench-baseline-20260922T082523Z.tar.gz)、[汇总 CSV](../../.tmp/spinbench-baseline-20260922T082523Z/summary.csv)、[运行后审计](../../.tmp/spinbench-baseline-20260922T082523Z/post-run-audit.json)、[归档 SHA256 校验](../../.tmp/spinbench-baseline-20260922T082523Z/archive-audit.json)。
归档SHA256：`24e9ef5d788cec1ce3d8deab270ec067f97da0a2f2dbd7a8681b31ecde97a206`。

<a id="20260922-spin-cold-clobber-queue"></a>
## 2026-09-22：内联 CPU 热度、原 clobber 与冷队列门槛

输入：`2db1e74 + 冻结修改`。取消手工寄存器保存并引入队列门槛；首次少线程JIT判定失败保留，后续50场单列，队列门槛现已删除。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-cold-clobber-queue.md)；[完整归档](../../.tmp/cold-clobber-20260922.tar.gz)、[分段性能核对](../../.tmp/cold-clobber-20260922/performance-audit.json)、[JIT机器码核对](../../.tmp/cold-clobber-20260922/jit-code-audit.json)、[源码/ELF核对](../../.tmp/cold-clobber-20260922/source-code-audit.json)、[PMU汇总](../../.tmp/cold-clobber-20260922/pmu/pmu-summary.json)。
归档SHA256：`152b3e9a0ddb4b4751ef9581bc213f1385fdf4829b477dc5319ff3aa99768e45`。

<a id="20260922-spin-cold-stage1"></a>
## 2026-09-22：配对冷路径，第一阶段

输入：`第一阶段冻结配对C壳`。局部cookie；单线程改善，20线程下降12.64%–14.43%，当时默认关闭。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-cold-stage1.md)；[完整stage1归档](../../.tmp/cold-fast-20260922/stage1.tar.gz)。
归档SHA256：`8312bee47b064ad047f28ca313a4473094383dd16ff1d8c50e8212e6176826dd`。

<a id="20260922-spin-cold-stage2"></a>
## 2026-09-22：公共调用精简，第二阶段

输入：`31d8fd2 + 冻结修改`。公共调用精简但仍为局部cookie；竞争验收未通过，不代表per-CPU版。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-cold-stage2.md)；[stage2.tar.gz](../../.tmp/cold-fast-20260922/stage2.tar.gz)。
归档SHA256：`80d976d289adaecdce6a6e2331c6945b0723aeb02a944a4cd0b07ba74ba98716`。

<a id="20260922-spin-cpu-hot-cookie"></a>
## 2026-09-22：共享 CPU 热度 cookie 与冷态快路径

输入：`d1c8ddf + 冻结修改`。36场性能、8场功能、12场单线程PMU；较快OFF与较慢ON是不同调用壳，均非现行唯一调用壳。
首次paired/gate-off脚本漏拷冻结源码，翻译器在负载开始前退出；失败已排空并保留。修正控制脚本后8场功能通过，未改生产源码或重跑性能矩阵；竞争性能验收仍未通过。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-cpu-hot-cookie.md)；[完整归档](../../.tmp/cold-fast-20260922/percpu-hot.tar.gz)、[PMU汇总](../../.tmp/cold-fast-20260922/percpu-hot/pmu/pmu-summary.json)、[源码/机器码核对](../../.tmp/cold-fast-20260922/percpu-hot/same-source-code-audit.json)。
归档SHA256：`e8eefa660dc6cb0fe0f214c86df85695ec708f1392462f4f2103e82a6d67b0e8`。

<a id="20260922-spin-mcs-frequency"></a>
## 2026-09-22：spin CPU 热度改为 MCS 入队频率

输入：`bf16b10 + MCS1024修改`。20线程4.042/3.959，相对当时恢复版下降18.7%/17.3%；随后撤回。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-mcs-frequency.md)；[完整归档](../../.tmp/spin_mcs_20260922/spin-mcs-20260922.tar.gz)、[observe 汇总](../../.tmp/spin_mcs_20260922/observe/summary.csv)、[adaptive 汇总](../../.tmp/spin_mcs_20260922/adaptive/summary.csv)、[审核结果](../../.tmp/spin_mcs_20260922/audit.json)。
MCS实验归档 SHA256：`4c91bdfc7e24a6bfe3ac621dc9375fe170395d60e2995f7e4ad1531654d00836`；比较用恢复版归档 SHA256：`72824b02cc049b11de5c3c7c5c864aa82783deed3cb18995bef1e0b2836ec5e8`。

<a id="20260922-spin-mcs-rollback"></a>
## 2026-09-22：撤回 spin MCS 频率统计

输入：`恢复bf16b10入口计数`。功能回退验收；当时未重跑性能矩阵，不能把旧恢复成绩记成本次实测。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-mcs-rollback.md)；[完整归档](../../.tmp/spin_mcs_rollback_20260922/spin-mcs-rollback-20260922.tar.gz)、[审核结果](../../.tmp/spin_mcs_rollback_20260922/audit.json)。
归档SHA256：`825d96f5743cf84342f052b59bc38c24ab7415b3bd87254316241d3d216b666d`。

<a id="20260922-spin-mcs1-lock32"></a>
## 2026-09-22：CPU MCS1 / hotlock32 与移除 busy 的合并性能

输入：`35414c2 + 冻结修改，后为383249f`。MCS1/CPU400亿窗口/锁33次、删除busy合并测量；单轮20线程5.011/4.802，两项贡献未拆分。
基础及定向单元3/3、16个错误变体检出，覆盖每次实际MCS采样、单锁32/33边界、spin独立时钟、mutex复用、冷热转换、碰撞/满表及非task丢样。另有18场性能和2场自然加热adaptive功能；未构建SELFTEST或运行生命周期探针，未测8/16线程、nested/early live、真实中断压力、mutex负载、全量单元或PMU。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-mcs1-lock32.md)；[完整归档](../../.tmp/spin-mcs1-lock32-20260922T091214Z/spin-mcs1-lock32-20260922T091214Z.tar.gz)、[三方汇总](../../.tmp/spin-mcs1-lock32-20260922T091214Z/observe/summary.csv)、[排空与冻结输入审计](../../.tmp/spin-mcs1-lock32-20260922T091214Z/post-run-audit.json)、[离线归档审计](../../.tmp/spin-mcs1-lock32-20260922T091214Z/archive-audit.json)。
归档SHA256：`25de7424b6cea8c1b9b873c5076bd97396e304ddc13f3ed257d3a30f8264523f`。

<a id="20260922-spin-mcs1-window4e10"></a>
## 2026-09-22：CPU 窗口400亿、spin MCS阈值1重测

输入：`a6ae430 + 两个采样参数修改`。CPU窗口40亿→400亿、MCS4→1；单轮重测，不能从合并结果单独归因。
基础及采样单元3组、25个错误变体检出，覆盖首次/逐次MCS事件、严格窗口边界、冷热转换和单锁计数保留。当时仍有队列门槛4，少线程零JIT判定属于旧策略；未重跑nested/early、RCUHT或PMU。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-mcs1-window4e10.md)；[完整归档](../../.tmp/spin-mcs1-window4e10-20260922.tar.gz)、[独立核对](../../.tmp/spin-mcs1-window4e10-20260922/audit.json)。
归档SHA256：`1ee6a571e26ced2aaa9cb4810a0210e3554f2640fe342115bdb24eb54c140f1a`。

<a id="20260922-spin-mcs32"></a>
## 2026-09-22：spin CPU 热度按32次MCS入队检查

输入：`508d308 + MCS32修改`。18场单轮；20线程3.937/3.883，相对前基线下降20.8%/18.4%。
基础及定向单元6/6、14个错误变体检出，覆盖CPU32/单锁1025边界、独立时钟、冷却/重热及NUMA开关下物理/虚拟MCS发布恰好计数一次；原生MCS完成40万次操作，另有2场自然加热adaptive功能。normal与SELFTEST均构建通过，但SELFTEST未加载、生命周期探针未运行；未测8/16线程、nested/early live、全量单元、mutex负载或PMU。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-mcs32.md)；[完整归档](../../.tmp/spin-mcs32-20260922T084721Z/spin-mcs32-20260922T084721Z.tar.gz)、[三方汇总](../../.tmp/spin-mcs32-20260922T084721Z/observe/summary.csv)、[排空及冻结输入审计](../../.tmp/spin-mcs32-20260922T084721Z/post-run-audit.json)、[离线归档审计](../../.tmp/spin-mcs32-20260922T084721Z/archive-audit.json)。
归档SHA256：`a0e89aba55b0e39ea54ab76c23737334163a07e284232a38769a243ce4574943`。

<a id="20260922-spin-mcs4-full-benchmark"></a>
## 2026-09-22：MCS4 / 40亿CPU窗口完整三方单轮 bench

输入：`383249f + MCS4/40亿窗口修改`。30场单轮；20线程5.009/4.768，单线程下降；现行参数已不同。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260922-spin-mcs4-full-benchmark.md)；[完整归档](../../.tmp/spinbench-mcs4-20260922T102755Z/spinbench-mcs4-20260922T102755Z.tar.gz)、[三方汇总](../../.tmp/spinbench-mcs4-20260922T102755Z/observe/summary.csv)、[运行后审计](../../.tmp/spinbench-mcs4-20260922T102755Z/post-run-audit.json)、[离线归档核验](../../.tmp/spinbench-mcs4-20260922T102755Z/archive-audit.json)。
归档SHA256：`707daaa0340e0e9cc355caf5aca1dfde1e65e477db1513d41694f123ebef117a`。

<a id="20260923-spin-c-if-full"></a>
## 2026-09-23：C if 冷热分支完整单轮矩阵

输入：`8941012`。84场单轮、两种调用壳和队列门槛；完整原始样本保留。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260923-spin-c-if-full.md)；[完整归档](../../.tmp/spin-c-if-full-20260923.tar.gz)、[独立审计](../../.tmp/spin-c-if-full-20260923/independent-audit.json)、[最终状态](../../.tmp/spin-c-if-full-20260923/final-state.json)。
归档SHA256：`b07306a30387310fbe25b0304ff2caadb3dd1055d452c6eb57a0e7bebc45cbd6`。

<a id="20260923-spin-c-if"></a>
## 2026-09-23：恢复 C if 冷热分支

输入：`95d01f7 + C if修改`。恢复C if、编译器管理寄存器；当时解锁仍有调用端分支，后由generic入口替代。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260923-spin-c-if.md)；[归档](../../.tmp/spin-c-if-20260923.tar.gz)。
归档SHA256：`f107dda2e27c18b1ad8794b0d3ed32e7963813847a35a846e99dedb5959485dc`。

<a id="20260923-spin-heat-only-full"></a>
## 2026-09-23：仅CPU热值分流的完整重测

输入：`db42cf4`。84场单轮；宏中删除两个开关判断，provider当时仍保留队列门槛。
基础及相关单元6组、25个错误变体检出，真实调用宏覆盖冷热/双CPU/活跃寄存器及精确续点，wrapper覆盖COMPLETE、拒绝和FULL续跑。未重跑全量单元、nested/early live、RCUHT、PMU、SELFTEST或真实IRQ/NMI压力。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260923-spin-heat-only-full.md)；[完整归档](../../.tmp/spin-heat-only-full-20260923.tar.gz)、[独立审计](../../.tmp/spin-heat-only-full-20260923/independent-audit.json)、[最终状态](../../.tmp/spin-heat-only-full-20260923/final-state.json)。
归档SHA256：`6205210aa8ee5299a26d8e0075cea9665c81caf10212612e7728168411f40bf4`。

<a id="20260923-spin-three-round"></a>
## 2026-09-23：三轮完整性能矩阵

输入：`运行器03d86d3；spin db42cf4`。252场、84配置×3轮；默认轮次与离散度汇总验证，旧两壳/队列策略不代表当前168场矩阵。
运行器22项回归通过，覆盖默认三轮、轮次反序、显式单轮/功能模式、无效样本排除及吞吐/ns配对。最高150.11%的三轮spread原样保留；该批仅spin，未追加全量单元、nested/early、RCUHT、PMU、SELFTEST或真实IRQ/NMI压力。
[冻结原文](https://github.com/hailongeric/kdlock/blob/39b0e7c3c74d606d31695f9eb9b3f5ef6a7a6e43/bench/tclock_compare/results/20260923-spin-three-round.md)；[完整归档](../../.tmp/spin-three-round-20260923.tar.gz)、[汇总CSV](../../.tmp/spin-three-round-20260923/performance/summary.csv)、[全部原始记录](../../.tmp/spin-three-round-20260923/performance/records.json)、[独立审计](../../.tmp/spin-three-round-20260923/independent-audit.json)、[最终状态](../../.tmp/spin-three-round-20260923/final-state.json)。
归档SHA256：`6c2132fad5a2884a205dc52c1f694b5360e12397c4ea24512ce76a11c0ee1730`。
