# py-viewer - 炎核看图工具

带有 AI 聊天助手功能的炎核 CAD 看图工具。

## 功能特点

- **3D 模型查看**: 支持 STP、STEP、IGS 格式模型导入
- **AI 聊天助手**: 集成 DeerFlow AI 助手，支持自然语言交互
- **脚本自动执行**: AI 可以自动执行 Python 脚本操作模型
- **草图脚本**: 支持手动运行自定义草图脚本

## 依赖安装

```bash
# 创建并激活虚拟环境
uv venv --python 3.12 .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 安装依赖
uv sync
```

## 配置

### 1. 炎核开发引擎路径

修改 `main.py` 中的 `DEFAULT_DLL_PATH`：

```python
DEFAULT_DLL_PATH = 'C:/Users/epro/Downloads/YHCAD/YHCAD_Setup_2026.1.0.57_Beta_Windows_x86-64'
```

### 2. DeerFlow AI 服务配置

通过环境变量配置 AI 服务地址：

```bash
set DEERFLOW_BASE_URL=http://172.16.34.129:8301
```

或者在代码中修改 `DEERFLOW_BASE_URL` 常量。

## 运行

```bash
python main.py
```

## 使用说明

1. **创建文档**: 点击顶部工具栏"创建文档"按钮
2. **导入模型**: 点击"导入模型"按钮选择 STP/STEP/IGS 文件
3. **AI 聊天**: 在右侧 AI 助手面板输入消息，AI 可以：
   - 回答关于模型的问题
   - 自动执行脚本操作模型
   - 执行复杂的建模任务
4. **运行脚本**: 点击"运行脚本"按钮手动执行草图脚本

## AI 功能

AI 助手通过 DeerFlow API 提供以下能力：

- **自然语言交互**: 用自然语言描述你想做的操作
- **自动脚本执行**: AI 会自动生成并执行 Python 脚本
- **上下文理解**: AI 记住对话历史，支持多轮对话

示例对话：
- "创建一个立方体"
- "导入一个球体并移动到指定位置"
- "显示模型的尺寸信息"
