# @deer-flow/js-sdk

JavaScript/TypeScript SDK for DeerFlow AI Agent system.

## Installation

```bash
npm install @deer-flow/js-sdk
# or
yarn add @deer-flow/js-sdk
# or
pnpm add @deer-flow/js-sdk
```

## Quick Start

```typescript
import { DeerFlowClient } from "@deer-flow/js-sdk";

// Initialize the client
const client = new DeerFlowClient({
  baseUrl: "http://localhost:8001",
  userId: "your-user-id", // Optional: for thread isolation
  authToken: "your-token", // Optional: for authentication
});

// Create a new conversation thread
const thread = await client.threads.create();
console.log("Created thread:", thread.thread_id);

// Send a message and stream the response
for await (const event of client.threads.stream(thread.thread_id, {
  messages: [{ type: "human", content: "Hello!" }]
})) {
  if (event.type === "messages-tuple") {
    for (const msg of event.data) {
      console.log("Message:", msg.content);
    }
  }
}
```

## API Reference

### Client Configuration

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `baseUrl` | string | Yes | Backend API base URL (e.g., `http://localhost:8001`) |
| `userId` | string | No | User ID for thread isolation |
| `authToken` | string | No | Authentication token |
| `timeout` | number | No | Request timeout in milliseconds (default: 30000) |

### Threads API

#### Create a Thread

```typescript
const thread = await client.threads.create({
  assistant_id: "lead_agent", // Optional
  metadata: { theme: "dark" }, // Optional
});
```

#### Get a Thread

```typescript
const thread = await client.threads.get(threadId);
```

#### Update a Thread

```typescript
await client.threads.update(threadId, {
  metadata: { theme: "light" },
});
```

#### Delete a Thread

```typescript
await client.threads.delete(threadId);
```

#### Search Threads

```typescript
const threads = await client.threads.search({
  metadata: { theme: "dark" },
  limit: 10,
  offset: 0,
  status: "idle",
  sortBy: "updated_at",
  sortOrder: "desc",
});
```

#### Stream a Thread

```typescript
for await (const event of client.threads.stream(threadId, {
  messages: [
    {
      type: "human",
      content: "What is the weather today?",
    },
  ],
  config: {
    recursion_limit: 100,
  },
})) {
  switch (event.type) {
    case "values":
      console.log("State update:", event.data);
      break;
    case "messages-tuple":
      for (const msg of event.data) {
        console.log("Message:", msg.content);
      }
      break;
    case "custom":
      console.log("Custom event:", event.data);
      break;
    case "langchain":
      console.log("LangChain event:", event.event, event.data);
      break;
    case "end":
      console.log("Token usage:", event.usage);
      break;
  }
}
```

#### Stream with Tool Call Event Handlers

当你需要在其他平台接入 DeerFlow API，并希望在接收到特定 tool call 时执行操作时，可以使用 `streamWithHandlers` 方法：

```typescript
// 定义工具调用事件处理器
await client.threads.streamWithHandlers(threadId, {
  messages: [{ type: "human", content: "帮我执行一个脚本" }],
  config: {
    configurable: {
      assistant_id: "lead_agent"
    }
  },
  // 注册工具调用事件处理器
  handlers: {
    // exec_script 事件：当 Agent 请求执行脚本时
    exec_script: (event) => {
      console.log("执行脚本:", event.args.script);
      console.log("描述:", event.args.description);
      console.log("语言:", event.args.language);
      
      // 在这里你可以：
      // 1. 显示脚本内容给用户确认
      // 2. 在浏览器中执行（如 JavaScript）
      // 3. 通过 WebSocket 发送到后端执行
      // 4. 记录到日志
    },
    // present_files 事件：当 Agent 请求展示文件时
    present_files: (event) => {
      console.log("展示文件:", event.args.filepaths);
      // 打开文件查看器或下载文件
    },
    // present_model 事件：当 Agent 请求展示模型时
    present_model: (event) => {
      console.log("展示模型:", event.args);
      // 打开 3D 模型查看器
    }
  },
  // 启用调试模式，打印所有事件到控制台
  debug: true
});
```

**事件对象结构：**

```typescript
interface ToolCallEvent {
  // 工具名称，如 "exec_script", "present_files"
  name: string;
  // 工具调用 ID
  id: string;
  // 工具参数（已解析为对象）
  args: Record<string, unknown>;
  // 原始 tool call 对象
  toolCall: ToolCall;
}
```

**可用处理器：**

| 处理器名称 | 触发条件 | 常用参数 |
|-----------|----------|---------|
| `exec_script` | Agent 请求执行脚本 | `script`, `description`, `language` |
| `present_files` | Agent 请求展示文件 | `filepaths` |
| `present_model` | Agent 请求展示模型 | 模型相关参数 |
| `[custom]` | 自定义工具 | 取决于工具定义 |

#### Run and Wait

```typescript
const result = await client.threads.runAndWait(threadId, {
  messages: [{ type: "human", content: "Hello!" }],
});
console.log("Result:", result);
```

### Runs API

#### List Runs

```typescript
const runs = await client.runs.list(threadId);
```

#### Get Run Details

```typescript
const run = await client.runs.get(threadId, runId);
```

#### Cancel a Run

```typescript
await client.runs.cancel(threadId, runId);
```

#### Get Run Messages

```typescript
const { data: messages, has_more } = await client.runs.getMessages(threadId, runId);
```

### Uploads API

#### Upload Files

```typescript
const files = await inputElement.files;
const result = await client.uploads.upload(threadId, Array.from(files));
console.log("Uploaded:", result.files);
```

#### List Uploaded Files

```typescript
const files = await client.uploads.list(threadId);
```

#### Delete an Uploaded File

```typescript
await client.uploads.delete(threadId, "filename.pdf");
```

### Artifacts API

#### Get an Artifact

```typescript
const blob = await client.artifacts.get(threadId, "path/to/artifact.html");
```

#### Download an Artifact

```typescript
await client.artifacts.download(threadId, "path/to/artifact.html", "download.html");
```

### Models API

#### List Models

```typescript
const models = await client.models.list();
```

#### Get Model Details

```typescript
const model = await client.models.get("claude-3-5-sonnet");
```

### Memory API

#### Get Memory

```typescript
const memory = await client.memory.get();
console.log("User context:", memory.userContext);
console.log("Facts:", memory.facts);
```

#### Reload Memory

```typescript
await client.memory.reload();
```

### MCP API

#### Get MCP Config

```typescript
const config = await client.mcp.getConfig();
```

#### Update MCP Config

```typescript
await client.mcp.updateConfig({
  "my-server": {
    name: "my-server",
    enabled: true,
    type: "stdio",
    command: "node",
    args: ["server.js"],
  },
});
```

### Skills API

#### List Skills

```typescript
const skills = await client.skills.list();
```

#### Get Skill Details

```typescript
const skill = await client.skills.get("my-skill");
```

#### Update Skill

```typescript
await client.skills.update("my-skill", true); // Enable
```

#### Install a Skill

```typescript
const formData = new FormData();
formData.append("file", skillFile);
const skill = await client.skills.install(formData);
```

### Feedback API

#### Create Feedback

```typescript
const feedback = await client.feedback.create(threadId, runId, {
  key: "helpfulness",
  score: 1,
  comment: "Very helpful!",
});
```

#### List Feedback

```typescript
const feedbacks = await client.feedback.list(threadId, runId);
```

#### Delete Feedback

```typescript
await client.feedback.delete(threadId, runId, feedbackId);
```

### Token Usage

```typescript
const usage = await client.getTokenUsage(threadId);
console.log("Total tokens:", usage.total_tokens);
console.log("By model:", usage.by_model);
```

## Error Handling

```typescript
import { DeerFlowError, AuthenticationError, NotFoundError } from "@deer-flow/js-sdk";

try {
  await client.threads.get("non-existent-id");
} catch (error) {
  if (error instanceof NotFoundError) {
    console.log("Thread not found");
  } else if (error instanceof AuthenticationError) {
    console.log("Authentication failed");
  } else if (error instanceof DeerFlowError) {
    console.log("DeerFlow error:", error.message);
  } else {
    console.log("Unknown error:", error);
  }
}
```

## Browser vs Node.js

This SDK works in both browser and Node.js environments.

### Node.js Example

```typescript
import { DeerFlowClient } from "@deer-flow/js-sdk";

const client = new DeerFlowClient({
  baseUrl: "http://localhost:8001",
});

// Use in Node.js
const thread = await client.threads.create();
```

### Browser Example

```typescript
import { DeerFlowClient } from "@deer-flow/js-sdk";

const client = new DeerFlowClient({
  baseUrl: "/api", // Relative path works in browser
});

// Use in browser
const thread = await client.threads.create();
```

## License

MIT
