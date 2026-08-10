# 脚本生成到模型展示流程说明

本文档简要说明 DeerFlow 项目如何从 AI 生成脚本，到脚本执行，再到 3D 模型展示的工作流程。

---

## 核心流程

```
用户输入 → AI 生成脚本 → exec_script 工具返回 → 客户端拦截 → 脚本执行 → 生成模型文件 → present_model → 前端展示
```

---

## 三种客户端执行路径

### 路径 A: Frontend (Next.js)

1. **前端监听工具调用**：`useThreadStream` Hook 的 `onToolEnd` 回调监听 `exec_script` 事件
2. **获取脚本内容**：从 `event.data` 中提取 `script`, `description`, `need_yh`
3. **调用 MCP 执行**：通过 MCP `run_scripts` 工具执行脚本
4. **模型展示**：脚本执行后返回模型 URL，前端调用 `present_model` 工具，在聊天界面显示 3D 模型查看器

**关键文件**:
- `frontend/src/core/threads/hooks.ts` - 流式响应处理
- `frontend/src/components/workspace/` - 模型渲染组件

---

### 路径 B: Qt 嵌入客户端 (qt-embed.html)

1. **SDK 拦截流式事件**：`processStream` 解析 `messages-last` 模式中的 `exec_script` tool call
2. **发送脚本请求**：通过 CEF/WebView2 发送 `SCRIPT_REQUEST` 消息给 Qt 原生应用
3. **Qt 执行脚本**：原生应用调用 NCTI SDK 执行脚本
4. **返回结果**：Qt 发送 `SCRIPT_RESULT` 消息，前端将结果发送给 AI 继续处理

**关键文件**:
- `packages/js-sdk/qt-embed.html` - Qt 嵌入客户端 SDK

---

### 路径 C: Python 客户端 (py-viewer)

1. **HTTP 接收脚本**：Flask 服务器监听 `/execute_script` 端点
2. **wxPython GUI 执行**：`MainWindow.run_sketch_script_http` 在 NCTI 环境中执行脚本
3. **生成模型文件**：调用 NCTI SDK 生成 `.yha` 模型文件
4. **模型展示**：右侧 WebView 显示 3D 模型查看器

**关键文件**:
- `packages/py-viewer/main.py` - 主入口
- `packages/py-viewer/ui/main_window.py` - 脚本执行入口
- `packages/py-viewer/services/http_server.py` - HTTP 服务

---

## 核心工具

| 工具 | 位置 | 作用 |
|------|------|------|
| `exec_script` | `backend/packages/harness/deerflow/tools/builtins/exec_script_tool.py` | AI 生成脚本后返回给前端 |
| `present_model` | `backend/packages/harness/deerflow/tools/builtins/present_model_tool.py` | 将模型 URL 添加到 artifacts 用于前端展示 |
| `run_scripts` | `mcps/cad_script_mcp/main.py` | MCP 服务器执行脚本的工具 |

---

## 数据流示例

```
用户："创建一个边长为 10 的立方体"

1. AI 生成脚本并调用 exec_script:
   {
     "script": "import NCTI\npart = NCTI.CreatePart('Box')\nbox = NCTI.Primitive.Box(10, 10, 10)",
     "description": "创建一个边长为 10 的立方体",
     "need_yh": false
   }

2. 客户端拦截并执行脚本 → 调用 NCTI SDK

3. MCP 返回模型文件 URL:
   http://localhost:8310/files/projects/box-123.yha

4. 调用 present_model 工具，前端在聊天界面渲染 3D 模型查看器
```

---

## 配置文件

- `backend/config.yaml` - 后端工具和模型配置
- `extensions_config.json` - MCP 服务器配置
- `packages/py-viewer/config.py` - Python 客户端配置

---

## 关键文件清单

| 文件 | 说明 |
|------|------|
| `backend/.../exec_script_tool.py` | exec_script 工具定义 |
| `backend/.../present_model_tool.py` | present_model 工具定义 |
| `frontend/src/core/threads/hooks.ts` | 前端线程流处理 |
| `packages/js-sdk/qt-embed.html` | Qt 嵌入客户端 |
| `packages/py-viewer/` | Python 客户端 |
| `mcps/cad_script_mcp/main.py` | MCP 服务器 |
