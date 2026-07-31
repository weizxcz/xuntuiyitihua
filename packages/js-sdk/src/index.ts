/**
 * DeerFlow JavaScript SDK
 *
 * A TypeScript/JavaScript SDK for interacting with the DeerFlow AI Agent system.
 *
 * @example
 * ```typescript
 * import { DeerFlowClient } from "@deer-flow/js-sdk";
 *
 * const client = new DeerFlowClient({
 *   baseUrl: "http://localhost:8001",
 *   userId: "user-123",
 * });
 *
 * // Create a new conversation thread
 * const thread = await client.threads.create();
 * console.log("Created thread:", thread.thread_id);
 *
 * // Send a message and stream the response
 * for await (const event of client.threads.stream(thread.thread_id, {
 *   messages: [{ type: "human", content: "Hello!" }]
 * })) {
 *   if (event.type === "messages-tuple") {
 *     for (const msg of event.data) {
 *       console.log("Message:", msg.content);
 *     }
 *   }
 * }
 * ```
 *
 * @example
 * ```typescript
 * // 使用 streamWithHandlers 处理工具调用事件
 * await client.threads.streamWithHandlers(threadId, {
 *   messages: [{ type: "human", content: "帮我执行一个脚本" }],
 *   handlers: {
 *     // 当 Agent 请求执行脚本时
 *     exec_script: (event) => {
 *       console.log("执行脚本:", event.args.script);
 *       console.log("描述:", event.args.description);
 *     },
 *     // 当 Agent 请求展示文件时
 *     present_files: (event) => {
 *       console.log("展示文件:", event.args.filepaths);
 *     }
 *   }
 * });
 * ```
 */

export { DeerFlowClient } from "./client";
export { HttpClient } from "./http-client";

// Type exports
export type {
  ClientConfig,
  Thread,
  ThreadState,
  ThreadCreateOptions,
  ThreadSearchOptions,
  Message,
  MessageContent,
  TextContentPart,
  ImageContentPart,
  ContentPart,
  AIMessage,
  ToolCall,
  ToolCallEvent,
  EventHandlers,
  StreamWithHandlersOptions,
  Run,
  RunCreateOptions,
  RunConfig,
  StreamOptions,
  StreamEvent,
  ValuesEvent,
  MessagesEvent,
  CustomEvent,
  LangChainEvent,
  EndEvent,
  TokenUsage,
  Artifact,
  UploadFile,
  UploadResponse,
  Model,
  MemoryData,
  MemoryFact,
  MCPServer,
  Skill,
  Feedback,
  Todo,
} from "./types";

// Error exports
export {
  DeerFlowError,
  AuthenticationError,
  NotFoundError,
  NetworkError,
} from "./types";
