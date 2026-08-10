/**
 * DeerFlow JavaScript SDK Types
 */

// ============================================================================
// Core Types
// ============================================================================

export interface ClientConfig {
  /** Backend API base URL (e.g., http://localhost:8001) */
  baseUrl: string;
  /** Optional authentication token */
  authToken?: string;
  /** Optional user ID for thread isolation */
  userId?: string;
  /** Request timeout in milliseconds (default: 30000) */
  timeout?: number;
}

// ============================================================================
// Thread Types
// ============================================================================

export interface Thread {
  thread_id: string;
  status: "idle" | "busy" | "interrupted" | "error";
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  values: ThreadState;
  interrupts: Record<string, unknown>;
}

export interface ThreadState {
  title: string;
  messages: Message[];
  artifacts?: string[];
  todos?: Todo[];
}

export interface ThreadCreateOptions {
  thread_id?: string;
  assistant_id?: string;
  metadata?: Record<string, unknown>;
}

export interface ThreadSearchOptions {
  metadata?: Record<string, unknown>;
  limit?: number;
  offset?: number;
  status?: "idle" | "busy" | "interrupted" | "error";
  sortBy?: "created_at" | "updated_at";
  sortOrder?: "asc" | "desc";
}

// ============================================================================
// Message Types
// ============================================================================

export type MessageContent = string | TextContentPart[];

export interface TextContentPart {
  type: "text";
  text: string;
}

export interface ImageContentPart {
  type: "image_url";
  image_url: {
    url: string;
    detail?: "low" | "high" | "auto";
  };
}

export type ContentPart = TextContentPart | ImageContentPart;

export interface Message {
  id?: string;
  type: "human" | "ai" | "system" | "tool";
  content: MessageContent;
  name?: string;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
  additional_kwargs?: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string; // JSON string
  };
  // 解析后的参数对象（用于事件处理）
  args?: Record<string, unknown>;
}

// ============================================================================
// Tool Call 事件处理类型
// ============================================================================

/**
 * Tool Call 事件数据
 */
export interface ToolCallEvent {
  /** 工具名称，如 "exec_script", "present_files" */
  name: string;
  /** 工具调用 ID */
  id: string;
  /** 工具参数（已解析） */
  args: Record<string, unknown>;
  /** 原始 tool call 对象 */
  toolCall: ToolCall;
}

/**
 * 事件处理器回调
 * @param event 工具调用事件
 * @returns 处理结果，可以返回 void 或结果对象
 */
export type ToolCallHandler = (event: ToolCallEvent) => void | Promise<void>;

/**
 * 事件处理器注册表
 */
export interface EventHandlers {
  /** exec_script 工具处理器 - 执行脚本 */
  exec_script?: ToolCallHandler;
  /** present_files 工具处理器 - 展示文件 */
  present_files?: ToolCallHandler;
  /** present_model 工具处理器 - 展示模型 */
  present_model?: ToolCallHandler;
  /** 自定义工具处理器 */
  [customTool: string]: ToolCallHandler | undefined;
}

/**
 * Stream 事件处理选项
 */
export interface StreamWithHandlersOptions {
  /** 消息数组 */
  messages: Message[];
  /** 可选的配置 */
  config?: Record<string, unknown>;
  /** 流式模式，默认为 ["values", "messages", "custom"] */
  streamModes?: StreamMode[];
  /** 工具调用事件处理器 */
  handlers?: EventHandlers;
  /** 是否打印所有事件到控制台（调试用） */
  debug?: boolean;
}

export interface AIMessage extends Message {
  type: "ai";
  response_metadata?: Record<string, unknown>;
}

// ============================================================================
// Run Types
// ============================================================================

export interface Run {
  run_id: string;
  thread_id: string;
  status: "pending" | "running" | "success" | "error" | "cancelled";
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  error?: string;
}

export interface RunCreateOptions {
  assistant_id?: string;
  input?: Partial<ThreadState>;
  config?: RunConfig;
  metadata?: Record<string, unknown>;
}

export interface RunConfig {
  recursion_limit?: number;
  configurable?: Record<string, unknown>;
}

export interface StreamOptions {
  threadId?: string;
  assistantId?: string;
  config?: RunConfig;
  context?: Record<string, unknown>;
  signal?: AbortSignal;
}

/**
 * Stream mode options for LangGraph streaming
 *
 * Based on backend docs/STREAMING.md:
 * - "values": Node-level state snapshots (title, messages, artifacts)
 * - "messages": Token-level deltas from LLM streaming
 * - "messages-tuple": HTTP SDK variant of messages mode
 * - "messages-last": Custom mode that only returns the last message from values snapshot
 * - "custom": Explicit StreamWriter.write() events
 * - "updates": Graph node updates
 * - "events": LangGraph events
 * - "debug": Debug information
 * - "tasks": Task information
 * - "checkpoints": Checkpoint information
 */
export type StreamMode =
  | "values"
  | "messages"
  | "messages-tuple"
  | "messages-last"
  | "custom"
  | "updates"
  | "events"
  | "debug"
  | "tasks"
  | "checkpoints";

export interface StreamRequestOptions {
  messages: Message[];
  config?: Record<string, unknown>;
  streamModes?: StreamMode[];
}

// ============================================================================
// Stream Event Types
// ============================================================================

export type StreamEvent =
  | ValuesEvent
  | MessagesEvent
  | CustomEvent
  | LangChainEvent
  | EndEvent;

export interface ValuesEvent {
  type: "values";
  data: Partial<ThreadState>;
}

export interface MessagesEvent {
  type: "messages-tuple";
  data: Message[];
}

export interface CustomEvent {
  type: "custom";
  data: unknown;
}

export interface LangChainEvent {
  type: "langchain";
  event: string;
  name: string;
  data: unknown;
  metadata?: Record<string, unknown>;
}

export interface EndEvent {
  type: "end";
  usage?: TokenUsage;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

// ============================================================================
// Artifact Types
// ============================================================================

export interface Artifact {
  path: string;
  type: string;
  size?: number;
  created_at?: string;
}

// ============================================================================
// File Upload Types
// ============================================================================

export interface UploadFile {
  filename: string;
  size: number;
  path: string;
  status: "uploading" | "uploaded" | "error";
  error?: string;
}

export interface UploadResponse {
  success: boolean;
  files: UploadFile[];
}

// ============================================================================
// Model Types
// ============================================================================

export interface Model {
  name: string;
  display_name: string;
  provider: string;
  supports_thinking: boolean;
  supports_vision: boolean;
  max_tokens?: number;
}

// ============================================================================
// Memory Types
// ============================================================================

export interface MemoryFact {
  id: string;
  content: string;
  category: "preference" | "knowledge" | "context" | "behavior" | "goal";
  confidence: number;
  created_at: string;
  source: string;
}

export interface MemoryData {
  userContext: string;
  personalContext: string;
  topOfMind: string[];
  recentMonths: string;
  earlierContext: string;
  longTermBackground: string;
  facts: MemoryFact[];
}

// ============================================================================
// MCP Types
// ============================================================================

export interface MCPServer {
  name: string;
  enabled: boolean;
  type: "stdio" | "sse" | "http";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  description?: string;
}

// ============================================================================
// Skill Types
// ============================================================================

export interface Skill {
  name: string;
  description: string;
  enabled: boolean;
  category?: string;
  allowed_tools?: string[];
}

// ============================================================================
// Feedback Types
// ============================================================================

export interface Feedback {
  feedback_id: string;
  run_id: string;
  key: string;
  score: number;
  comment?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================================
// Todo Types
// ============================================================================

export interface Todo {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed";
  activeForm?: string;
}

// ============================================================================
// Error Types
// ============================================================================

export class DeerFlowError extends Error {
  constructor(
    message: string,
    public readonly cause?: unknown,
    public readonly statusCode?: number,
  ) {
    super(message);
    this.name = "DeerFlowError";
  }
}

export class AuthenticationError extends DeerFlowError {
  constructor(message = "Authentication failed") {
    super(message, undefined, 401);
    this.name = "AuthenticationError";
  }
}

export class NotFoundError extends DeerFlowError {
  constructor(message = "Resource not found") {
    super(message, undefined, 404);
    this.name = "NotFoundError";
  }
}

export class NetworkError extends DeerFlowError {
  constructor(message = "Network error", cause?: unknown) {
    super(message, cause, undefined);
    this.name = "NetworkError";
  }
}
