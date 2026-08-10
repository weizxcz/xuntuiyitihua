# scripts/ — 训练 / 预测 / 评估 / 标注

NCTI 版 FeatureFox 完整工作流脚本。运行需要 yhcad_py312 环境 + NCTI SDK。

## 预测

### `predict.py` — 预测入口
```bash
python -m featurefox.scripts.predict <step文件> [阈值]
```
核心参数：
- `DEFAULT_THRESHOLD = 0.10`（第一级边剪枝）
- `INST_THRESHOLD = 0.80`（第二级实例分类器）
- `MIN_INSTANCE_FACES = 2`（盲孔最少面数）
- `MIN_PLANE_RATIO = 0.0`（盲孔不适用平面占比过滤）

## 训练

### `train.py` — 边分类器训练（全量）
```bash
python -m featurefox.scripts.train 2000    # 前 2000 件
python -m featurefox.scripts.train 0       # 全量 62495 件
```
超参：200 棵树，max_depth=6，learning_rate=0.1，等渗校准。
输出：`models/edge_clf.json` + `models/calibrator.pkl`

### `train_seg12only.py` — seg12-only 边分类器
```bash
python -m featurefox.scripts.train_seg12only
```
仅用含盲孔 seg=12 标注的 STEP 文件训练，测试集固定为 `test_names.json`（12486 件）。
输出：`models/edge_clf_seg12only.json` + `models/calibrator_seg12only.pkl`

### `train_instance.py` — 实例分类器训练（全量）
```bash
python -m featurefox.scripts.train_instance 0
```
分 chunk 子进程隔离收集训练数据，防止 NCTI 累积 segfault。
输出：`models/inst_clf.json` + `models/inst_calibrator.pkl`

### `train_instance_seg12only.py` — seg12-only 实例分类器
```bash
python -m featurefox.scripts.train_instance_seg12only
```
输出：`models/inst_clf_seg12only.json` + `models/inst_calibrator_seg12only.pkl`

## 评估

### `evaluate.py` — 评估脚本
```bash
python -m featurefox.scripts.evaluate 50            # 前 50 文件
python -m featurefox.scripts.evaluate 0             # 全量
python -m featurefox.scripts.evaluate 0 0.10 50000  # 指定阈值 + offset
```

### `run_evaluate.py` — Linux 单进程评估
```bash
python3 featurefox/scripts/run_evaluate.py [max_files] [threshold] [offset]
```

### `run_evaluate_chunked.py` — 子进程隔离评估
```bash
python3 featurefox/scripts/run_evaluate_chunked.py [max_files] [threshold] [offset]
```
每 30 件一个子进程，崩溃不影响其余 chunk。

### `sweep_thresholds.py` — 阈值扫描
```bash
python -m featurefox.scripts.sweep_thresholds [n_holdout] [offset]
```
9 点扫描 (0.05~0.50)，产出 Mode A（纯第一级）和 Mode B（全流水线）P/R/F1 曲线。

### `threshold_sweep.py` — STEP-parser 版阈值扫描
依赖原版 StepParser（`utils/through_step/featurefox/`），用于对比分析。

## 标注

### `annotate_blind_hole_ncti.py` — 盲孔批量标注
```bash
python3 featurefox/scripts/annotate_blind_hole_ncti.py
```
配置在脚本顶部的 `# 配置区` 中修改。
输出：JSON 标签 + STEP 文件（仅含盲孔的件）。

### `gen_test_split.py` — 生成测试集划分
生成 `test_names.json`，用于固定测试集。

## 模型路径

所有模型统一保存在 `featurefox/models/` 目录：
- `edge_clf.json` / `calibrator.pkl`
- `edge_clf_seg12only.json` / `calibrator_seg12only.pkl`
- `inst_clf.json` / `inst_calibrator.pkl`
- `inst_clf_seg12only.json` / `inst_calibrator_seg12only.pkl`
