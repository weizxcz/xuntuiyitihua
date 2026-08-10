# debug/ — 诊断与调试工具

单文件诊断、holdout 漏检分析、阈值策略扫描工具。**注意：部分工具使用 STEP-parser 版本**（依赖 `utils/through_step/featurefox/`），与 NCTI 版本的 `lib/` 不兼容。

## 文件

### NCTI 版

#### `_smoke.py` — 单件冒烟测试
```bash
python -m featurefox.debug._smoke [step文件名]
```
验证 NctiPart 建图 + 特征符号 + 面数断言。无需训练模型。
检查项：面数一致性、AAG 构建、凸凹性分布、seg9 内部边符号、首条边 30 维特征。

#### `_diag.py` — 崩件定位器
```bash
python -m featurefox.debug._diag
```
逐件处理 40-80 号文件，崩件 segfault 杀进程时最后打印的件即为问题件。

### STEP-parser 版（通槽 seg=9）

以下工具使用原始 STEP 文本解析版 FeatureFox（`utils/through_step/featurefox/`），依赖 `StepParser` + `build_face_graph(parser)`：

#### `_debug_one.py` — 单文件两级管线 dump
```bash
python -m featurefox.debug._debug_one <step路径>
```
完整输出：标签解析 → STEP 解析 → 边特征 + 概率直方图 → 剪枝连通分量 → 后处理 → 实例分类器概率 + 逐特征值。

#### `_stat_holdout.py` — holdout 漏检阶段分析
```bash
python -m featurefox.debug._stat_holdout [n_files] [offset]
```
按漏检阶段分桶：
- `L1_MISS`：第一级剪枝零召回
- `L1_PART`：部分召回
- `L2_KILL`：第一级有但第二级杀
- `L2_KILL_FULL`：第一级完整恢复但第二级杀

#### `_sweep_inst.py` — 第二级策略扫描
```bash
python -m featurefox.debug._sweep_inst [n] [offset]
```
对比 6 种策略的面级 P/R/F1：
- A：单级（无第二级）
- B~C：不同阈值的第二级
- D~F：第二级 + 几何豁免规则

#### `_bench_one.py` — 单文件耗时基准
```bash
python -m featurefox.debug._bench_one
```
分阶段计时：StepParser.parse → build_face_graph → 模型加载 → predict 全流程。
