# INSTALL.md — FeatureFox 一键跑通指南

> 目标：别人 `git clone` 后，**5 分钟**内跑通训练 + 推理 + 评估。
> 涉及 3 个环境变量 + 1 个 JSON 配置文件 + 1 份数据目录。

---

## 0. 5 分钟速览

```bash
git clone <your-repo-url> GeoFeatureRecMethod
cd GeoFeatureRecMethod/featurefox
pip install -r requirement.txt

# 改 1 个 JSON（SDK 路径）
vim config/ncti_config.json   # 把 dllPath 改成你自己的 SDK 路径

# 准备数据（指向你自己已有的 STEP + labels）
export FEATUREFOX_STEPS_DIR=/your/data/steps
export FEATUREFOX_LABELS_DIR=/your/data/labels

# 跑训练
python -m featurefox.scripts.train 0            # 第一级
python -m featurefox.scripts.train_instance 0   # 第二级

# 跑推理
python -m featurefox.scripts.predict /your/data/steps/some_part.step
```

---

## 1. Python 环境

| 项 | 要求 |
|---|---|
| **Python** | 3.8+（推荐 3.10/3.11，与 NCTI yhcad_py312 配套） |
| **OS** | Linux x86-64（推荐，NCTI SDK Linux 版）；Windows 仅供推理（依赖 YHCADSmartCleaner） |
| **pip 包** | `pip install -r featurefox/requirement.txt` |

`requirement.txt` 内容：
```
xgboost       ≥1.7
numpy         ≥1.21
networkx      ≥2.6
scikit-learn  ≥1.0
```

---

## 2. NCTI SDK 配置（**唯一**必须改的 JSON）

文件：`featurefox/config/ncti_config.json`

把 `dllPath` 改成你本地 NCTI SDK 的安装路径：

```json
{
    "dllPath": "/your/path/to/YanHe_GMDE_SDK_2026.x.x_Linux_x86-64_Community",
    "addKernelPath": [],
    "loadDLL": [
        "libncti_command.so",
        "libncti_occ_plugin.so",
        "libncti_doc_occ.so"
    ]
}
```

> **SDK 没装？** 找炎核同事要 `/softwares/YanHe_GMDE_SDK_*_Linux_x86-64_Community` 整个目录。
> SDK 启动时会自动 loadDLL 列表里的 3 个 .so。

---

## 3. 数据目录（**两个环境变量**）

FeatureFox 不自带数据，需要你自己有 STEP 文件 + 标签 JSON。

### 数据格式要求

| 目录 | 内容 | 文件名要求 |
|---|---|---|
| `STEPS_DIR` | `*.step`（或 `.stp`） | 与 `LABELS_DIR` 的 JSON **同名**（仅后缀不同） |
| `LABELS_DIR` | `*.json`（标签） | 见下方格式 |

### 标签 JSON 格式（`inner.seg` dict，`inner.inst` 邻接矩阵）

```json
{
    "0": {
        "seg": {"0": 0, "1": 0, "2": 12, "3": 12, "4": 9, ...},
        "inst": [[0, 1, 0, 0, 0, ...], ...]
    }
}
```

- `seg[cell_id] == 9` → 通槽
- `seg[cell_id] == 12` → 盲孔
- `inst[i][j] == 1` → cell i 和 cell j 同属一个特征实例

### 跑训练前必须设这两个变量

```bash
# 方式 A：当前 shell 临时设
export FEATUREFOX_STEPS_DIR=/your/data/steps
export FEATUREFOX_LABELS_DIR=/your/data/labels

# 方式 B：写到 ~/.bashrc 永久生效
echo 'export FEATUREFOX_STEPS_DIR=/your/data/steps' >> ~/.bashrc
echo 'export FEATUREFOX_LABELS_DIR=/your/data/labels' >> ~/.bashrc
```

### 兜底（不设环境变量）

代码兜底到 `~/featurefox_data/steps/` 和 `~/featurefox_data/labels/`，把数据放那里也行（不推荐，污染主目录）。

---

## 4. 模型文件（**已经随仓库入库**）

`featurefox/models/` 下应有 4 个核心文件：

| 文件 | 用途 |
|---|---|
| `edge_clf.json` | 第一级边分类器（XGBoost 200棵树，深度 6） |
| `calibrator.pkl` | 第一级等温校准器 |
| `inst_clf.json` | 第二级实例分类器（XGBoost 200棵树，深度 4） |
| `inst_calibrator.pkl` | 第二级等温校准器 |

如果想用自定义模型：

```bash
export FEATUREFOX_MODELS_DIR=/your/custom/models
```

---

## 5. 跑起来！

所有命令都在 `featurefox/` 目录下执行。

### 训练（需要 STEP + labels）

```bash
# 全量（62495 件）—— 耗时 5h+，建议先小批量试
python -m featurefox.scripts.train 100         # 100 件冒烟
python -m featurefox.scripts.train 0            # 0 = 全量

# 第二级实例分类器
python -m featurefox.scripts.train_instance 0
```

### 推理（不需要 labels）

```bash
# 单文件
python -m featurefox.scripts.predict /your/data/steps/part.step

# 整目录批量
python -m featurefox.scripts.run_evaluate /your/data/steps/
```

### 评估（需要 labels）

```bash
# 全量评估
python -m featurefox.scripts.evaluate 0

# 子进程隔离版（生产用）
python -m featurefox.scripts.run_evaluate_chunked
```

### 调试工具

```bash
# 单文件分阶段 dump
python -m featurefox.debug._debug_one /your/data/steps/part.step

# 单文件分阶段耗时实测
python -m featurefox.debug._bench_one /your/data/steps/part.step

# 阈值扫描
python -m featurefox.scripts.threshold_sweep 1000 14000

# holdout 漏检分桶统计
python -m featurefox.debug._stat_holdout 0 14000
```

---

## 6. 验证环境是否正确

```bash
# 检查 Python 依赖
python -c "import xgboost, numpy, networkx, sklearn; print('OK')"

# 检查 FeatureFox 路径解析
python -c "from featurefox.lib._env import get_steps_dir, get_labels_dir, get_models_dir; print(get_steps_dir(), get_labels_dir(), get_models_dir())"

# 检查 NCTI SDK 加载
python -c "from featurefox.lib.ncti_backend import load_part; print('NCTI backend importable')"

# 检查模型文件
ls -lh featurefox/models/edge_clf.json featurefox/models/inst_clf.json
```

---

## 7. 常见问题

| 问题 | 解法 |
|---|---|
| `FileNotFoundError: /data/data2/steps` | 没设 `FEATUREFOX_STEPS_DIR` 环境变量 |
| `dlopen: libncti_*.so: cannot open` | SDK 路径错或缺 LD_LIBRARY_PATH |
| `XGBoostError: edge_clf.json not found` | 模型文件没下载 / `FEATUREFOX_MODELS_DIR` 错 |
| `ModuleNotFoundError: detect_blind_holes_*` | debug 脚本需要 YHCADSmartCleaner 兄弟目录；设 `NCTI_PROJECT_ROOT=/path/to/YHCADSmartCleaner` |
| 训练时 segfault | NCTI 批量资源冲突，用 subprocess 隔离版（`run_evaluate_chunked`） |

---

## 8. 完全干净的最小环境

```bash
# 干净的 conda env
conda create -n featurefox python=3.10 -y
conda activate featurefox

# 装包
cd GeoFeatureRecMethod/featurefox
pip install -r requirement.txt

# 配 SDK（改 JSON + 加 LD 路径）
export LD_LIBRARY_PATH=/your/SDK/path/lib:$LD_LIBRARY_PATH
vim config/ncti_config.json   # 改 dllPath

# 配数据
export FEATUREFOX_STEPS_DIR=/your/data/steps
export FEATUREFOX_LABELS_DIR=/your/data/labels

# 跑
python -m featurefox.scripts.predict /your/data/steps/your_part.step
```

跑通上面这一行就算成功。
