# DeerFlow Java SDK

DeerFlow 的 Java SDK，提供与 DeerFlow 后端 API 交互的 Java 接口。

## 功能特性

- **线程管理**: 创建、更新、删除和搜索线程
- **流式响应**: 实时流式处理线程运行
- **聊天模式**: 简单的聊天接口，自动累积响应
- **文件上传**: 上传和管理文件
- **模型管理**: 列出和获取可用模型
- **内存管理**: 访问和管理用户记忆
- **MCP 配置**: 配置 MCP 服务器
- **技能管理**: 列出和管理技能
- **反馈管理**: 创建和管理反馈

## 环境要求

- Java 11 或更高版本

## 依赖

SDK 需要以下依赖：

| 依赖 | 版本 | 说明 |
|------|------|------|
| OkHttp | 4.12.0 | HTTP 客户端 |
| Okio | 3.6.0 | IO 库（OkHttp 传递依赖） |
| Kotlin Stdlib | 1.9.0 | Kotlin 标准库（传递依赖） |

### 使用 Maven 获取依赖

```bash
# 下载依赖到 libs 目录
mvn dependency:copy-dependencies -DoutputDirectory=libs
```

### 使用 Gradle 获取依赖

```bash
# 下载依赖到 libs 目录
gradle copyDependencies
```

### 手动下载

从 [Maven Central](https://repo.maven.apache.org/maven2/) 下载：
- [okhttp-4.12.0.jar](https://repo.maven.apache.org/maven2/com/squareup/okhttp3/okhttp/4.12.0/okhttp-4.12.0.jar)
- [okio-jvm-3.6.0.jar](https://repo.maven.apache.org/maven2/com/squareup/okio/okio-jvm/3.6.0/okio-jvm-3.6.0.jar)
- [kotlin-stdlib-1.9.0.jar](https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/1.9.0/kotlin-stdlib-1.9.0.jar)

## 项目结构

```
android-sdk/
├── src/
│   └── com/deerflow/android/sdk/
│       ├── DeerFlowClient.java       # 主客户端
│       ├── HttpClient.java           # OkHttp 客户端
│       ├── ThreadsApi.java           # 线程 API
│       ├── RunsApi.java              # 运行 API
│       ├── UploadsApi.java           # 上传 API
│       ├── ModelsApi.java            # 模型 API
│       ├── MemoryApi.java            # 内存 API
│       ├── McpApi.java               # MCP API
│       ├── SkillsApi.java            # Skill API
│       ├── FeedbackApi.java          # 反馈 API
│       ├── ArtifactsApi.java         # 制品 API
│       ├── utils/
│       │   └── JsonUtils.java        # JSON 工具
│       ├── models/                   # 数据模型
│       │   ├── ClientConfig.java
│       │   ├── DeerFlowError.java
│       │   ├── Thread.java
│       │   ├── Message.java
│       │   ├── Run.java
│       │   ├── Stream.java
│       │   ├── Upload.java
│       │   ├── Model.java
│       │   ├── Memory.java
│       │   ├── MCP.java
│       │   ├── Skill.java
│       │   ├── Feedback.java
│       │   └── Todo.java
│       └── example/
│           └── QtEmbedExample.java   # 使用示例
└── README.md                         # 文档
```

## 快速开始

### 1. 初始化客户端

```java
import com.deerflow.android.sdk.DeerFlowClient;
import com.deerflow.android.sdk.models.ClientConfig;

DeerFlowClient client = new DeerFlowClient(
    new ClientConfig("http://172.16.37.164:8301")
);
```

### 2. 创建线程

```java
import com.deerflow.android.sdk.models.Thread;
import com.deerflow.android.sdk.models.ThreadCreateOptions;

Thread thread = client.getThreads().create(new ThreadCreateOptions());
System.out.println("创建线程：" + thread.getThreadId());
```

### 3. 发送消息（聊天模式）

```java
import com.deerflow.android.sdk.models.Message;
import com.deerflow.android.sdk.models.MessageType;

String response = client.getThreads().chat(
    thread.getThreadId(),
    Arrays.asList(new Message(MessageType.HUMAN, "你好！"))
);

System.out.println("响应：" + response);
```

### 4. 流式处理

```java
import com.deerflow.android.sdk.models.Message;
import com.deerflow.android.sdk.models.MessageType;
import com.deerflow.android.sdk.models.StreamMode;

client.getThreads().stream(
    thread.getThreadId(),
    Arrays.asList(new Message(MessageType.HUMAN, "你好！")),
    Arrays.asList(StreamMode.VALUES, StreamMode.MESSAGES, StreamMode.CUSTOM),
    (event, data) -> {
        System.out.println("事件：" + event + ", 数据：" + data);
    }
);
```

### 5. 等待完成

```java
import com.deerflow.android.sdk.models.ThreadState;

ThreadState state = client.getThreads().runAndWait(
    thread.getThreadId(),
    Arrays.asList(new Message(MessageType.HUMAN, "你好！"))
);

System.out.println("消息：" + state.getMessages());
```

## API 参考

### Threads API（线程）

```java
// 创建线程
Thread thread = client.getThreads().create();

// 获取线程
Thread thread = client.getThreads().get(threadId);

// 更新线程
client.getThreads().update(threadId, Map.of("key", "value"));

// 删除线程
client.getThreads().delete(threadId);

// 搜索线程
List<Thread> threads = client.getThreads().search(new ThreadSearchOptions());

// 获取线程状态
ThreadState state = client.getThreads().getState(threadId);

// 获取线程历史
List<ThreadState> history = client.getThreads().getHistory(threadId, 10);

// 更新线程状态
client.getThreads().updateState(threadId, Map.of("messages", List.of()));

// 从消息重新生成
client.getThreads().regenerate(threadId, messageId);
```

### Runs API（运行）

```java
// 列出运行
List<Run> runs = client.getRuns().list(threadId);

// 获取运行
Run run = client.getRuns().get(threadId, runId);

// 取消运行
client.getRuns().cancel(threadId, runId);

// 获取运行消息
RunMessagesResponse messages = client.getRuns().getMessages(threadId, runId);
```

### Uploads API（上传）

```java
// 上传文件
UploadResponse response = client.getUploads().upload(threadId, new File("/path/to/file"));

// 列出上传的文件
List<UploadFile> files = client.getUploads().list(threadId);

// 删除文件
client.getUploads().delete(threadId, filename);
```

### Models API（模型）

```java
// 列出模型
List<Model> models = client.getModels().list();

// 获取模型
Model model = client.getModels().get("model-name");
```

### Memory API（内存）

```java
// 获取内存
MemoryData memory = client.getMemory().get();

// 重新加载内存
client.getMemory().reload();

// 获取内存配置
Map<String, Object> config = client.getMemory().getConfig();
```

### MCP API

```java
// 获取 MCP 配置
Map<String, MCPServer> config = client.getMcp().getConfig();

// 更新 MCP 配置
client.getMcp().updateConfig(Map.of(
    "server-name", new MCPServer()
        .setName("server-name")
        .setEnabled(true)
        .setType(MCPServerType.STDIO)
        .setCommand("command")
        .setArgs(Arrays.asList("arg1", "arg2"))
));
```

### Skills API（技能）

```java
// 列出技能
List<Skill> skills = client.getSkills().list();

// 获取技能
Skill skill = client.getSkills().get("skill-name");

// 更新技能
client.getSkills().update("skill-name", true);
```

### Feedback API（反馈）

```java
// 创建反馈
Feedback feedback = client.getFeedback().create(
    threadId,
    runId,
    new FeedbackCreateOptions()
        .setKey("rating")
        .setScore(1.0f)
        .setComment("很好的响应！")
);

// 列出反馈
List<Feedback> feedbacks = client.getFeedback().list(threadId, runId);

// 删除反馈
client.getFeedback().delete(threadId, runId, feedbackId);
```

### Artifacts API（制品）

```java
// 获取制品
byte[] bytes = client.getArtifacts().get(threadId, artifactPath);

// 下载制品
client.getArtifacts().download(threadId, artifactPath, "output.txt");
```

## 类型说明

### Message（消息）

```java
public class Message {
    private String id;
    private MessageType type;      // HUMAN, AI, SYSTEM, TOOL
    private String content;
    private String name;
    private String tool_call_id;
    private List<ToolCall> tool_calls;
    private Map<String, Object> additional_kwargs;
}
```

### Thread（线程）

```java
public class Thread {
    private String thread_id;
    private ThreadStatus status;   // IDLE, BUSY, INTERRUPTED, ERROR
    private String created_at;
    private String updated_at;
    private Map<String, Object> metadata;
    private ThreadState values;
    private Map<String, Object> interrupts;
}
```

### StreamMode（流模式）

```java
public enum StreamMode {
    VALUES,           // 节点状态快照
    MESSAGES,         // 令牌级增量
    MESSAGES_TUPLE,   // HTTP SDK 变体
    MESSAGES_LAST,    // 仅返回最后一条消息
    CUSTOM,           // 显式 StreamWriter 事件
    UPDATES,          // 图节点更新
    EVENTS,           // LangGraph 事件
    DEBUG,            // 调试信息
    TASKS,            // 任务信息
    CHECKPOINTS       // 检查点信息
}
```

## 错误处理

SDK 抛出类型化的异常：

```java
import com.deerflow.android.sdk.models.*;

try {
    client.getThreads().create();
} catch (AuthenticationException e) {
    // 处理认证错误 (401)
} catch (NotFoundException e) {
    // 处理未找到错误 (404)
} catch (DeerFlowException e) {
    // 处理其他 SDK 错误
    System.err.println("错误：" + e.getMessage());
    if (e.getStatusCode() != null) {
        System.err.println("状态码：" + e.getStatusCode());
    }
} catch (Exception e) {
    // 处理其他异常
}
```

## 编译

### 使用 Maven

```bash
# 下载依赖
mvn dependency:copy-dependencies -DoutputDirectory=libs

# 编译所有源文件
mkdir -p build/classes
javac -d build/classes -cp "libs/*" $(find src -name "*.java")

# 运行示例
java -cp "build/classes:libs/*" com.deerflow.android.sdk.example.QtEmbedExample http://172.16.37.164:8301
```

### 使用 Gradle

```bash
# 下载依赖
gradle copyDependencies

# 编译
gradle build

# 运行示例
gradle run --args="http://172.16.37.164:8301"
```

### 手动编译

```bash
# 创建 libs 目录并下载依赖
mkdir -p libs
# 将下载的 jar 文件放入 libs 目录

# 编译所有源文件
mkdir -p build/classes
javac -d build/classes -cp "libs/*" $(find src -name "*.java")

# 运行示例
java -cp "build/classes:libs/*" com.deerflow.android.sdk.example.QtEmbedExample http://172.16.37.164:8301
```

## 许可证

MIT License
