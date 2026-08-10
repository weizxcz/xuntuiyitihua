# Split Assembly and Detect Blind Hole

## 项目功能

这个目录用于独立打包上传到 Linux 服务器运行盲孔识别流程。

核心流程：

1. 读取服务器 STEP/STP 源文件目录。
2. 使用 NCTI 在 pipeline 内部判断并拆分装配体。
3. 对原始或拆分后的 target STP 调用 v15_23 盲孔识别。
4. 检测到盲孔时生成训练 JSON，并通过后端接口更新数据库。
5. 训练 JSON 顶层统一为数组格式：`[{...}]`。

## 关键目录

```text
Split_Assembly_and_Detect_blind_hole/
├── README.md
├── optimized_pipeline/
│   └── fast_blindhole_pipeline.py
├── blind_hole/
│   ├── __init__.py
│   ├── pipeline_core.py
│   └── detect_blind_holes_and_export_stp_v15_23.py
├── countersunk_hole/
│   ├── __init__.py
│   └── detect_countersunk_holes_and_export_stp_v15.py
├── function/
│   ├── __init__.py
│   └── on_find_blind_hole_stp.py
└── config/
    ├── __init__.py
    ├── config_load.py
    ├── ncti_config.server.json
    └── ncti_config.example.json
```

## 核心脚本

### `optimized_pipeline/fast_blindhole_pipeline.py`

正式运行入口。它会调用 `blind_hole/pipeline_core.py` 中的 NCTI 拆分、盲孔识别、STEP face 到 NCTI cell_id 映射、JSON 保存和数据库更新逻辑。

### `blind_hole/pipeline_core.py`

盲孔 pipeline 的公共核心模块，包含：

- 后端 API 客户端。
- NCTI 初始化和装配体拆分逻辑。
- v15_23 盲孔识别入口。
- STEP face 到 NCTI cell_id 的映射。
- 训练 JSON 构造和保存。

### `blind_hole/detect_blind_holes_and_export_stp_v15_23.py`

当前使用的盲孔识别脚本，盲孔类别 id 为 `12`。

### `countersunk_hole/detect_countersunk_holes_and_export_stp_v15.py`

随包携带的沉头孔/沉孔识别脚本。当前目录的正式批处理入口仍是盲孔 pipeline，沉头孔脚本用于后续沉头孔流程扩展或单独调用。

## JSON 格式

生成的训练 JSON 顶层是数组：

```json
[
  {
    "seg": {},
    "inst": [],
    "bottom": {}
  }
]
```

内部字段含义保持原逻辑不变，只是最外层不再保存为 `{...}`。

## 服务器运行示例

```bash
cd /home/tianyibing/Split_Assembly_and_Detect_blind_hole
conda activate py311

export NCTI_CONFIG=$PWD/config/ncti_config.server.json
export NCTI_SDK=/mnt/data/workspace/wuhongqing/tools/YanHe_GMDE_SDK_2026.1.1.2_Beta_Linux_x86-64
unset PYTHONPATH
export LD_LIBRARY_PATH=$NCTI_SDK

python optimized_pipeline/fast_blindhole_pipeline.py \
  /mnt/data/geometry_data/steps/step_files \
  --api-base-url http://172.16.36.154:5060/api \
  --user "田一冰_v15_v23_2" \
  --mark-no-holes \
  --list-page-size 100
```

## 注意

- 不需要单独运行拆分脚本，`fast_blindhole_pipeline.py` 内部已经包含 NCTI 拆分逻辑。
- 旧版 `detect_blind_holes_and_export_stp_v15_15.py` 已移除。
- 旧 JSON 转换脚本不再包含在此打包目录中。
