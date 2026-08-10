# Graph-CAD 本代码说明

本目录为 Graph-CAD 项目的**代码部分**，原始仓库来自 `https://github.com/EESJGong/Graph-CAD.git`，
后迁移至 `https://github.com/weizxcz/xuntuiyitihua.git`。

## 项目简介

Graph-CAD 是一条「graph → mcp → bpy」三段式 CAD 自动生成流水线：

1. **graph 阶段**：将产品自然语言描述（instruction）转换为
   `MATERIAL LIBRARY` + 知识图谱（节点 / 边文本）。
2. **mcp 阶段**：将知识图谱转换为自然语言「MCP 建造脚本」。
3. **bpy 阶段**：将 MCP 脚本转换为可执行的 Blender Python 脚本，
   最终由 Blender 无头渲染出 3D 模型。

三段共用同一个基座模型，各自微调一个 LoRA 适配器（stage1 / stage2 / stage3）。

## 目录结构（代码资产）

```
Graph-CAD/
├── evaluate_and_report.py   # 端到端评测脚本（已接入远程推理端点）
├── infer_api.py             # 三段推理 API 入口
├── render_auto.py           # 批量渲染 output/demo 下的 bpy 脚本
├── utils/
│   └── blender_runner.py    # 调用 Blender 无头渲染 + LLM 输出清洗
├── prompt_sft/              # 三个阶段的 system prompt 模板（训练基底）
│   ├── graph_prompt.txt
│   ├── mcp_prompt.txt
│   └── bpy_prompt.txt
├── CADBench.jsonl           # 评测 / 指令数据集（仅 instruction，无标准答案）
└── .gitignore
```

## 已被 .gitignore 排除（不提交）

- `output/`：推理 / 渲染产物（含 195 个产品的 graph/mcp/bpy 三段 txt）。
- `checkpoints/`：训练产出的 LoRA 权重（当前为空）。
- `qwen3/`：本地模型相关目录（当前为空）。
- `config/system_config.json`：含本机绝对路径的本地配置。
- `__pycache__/`、`.idea/` 等缓存与编辑器文件。

## 远程端点配置（已改造）

`evaluate_and_report.py` 与 `infer_api.py` 已支持通过命令行参数指定远程端点：

- `--api-base` 默认 `http://172.16.55.7:9026/v1`
- `--api-key` 默认 `empty`
- `--model` 默认 `Qwen3.6-35B-A3B`
- Qwen3 已关闭 thinking：`extra_body={"chat_template_kwargs": {"enable_thinking": False}}`

> 注：当前三段共用同一个 `--model`。后续在 Mac（M1 Pro）上重新训练
> 3 个轻量 LoRA（推荐 Qwen3-4B-Instruct）后，需将 `infer_api.py` 改为
> per-stage model 参数（stage1 / stage2 / stage3 各配一个 lora_id）。

## 运行依赖

- Python 3.9+（conda 环境 `graphcad` / `yhcad`）
- Blender 4.x（无头渲染）
- openai（用于调用远程推理端点）
- 见各文件 import 头获取完整依赖
