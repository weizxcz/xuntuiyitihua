# CAD Script MCP Server

一个支持 **stdio** 和 **HTTP** 双协议的 MCP 服务器，用于执行 NCTI/YH Python 脚本，实现 3D 模型和草图的程序化创建与修改。

---

## 📋 功能特性

- **双协议支持**: 同时支持 stdio 和 HTTP/SSE 协议
- **脚本执行**: 执行 NCTI/YH Python 脚本进行 CAD 操作
- **模型管理**: 支持创建新文档或修改现有模型
- **文件服务**: 提供模型文件的 HTTP 访问端点
- **子进程执行**: 使用子进程执行脚本，防止主进程崩溃

---

## 🏗️ 项目结构

```
cad_script_mcp/
├── main.py              # MCP 服务器主程序（stdio + HTTP）
├── run_sketch_script.py # 脚本执行核心逻辑
├── run_scripts.py       # 脚本执行辅助模块
├── webcadscript.py      # Web CAD 脚本工具
├── params.py            # 参数定义（Pydantic 模型）
├── config.py            # 配置文件（SDK 路径、端口等）
├── storage/             # 模型文件存储目录
├── .venv/               # 虚拟环境
└── pyproject.toml       # 项目依赖配置
```

---

## 📦 安装

### 1. 创建虚拟环境

```bash
# 使用 uv（推荐）
uv venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# 或使用 pip
python -m venv .venv
```

### 2. 安装依赖

```bash
# 使用 uv（推荐）
uv pip install -e .

# 或使用 pip
pip install -e .
```

---

## 🚀 启动方式

### HTTP 模式

```bash
# 使用入口点
cad_script_mcp_http

# 或直接运行
python main.py --http

# 或使用 uv
uv run main.py --http
```

### stdio 模式（默认）

```bash
# 直接运行
python main.py

# 或使用 uv
uv run main.py
```

---

## ⚙️ 配置

编辑 `config.py` 文件：

```python
# config.py

# NCTI SDK DLL 路径配置
# 必须指向包含以下文件的目录：
#   - ncti_command.dll
#   - ncti_occ_plugin.dll
#   - ncti_render_vulkan.dll
#   - OCC/ (子目录)
DLL_PATH = "C:/Program Files/NCTI/sdk"

# HTTP 服务器配置
HTTP_PORT = 8310
HTTP_HOST = "0.0.0.0"

# 存储目录配置
STORAGE_DIR = "./storage"

# 临时目录配置
TEMP_DIR = "./storage/temp"
```

### 环境变量覆盖

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SDK_DLL_PATH` | NCTI SDK DLL 路径 | `config.py` 中的 `DLL_PATH` |
| `CAD_HTTP_SERVER_PORT` | HTTP 服务器端口 | `8310` |
| `CAD_HTTP_SERVER_HOST` | HTTP 服务器绑定地址 | `0.0.0.0` |

---

## 🔌 服务端点（HTTP 模式）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/mcp` | POST | MCP 协议端点 |
| `/files/{path}` | GET | 文件下载 |
| `/health` | GET | 健康检查 |

### 健康检查

```bash
curl http://localhost:8310/health
```

响应：
```json
{"status": "ok", "service": "cad-script-mcp"}
```

### MCP 端点

POST 请求到 `/mcp`，遵循 JSON-RPC 2.0 协议：

```bash
curl -X POST http://localhost:8310/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
  }'
```

---

## 🛠️ 可用工具

### `run_scripts` - 执行 CAD 脚本

执行一个或多个 CAD 脚本。

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `scripts` | array | 是 | 脚本列表 |
| `model_path` | string | 是 | 模型文件路径（格式：`{directory}/{filename}.yha`） |

**脚本对象结构**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `script_type` | string | 脚本类型标识 |
| `script_content` | string | Python 脚本内容 |
| `should_execute` | boolean | 是否执行此脚本 |

**示例**:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "run_scripts",
    "arguments": {
      "scripts": [
        {
          "script_type": "create_box",
          "script_content": "part = NCTI.CreatePart()\nbox = NCTI.Primitive.Box(10, 10, 10)",
          "should_execute": true
        }
      ],
      "model_path": "projects/test_model.yha"
    }
  }
}
```

### `get_file_url` - 获取文件 URL

获取已保存模型的 HTTP 访问 URL。

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 相对于 storage 目录的文件路径 |

**示例**:
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_file_url",
    "arguments": {
      "file_path": "projects/test_model.yha"
    }
  }
}
```

---

## 🦌 DeerFlow 配置

在 `extensions_config.json` 中添加：

```json
{
  "mcpServers": {
    "cad_script": {
      "enabled": true,
      "type": "http",
      "url": "http://localhost:8310/mcp",
      "description": "CAD 脚本执行 MCP 服务器"
    }
  }
}
```

---

## 📁 存储目录

服务器在 `storage/` 目录下存储和管理模型文件：

```
storage/
├── projects/          # 用户项目目录
└── temp/              # 临时文件目录
```

---

## 🐛 调试

### 日志级别

服务器默认启用 DEBUG 级别日志，输出格式：

```
2026-01-15 10:30:45 [DEBUG] main - [CONN] 请求 #1 处理
2026-01-15 10:30:46 [INFO] main - handle_run_scripts 开始处理
```

### 常见问题

**Q: SDK DLL 加载失败？**

确保 `DLL_PATH` 指向正确的 NCTI SDK 安装目录，并且所有依赖 DLL 都存在。

**Q: 脚本执行超时？**

脚本在子进程中执行，默认超时时间为 60 秒。可在 `run_sketch_script.py` 中修改 `DEFAULT_SCRIPT_TIMEOUT`。

**Q: 文件无法访问？**

检查 `STORAGE_DIR` 配置，确保目录存在且有读写权限。

---

## 📄 许可证

MIT License
