# models/ — 训练好的模型文件

XGBoost 分类器 + 等渗校准器。

## 边分类器（第一级）

| 文件 | 大小 | 说明 |
|------|------|------|
| `edge_clf.json` | ~990 KB | 全量样本训练，200 棵树 × max_depth=6 |
| `calibrator.pkl` | ~1 KB | 等渗回归校准器（概率映射） |
| `edge_clf_seg12only.json` | ~902 KB | 仅 seg=12 文件训练 |
| `calibrator_seg12only.pkl` | ~818 B | seg12-only 校准器 |

## 实例分类器（第二级）

| 文件 | 大小 | 说明 |
|------|------|------|
| `inst_clf.json` | ~358 KB | 真盲孔 vs 硬负样本分类 |
| `inst_calibrator.pkl` | ~720 B | 等渗回归校准器 |
| `inst_clf_seg12only.json` | ~355 KB | seg12-only 版本 |
| `inst_calibrator_seg12only.pkl` | ~704 B | seg12-only 校准器 |

## 评估报告

| 文件 | 说明 |
|------|------|
| `featurefox_blindhole_eval_report.json` | 全量评估结果 |
| `featurefox_blindhole_eval_report_test.json` | 测试集评估结果 |
| `test_names.json` | 固定测试集文件名列表（12486 件） |

## 模型格式

- `.json` — XGBoost Booster 序列化（可读文本格式，200 棵决策树）
- `.pkl` — Python pickle，`sklearn.isotonic.IsotonicRegression` 校准器

## 加载方式

```python
import xgboost as xgb, pickle

booster = xgb.Booster()
booster.load_model("models/edge_clf.json")

with open("models/calibrator.pkl", "rb") as f:
    calibrator = pickle.load(f)
```

或通过 `featurefox.scripts.predict.load_models()` / `load_instance_models()` 统一加载。
