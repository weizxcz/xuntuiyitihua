package com.deerflow.android.sdk.example;

import com.deerflow.android.sdk.DeerFlowClient;
import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * DeerFlow Java SDK 使用示例
 *
 * 演示如何使用 Java SDK 与 DeerFlow 后端通信
 * 不包含 Qt 通信，仅打印执行事件
 */
public class QtEmbedExample {

    private DeerFlowClient client;
    private String threadId;
    private boolean isStreaming = false;

    public QtEmbedExample(String baseUrl) {
        ClientConfig config = new ClientConfig(baseUrl);
        this.client = new DeerFlowClient(config);
    }

    /**
     * 初始化客户端并创建线程
     */
    public void initialize() throws Exception {
        System.out.println("=== 初始化 DeerFlow 客户端 ===");

        // 创建新线程
        Thread thread = client.getThreads().create();
        this.threadId = thread.getThreadId();

        System.out.println("创建线程成功：" + threadId);
    }

    /**
     * 处理聊天消息
     */
    public void handleChatMessage(String content) throws Exception {
        System.out.println("\n=== 处理消息 ===");
        System.out.println("用户：" + content);

        if (client == null || threadId == null) {
            initialize();
        }

        processMessage(content);
    }

    /**
     * 处理消息发送 - 使用流式模式
     */
    public void processMessage(String content) throws Exception {
        if (client == null || threadId == null) {
            System.err.println("SDK 未初始化，无法发送消息");
            return;
        }

        isStreaming = true;

        System.out.println("开始流式处理...");

        // 创建流
        client.getThreads().stream(
            threadId,
            Arrays.asList(new Message(MessageType.HUMAN, content)),
            Arrays.asList(StreamMode.VALUES, StreamMode.MESSAGES, StreamMode.CUSTOM),
            (event, data) -> {
                handleStreamEvent(event, data);
            }
        );

        isStreaming = false;
        System.out.println("消息处理完成");
    }

    /**
     * 处理流式事件
     */
    private void handleStreamEvent(String eventType, Object data) {
        System.out.println("\n--- 收到事件 ---");
        System.out.println("事件类型：" + eventType);
        System.out.println("数据：" + data);

        // 处理 messages 模式的事件
        if ("messages".equals(eventType) || "messages-tuple".equals(eventType)) {
            handleMessagesEvent(data);
        }

        // 处理 exec_script 事件
        if ("exec_script".equals(eventType)) {
            handleExecScriptEvent(data);
        }
    }

    /**
     * 处理 messages 事件
     */
    private void handleMessagesEvent(Object data) {
        System.out.println("处理 messages 事件...");

        // 这里可以解析消息内容并显示
        // 简化处理，实际项目中需要使用 JSON 解析
        System.out.println("消息数据：" + data);
    }

    /**
     * 处理 exec_script 事件
     */
    private void handleExecScriptEvent(Object data) {
        System.out.println("\n📜 检测到脚本执行请求!");

        // 解析脚本信息
        // 实际项目中需要使用 JSON 解析
        Map<String, Object> scriptInfo = (Map<String, Object>) data;

        String scriptId = (String) scriptInfo.getOrDefault("script_id", "script-" + System.currentTimeMillis());
        String description = (String) scriptInfo.getOrDefault("description", "无描述");
        String language = (String) scriptInfo.getOrDefault("language", "python");
        String script = (String) scriptInfo.getOrDefault("script", "");

        System.out.println("  脚本 ID: " + scriptId);
        System.out.println("  描述：" + description);
        System.out.println("  语言：" + language);
        System.out.println("  脚本内容:");
        System.out.println("  ---");
        for (String line : script.split("\n")) {
            System.out.println("  " + line);
        }
        System.out.println("  ---");

        // 打印执行事件，不实际执行
        System.out.println("  [事件] 脚本执行请求已打印，等待后续处理...");
    }

    /**
     * 运行示例
     */
    public void run() {
        try {
            // 初始化
            initialize();

            // 示例 1: 简单聊天
            System.out.println("\n========================================");
            System.out.println("示例 1: 简单聊天");
            System.out.println("========================================");
            handleChatMessage("你好，请介绍一下自己");

            // 示例 2: 请求执行脚本
            System.out.println("\n========================================");
            System.out.println("示例 2: 请求执行脚本");
            System.out.println("========================================");
            handleChatMessage("请帮我执行一个 Python 脚本，计算 1 到 100 的和");

            // 示例 3: 创建模型
            System.out.println("\n========================================");
            System.out.println("示例 3: 创建 3D 模型");
            System.out.println("========================================");
            handleChatMessage("请创建一个立方体模型");

            // 示例 4: 查询可用模型
            System.out.println("\n========================================");
            System.out.println("示例 4: 查询可用模型");
            System.out.println("========================================");
            List<Model> models = client.getModels().list();
            System.out.println("可用模型:");
            for (Model model : models) {
                System.out.println("  - " + model.getName() + " (" + model.getDisplayName() + ")");
            }

            // 示例 5: 查询可用技能
            System.out.println("\n========================================");
            System.out.println("示例 5: 查询可用技能");
            System.out.println("========================================");
            List<Skill> skills = client.getSkills().list();
            System.out.println("可用技能:");
            for (Skill skill : skills) {
                System.out.println("  - " + skill.getName() + ": " + skill.getDescription());
            }

        } catch (Exception e) {
            System.err.println("示例运行失败：" + e.getMessage());
            e.printStackTrace();
        }
    }

    /**
     * 主方法
     */
    public static void main(String[] args) {
        // 后端地址，可通过命令行参数指定
        String baseUrl = "http://localhost:8001";
        if (args.length > 0) {
            baseUrl = args[0];
        }

        System.out.println("DeerFlow Java SDK 示例");
        System.out.println("后端地址：" + baseUrl);
        System.out.println();

        QtEmbedExample example = new QtEmbedExample(baseUrl);
        example.run();
    }
}
