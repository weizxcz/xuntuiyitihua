# exec_script 工具定义

## 工具定义 JSON Schema

```json
{
  "name": "exec_script",
  "description": "Execute a script for CAD modeling operations.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "script": {
        "type": "string",
        "description": "The Python script content to execute."
      },
      "description": {
        "type": "string",
        "description": "Description of what the script does."
      },
      "language": {
        "type": "string",
        "description": "The language of the script (e.g., 'python').",
        "default": "python"
      }
    },
    "required": ["script"]
  }
}
```

## 使用示例

### 后端配置 (LangGraph)

在 DeerFlow 后端，`exec_script` 工具已经作为内置工具加载：

```python
# backend/packages/harness/deerflow/tools/builtins/exec_script_tool.py
from langchain_core.tools import tool

@tool
def exec_script(script: str, description: str = "", language: str = "python") -> dict:
    """Execute a script for CAD modeling operations.
    
    此工具将脚本返回给调用方，由调用方自行执行。
    
    Args:
        script: The Python script content to execute.
        description: Description of what the script does.
        language: The language of the script (default: python).
    
    Returns:
        A dictionary with the script content and metadata.
    """
    return {
        "success": True,
        "script": script,
        "description": description,
        "language": language,
        "message": "Script returned to caller for execution."
    }
```

该工具已在 `backend/packages/harness/deerflow/tools/tools.py` 中注册到 `BUILTIN_TOOLS` 列表。

### MCP 服务器配置

MCP 服务器 `cad_script_mcp` 也支持 `exec_script` 工具：

```python
# mcps/cad_script_mcp/main.py
{
    "name": "exec_script",
    "description": "Execute a script for CAD modeling operations. 此工具将脚本返回给调用方，由调用方自行执行。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "The Python script content to execute."
            },
            "description": {
                "type": "string",
                "description": "Description of what the script does."
            },
            "language": {
                "type": "string",
                "description": "The language of the script (e.g., 'python').",
                "default": "python"
            }
        },
        "required": ["script"]
    }
}
```

### SDK 前端处理

```typescript
// 方式 1: 按工具名称注册处理器
await client.threads.streamWithHandlers(threadId, {
  messages: [{ type: "human", content: "Create a box" }],
  handlers: {
    exec_script: (event) => {
      const { script, description, language } = event.args;
      
      console.log(`收到脚本执行请求：${description}`);
      console.log(`脚本内容:\n${script}`);
      
      // 选项 1: 显示脚本给用户确认
      // showScriptToUser(script, description);
      
      // 选项 2: 通过 WebSocket 发送到后端执行
      // websocket.send(JSON.stringify({ type: 'exec_script', script }));
      
      // 选项 3: 通过 MCP 的 run_scripts 工具执行
      // const mcpResult = await mcpClient.callTool({
      //   name: 'run_scripts',
      //   arguments: {
      //     scripts: [{ script_content: script, should_execute: true }],
      //     model_path: "thread-abc123/model.yha"
      //   }
      // });
      // await presentModel(mcpResult.file_url);
      
      // 注意：事件处理器不需要返回结果
      // 如果需要反馈执行结果，由用户自行发送消息给 Agent
    }
  }
});

// 方式 2: 使用通配符处理器处理所有工具调用
await client.threads.streamWithHandlers(threadId, {
  messages: [{ type: "human", content: "Create a box" }],
  handlers: {
    "*": (event) => {
      console.log(`收到工具调用：${event.name}`);
      console.log(`参数：`, event.args);
    }
  }
});
```

### Frontend 完整示例

```typescript
import { DeerFlowClient } from "@deer-flow/js-sdk";

const client = new DeerFlowClient({
  baseUrl: "http://localhost:8001",
  userId: "user-123"
});

const thread = await client.threads.create();

// 处理 exec_script 事件
await client.threads.streamWithHandlers(threadId, {
  messages: [{ type: "human", content: "帮我创建一个立方体" }],
  handlers: {
    exec_script: async (event) => {
      const { script, description } = event.args;
      
      console.log("Agent 请求执行脚本:", description);
      console.log("脚本内容:\n", script);
      
      // 通过 MCP 执行脚本
      const mcpResponse = await fetch("http://localhost:8310/mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "tools/call",
          params: {
            name: "run_scripts",
            arguments: {
              scripts: [{
                script_type: "create_box",
                script_content: script,
                should_execute: true
              }],
              model_path: `${threadId}/model.yha`,
              need_yh: false
            }
          }
        })
      });
      
      const result = await mcpResponse.json();
      const fileUrl = result.result.content[0].text.file_url;
      
      // 展示模型
      await presentModel(fileUrl);
    }
  }
});
```

## 如何区分聊天来源

大模型本身无法自动区分聊天来源，需要在**后端配置**上区分：

### 方案：统一工具 + 不同处理

1. **后端配置相同的工具**：Frontend 和 SDK 都使用 `exec_script` 工具
2. **前端/SDK 自行处理**：各自监听 `exec_script` 事件并自行决定如何执行

### Frontend 处理流程

```
LLM 调用 exec_script -> Frontend 监听到 tool_call -> 通过 MCP 执行 run_scripts -> 展示模型
```

### SDK 处理流程

```
LLM 调用 exec_script -> SDK 监听到 tool_call -> 用户自行处理（WebSocket/显示等）
```

## 工具对比

| 工具名称 | 执行位置 | 返回内容 | 适用场景 |
|----------|----------|----------|----------|
| `exec_script` | 调用方 | 脚本内容 | SDK/自定义前端 |
| `cad_script_run_scripts` | MCP 服务器 | 执行结果 + 文件 URL | Frontend 通过 MCP |

## 完整工作流程

### 方式 1: SDK 直接处理

```
用户请求 -> LLM -> exec_script -> SDK 接收 -> 用户自定义处理
```

### 方式 2: Frontend 通过 MCP

```
用户请求 -> LLM -> exec_script -> Frontend 监听 -> MCP run_scripts -> 执行 -> 展示
```

### 方式 3: 使用现成的 MCP 工具

```
用户请求 -> LLM -> cad_script_run_scripts -> MCP 执行 -> 返回 URL -> 展示
```
