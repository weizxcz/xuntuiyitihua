/**
 * DeerFlow JavaScript SDK Core Client
 *
 * @example
 * ```typescript
 * import { DeerFlowClient } from "@deer-flow/js-sdk";
 *
 * const client = new DeerFlowClient({
 *   baseUrl: "http://localhost:8001",
 * });
 *
 * // Create a new thread
 * const thread = await client.threads.create();
 *
 * // Stream with all modes (values, messages, custom)
 * for await (const event of client.threads.stream(thread.thread_id, {
 *   messages: [{ type: "human", content: "Hello!" }]
 * })) {
 *   console.log(event.type, event.data);
 * }
 *
 * // Simple chat with auto-accumulation
 * const response = await client.threads.chat(thread.thread_id, {
 *   messages: [{ type: "human", content: "Hello!" }]
 * });
 * console.log(response);
 * ```
 *
 * @see Backend streaming documentation for stream mode details
 */

import { HttpClient } from "./http-client";
import type {
  ClientConfig,
  Thread,
  ThreadCreateOptions,
  ThreadSearchOptions,
  ThreadState,
  Message,
  Run,
  RunCreateOptions,
  StreamOptions,
  StreamEvent,
  StreamMode,
  UploadFile,
  UploadResponse,
  Model,
  MemoryData,
  MCPServer,
  Skill,
  Feedback,
  Artifact,
  ToolCall,
  ToolCallEvent,
  EventHandlers,
  StreamWithHandlersOptions,
} from "./types";

export class DeerFlowClient {
  private http: HttpClient;
  private userId?: string;

  constructor(config: ClientConfig) {
    this.http = new HttpClient(config);
    this.userId = config.userId;
  }

  /**
   * Get the threads API client
   */
  get threads() {
    // Save http reference at the beginning to preserve it for generator functions
    const httpClient = this.http;
    return {
      /**
       * Create a new thread
       */
      create: async (options?: ThreadCreateOptions): Promise<Thread> => {
        return httpClient.post<Thread>("/api/threads", {
          thread_id: options?.thread_id,
          assistant_id: options?.assistant_id,
          metadata: options?.metadata,
        });
      },

      /**
       * Get a thread by ID
       */
      get: async (threadId: string): Promise<Thread> => {
        return httpClient.get<Thread>(`/api/threads/${threadId}`);
      },

      /**
       * Update a thread
       */
      update: async (threadId: string, updates: { metadata?: Record<string, unknown> }): Promise<Thread> => {
        return httpClient.put<Thread>(`/api/threads/${threadId}`, updates);
      },

      /**
       * Delete a thread
       */
      delete: async (threadId: string): Promise<void> => {
        await httpClient.delete(`/api/threads/${threadId}`);
        // Also clean up local thread data
        await httpClient.delete(`/api/threads/${threadId}`);
      },

      /**
       * Search threads
       */
      search: async (options?: ThreadSearchOptions): Promise<Thread[]> => {
        return httpClient.post<Thread[]>("/api/threads/search", {
          metadata: options?.metadata,
          limit: options?.limit,
          offset: options?.offset,
          status: options?.status,
          sort_by: options?.sortBy,
          sort_order: options?.sortOrder,
        });
      },

      /**
       * Update thread state
       */
      updateState: async (threadId: string, state: Partial<ThreadState>): Promise<void> => {
        return httpClient.post(`/api/threads/${threadId}/state`, {
          values: state,
        });
      },

      /**
       * Get thread state
       */
      getState: async (threadId: string): Promise<ThreadState> => {
        return httpClient.get<ThreadState>(`/api/threads/${threadId}/state`);
      },

      /**
       * Get thread history
       */
      getHistory: async (threadId: string, limit?: number): Promise<ThreadState[]> => {
        return httpClient.get<ThreadState[]>(`/api/threads/${threadId}/history`, { limit });
      },

      /**
       * Stream a thread run with messages
       *
       * @example
       * ```typescript
       * // Default: subscribe to all three modes (values, messages, custom)
       * for await (const event of client.threads.stream(threadId, {
       *   messages: [{ type: "human", content: "Hello!" }]
       * })) {
       *   console.log(event.type, event.data);
       * }
       *
       * // Custom modes: subscribe to specific modes
       * for await (const event of client.threads.stream(threadId, {
       *   messages: [{ type: "human", content: "Hello!" }],
       *   streamModes: ["messages", "custom"]
       * })) {
       *   console.log(event);
       * }
       * ```
       */
      stream: async function* (
        threadId: string,
        options: {
          messages: Message[];
          config?: Record<string, unknown>;
          streamModes?: StreamMode[];
        },
      ): AsyncGenerator<StreamEvent> {
        // Use httpClient from closure
        const streamModes = options.streamModes ?? ["values", "messages", "custom"];

        const response = await fetch(`${httpClient.getBaseUrl()}/api/threads/${threadId}/runs/stream`, {
          method: "POST",
          headers: httpClient.getDefaultHeaders(),
          body: JSON.stringify({
            input: { messages: options.messages },
            config: options.config,
            stream_mode: streamModes,
          }),
        });

        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error("Response body is null");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let currentEvent = ""; // 用于存储当前事件的 type

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            // 解析 event: 行
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim();
              continue;
            }

            // 解析 data: 行
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                // 添加 event type 到 parsed 对象
                yield { type: currentEvent, data: parsed } as StreamEvent;
                // 重置 currentEvent，每个 data 事件后重置
                currentEvent = "";
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }
      },

      /**
       * Run a thread and wait for completion
       */
      runAndWait: async (threadId: string, options: { messages: Message[]; config?: Record<string, unknown> }): Promise<ThreadState> => {
        return this.http.post<ThreadState>(`/api/threads/${threadId}/runs/wait`, {
          input: { messages: options.messages },
          config: options.config,
        });
      },

      /**
       * Regenerate from a specific message
       */
      regenerate: async (threadId: string, messageId: string): Promise<void> => {
        await this.http.post(`/api/threads/${threadId}/runs/regenerate/prepare`, {
          message_id: messageId,
        });
      },

      /**
       * Stream a thread run with tool call event handlers
       *
       * @example
       * ```typescript
       * await client.threads.streamWithHandlers(threadId, {
       *   messages: [{ type: "human", content: "Hello!" }],
       *   handlers: {
       *     exec_script: (event) => {
       *       console.log("执行脚本:", event.args.script);
       *     },
       *     present_files: (event) => {
       *       console.log("展示文件:", event.args.filepaths);
       *     }
       *   }
       * });
       *
       * // Custom stream modes
       * await client.threads.streamWithHandlers(threadId, {
       *   messages: [{ type: "human", content: "Hello!" }],
       *   streamModes: ["values", "messages", "custom"],
       *   handlers: { ... }
       * });
       * ```
       */
      streamWithHandlers: async (
        threadId: string,
        options: StreamWithHandlersOptions & { streamModes?: StreamMode[] },
      ): Promise<void> => {
        const { messages, config, handlers, debug, streamModes } = options;

        const response = await fetch(`${httpClient.getBaseUrl()}/api/threads/${threadId}/runs/stream`, {
          method: "POST",
          headers: httpClient.getDefaultHeaders(),
          body: JSON.stringify({
            input: { messages },
            config,
            stream_mode: streamModes ?? ["values", "messages", "custom"],
          }),
        });

        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error("Response body is null");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // 用于跟踪已处理的 tool call ID，避免重复触发
        const processedToolCallIds = new Set<string>();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);

                // 跳过 null 或无效数据
                if (!parsed || typeof parsed !== 'object') {
                  continue;
                }

                if (debug) {
                  console.log("[DeerFlow SDK] 收到事件:", parsed.type, parsed);
                }

                // 提取消息的辅助函数
                const extractMessages = (parsed: any): Message[] => {
                  const messages: Message[] = [];

                  // 处理 parsed 直接就是包含 messages 数组的对象（没有 data 包装）
                  // 当前后端格式：{ messages: [...] }，type 为 undefined
                  if (Array.isArray(parsed.messages)) {
                    if (debug) {
                      console.log("[DeerFlow SDK] 直接提取 parsed.messages，数量:", parsed.messages.length);
                    }
                    messages.push(...parsed.messages);
                    return messages;
                  }

                  if (!parsed.data) {
                    return messages;
                  }

                  // messages 模式（LangGraph 原生）：data 是 [messageChunk, metadata] 元组
                  if (parsed.type === "messages" && Array.isArray(parsed.data)) {
                    // data 是 [messageChunk, metadata] 格式
                    if (parsed.data.length >= 1) {
                      const msgChunk = parsed.data[0];
                      if (msgChunk && typeof msgChunk === "object") {
                        if (debug) {
                          console.log("[DeerFlow SDK] messages 模式 - 提取消息:", msgChunk.content);
                        }
                        messages.push(msgChunk);
                      }
                    }
                    return messages;
                  }

                  // messages-tuple 模式：data 是单个消息对象（不是数组）
                  if (parsed.type === "messages-tuple") {
                    if (parsed.data && typeof parsed.data === "object") {
                      messages.push(parsed.data);
                    }
                    return messages;
                  }

                  // values 模式：data 包含完整的消息历史
                  if (parsed.type === "values" && parsed.data?.messages) {
                    messages.push(...parsed.data.messages);
                  }

                  return messages;
                };

                // 提取并处理所有消息中的 tool_calls
                const allMessages = extractMessages(parsed);

                for (const msg of allMessages) {
                  if (!msg || msg.type !== "ai") {
                    continue;
                  }

                  // 处理两种格式：
                  // 1. 标准格式：tool_calls 数组
                  // 2. LangChain Chunk 格式：tool_call_chunks 数组（增量模式）
                  const toolCallData = msg.tool_calls || (msg as any).tool_call_chunks || [];

                  for (const rawToolCall of toolCallData) {
                    // 避免重复处理同一个 tool call
                    if (rawToolCall.id && processedToolCallIds.has(rawToolCall.id)) {
                      continue;
                    }
                    if (rawToolCall.id) {
                      processedToolCallIds.add(rawToolCall.id);
                    }

                    // 解析工具参数 - 处理不同的格式
                    let toolName: string;
                    let args: Record<string, unknown> = {};

                    // LangChain Chunk 格式：{ name, arguments, id }
                    if ("name" in rawToolCall && typeof rawToolCall.name === "string") {
                      toolName = rawToolCall.name;
                      if (rawToolCall.arguments) {
                        args = typeof rawToolCall.arguments === "string"
                          ? JSON.parse(rawToolCall.arguments)
                          : rawToolCall.arguments as Record<string, unknown>;
                      }
                    }
                    // function 格式：{ id, function: { name, arguments } }
                    else if ("function" in rawToolCall && rawToolCall.function) {
                      toolName = rawToolCall.function.name;
                      if (typeof rawToolCall.function.arguments === "string") {
                        args = JSON.parse(rawToolCall.function.arguments);
                      } else {
                        args = rawToolCall.function.arguments as Record<string, unknown>;
                      }
                    }
                    else {
                      // 无法解析，跳过
                      continue;
                    }

                    const event: ToolCallEvent = {
                      name: toolName,
                      id: rawToolCall.id,
                      args,
                      toolCall: rawToolCall,
                    };

                    if (debug) {
                      console.log("[DeerFlow SDK] ToolCall 事件:", event);
                    }

                    // 查找对应的处理器
                    const handler = handlers?.[event.name];
                    if (handler) {
                      if (debug) {
                        console.log(`[DeerFlow SDK] 调用处理器：${event.name}`);
                      }
                      await handler(event);
                    }
                  }
                }
              } catch (e) {
                if (debug) {
                  console.log("[DeerFlow SDK] 解析事件失败:", e, data);
                }
              }
            }
          }
        }
      },

      /**
       * Send a message and get the full response (non-streaming)
       *
       * This method subscribes to all stream modes and accumulates the AI response
       * into a complete message before returning.
       *
       * @example
       * ```typescript
       * const response = await client.threads.chat(threadId, {
       *   messages: [{ type: "human", content: "Hello!" }]
       * });
       * console.log(response); // "Hello! How can I help you?"
       * ```
       */
      chat: async (
        threadId: string,
        options: {
          messages: Message[];
          config?: Record<string, unknown>;
        },
      ): Promise<string> => {
        const chunks: Record<string, string[]> = {};
        let lastId = "";

        // Direct stream call with all modes
        const response = await fetch(`${httpClient.getBaseUrl()}/api/threads/${threadId}/runs/stream`, {
          method: "POST",
          headers: httpClient.getDefaultHeaders(),
          body: JSON.stringify({
            input: { messages: options.messages },
            config: options.config,
            stream_mode: ["values", "messages", "custom"],
          }),
        });

        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error("Response body is null");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                // Accumulate AI message deltas by message ID
                if (parsed.type === "messages-tuple" && parsed.data && typeof parsed.data === "object") {
                  const msg = parsed.data as Message;
                  if (msg.type === "ai" && msg.id) {
                    const content = typeof msg.content === "string" ? msg.content : "";
                    if (content) {
                      chunks[msg.id] = chunks[msg.id] || [];
                      chunks[msg.id].push(content);
                      lastId = msg.id;
                    }
                  }
                }
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }

        // Join all chunks for the last message
        return chunks[lastId] ? chunks[lastId].join("") : "";
      },
    };
  }

  /**
   * Get the runs API client
   */
  get runs() {
    return {
      /**
       * List runs for a thread
       */
      list: async (threadId: string): Promise<Run[]> => {
        return this.http.get<Run[]>(`/api/threads/${threadId}/runs`);
      },

      /**
       * Get a run by ID
       */
      get: async (threadId: string, runId: string): Promise<Run> => {
        return this.http.get<Run>(`/api/threads/${threadId}/runs/${runId}`);
      },

      /**
       * Cancel a run
       */
      cancel: async (threadId: string, runId: string): Promise<void> => {
        await this.http.post(`/api/threads/${threadId}/runs/${runId}/cancel`);
      },

      /**
       * Get run messages
       */
      getMessages: async (threadId: string, runId: string, beforeSeq?: number): Promise<{ data: Message[]; has_more: boolean }> => {
        return this.http.get<{ data: Message[]; has_more: boolean }>(
          `/api/threads/${threadId}/runs/${runId}/messages`,
          beforeSeq ? { before_seq: String(beforeSeq) } : undefined,
        );
      },
    };
  }

  /**
   * Get the uploads API client
   */
  get uploads() {
    return {
      /**
       * Upload files to a thread
       */
      upload: async (threadId: string, files: File[]): Promise<UploadResponse> => {
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }

        return this.http.upload<UploadResponse>(`/api/threads/${threadId}/uploads`, formData);
      },

      /**
       * List uploaded files for a thread
       */
      list: async (threadId: string): Promise<UploadFile[]> => {
        return this.http.get<{ files: UploadFile[] }>(`/api/threads/${threadId}/uploads/list`).then((r) => r.files);
      },

      /**
       * Delete an uploaded file
       */
      delete: async (threadId: string, filename: string): Promise<void> => {
        await this.http.delete(`/api/threads/${threadId}/uploads/${encodeURIComponent(filename)}`);
      },
    };
  }

  /**
   * Get the artifacts API client
   */
  get artifacts() {
    return {
      /**
       * Get an artifact by path
       */
      get: async (threadId: string, artifactPath: string): Promise<Blob> => {
        return this.http.download(`/api/threads/${threadId}/artifacts/${artifactPath}`);
      },

      /**
       * Download an artifact
       */
      download: async (threadId: string, artifactPath: string, filename?: string): Promise<void> => {
        const blob = await (this as unknown as { get: (threadId: string, artifactPath: string) => Promise<Blob> }).get(threadId, artifactPath);
        // @ts-ignore - browser API
        const url = URL.createObjectURL(blob);
        // @ts-ignore - browser API
        const a = document.createElement("a");
        a.href = url;
        a.download = filename || artifactPath.split("/").pop() || "artifact";
        // @ts-ignore - browser API
        document.body.appendChild(a);
        a.click();
        // @ts-ignore - browser API
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      },
    };
  }

  /**
   * Get the models API client
   */
  get models() {
    return {
      /**
       * List available models
       */
      list: async (): Promise<Model[]> => {
        return this.http.get<{ models: Model[] }>("/api/models").then((r) => r.models);
      },

      /**
       * Get a model by name
       */
      get: async (name: string): Promise<Model> => {
        return this.http.get<Model>(`/api/models/${name}`);
      },
    };
  }

  /**
   * Get the memory API client
   */
  get memory() {
    return {
      /**
       * Get memory data
       */
      get: async (): Promise<MemoryData> => {
        return this.http.get<MemoryData>("/api/memory");
      },

      /**
       * Reload memory
       */
      reload: async (): Promise<void> => {
        await this.http.post("/api/memory/reload");
      },

      /**
       * Get memory config
       */
      getConfig: async (): Promise<Record<string, unknown>> => {
        return this.http.get<Record<string, unknown>>("/api/memory/config");
      },
    };
  }

  /**
   * Get the MCP API client
   */
  get mcp() {
    return {
      /**
       * Get MCP config
       */
      getConfig: async (): Promise<{ mcp_servers: Record<string, MCPServer> }> => {
        return this.http.get<{ mcp_servers: Record<string, MCPServer> }>("/api/mcp/config");
      },

      /**
       * Update MCP config
       */
      updateConfig: async (servers: Record<string, MCPServer>): Promise<void> => {
        await this.http.put("/api/mcp/config", { mcp_servers: servers });
      },
    };
  }

  /**
   * Get the skills API client
   */
  get skills() {
    return {
      /**
       * List available skills
       */
      list: async (): Promise<Skill[]> => {
        return this.http.get<{ skills: Skill[] }>("/api/skills").then((r) => r.skills);
      },

      /**
       * Get a skill by name
       */
      get: async (name: string): Promise<Skill> => {
        return this.http.get<Skill>(`/api/skills/${name}`);
      },

      /**
       * Update skill enabled state
       */
      update: async (name: string, enabled: boolean): Promise<void> => {
        await this.http.put(`/api/skills/${name}`, { enabled });
      },

      /**
       * Install a skill from a .skill archive
       */
      install: async (formData: FormData): Promise<Skill> => {
        return this.http.upload<Skill>("/api/skills/install", formData);
      },
    };
  }

  /**
   * Get the feedback API client
   */
  get feedback() {
    return {
      /**
       * Create feedback for a run
       */
      create: async (threadId: string, runId: string, feedback: { key: string; score: number; comment?: string }): Promise<Feedback> => {
        return this.http.post<Feedback>(`/api/threads/${threadId}/runs/${runId}/feedback`, feedback);
      },

      /**
       * Get feedback for a run
       */
      list: async (threadId: string, runId: string): Promise<Feedback[]> => {
        return this.http.get<Feedback[]>(`/api/threads/${threadId}/runs/${runId}/feedback`);
      },

      /**
       * Delete feedback
       */
      delete: async (threadId: string, runId: string, feedbackId: string): Promise<void> => {
        await this.http.delete(`/api/threads/${threadId}/runs/${runId}/feedback/${feedbackId}`);
      },
    };
  }

  /**
   * Get token usage for a thread
   */
  getTokenUsage = async (threadId: string): Promise<{
    thread_id: string;
    total_tokens: number;
    total_input_tokens: number;
    total_output_tokens: number;
    total_runs: number;
    by_model: Record<string, { tokens: number; runs: number }>;
    by_caller: { lead_agent: number; subagent: number; middleware: number };
  }> => {
    return this.http.get(`/api/threads/${threadId}/token-usage`);
  };
}

// Re-export for the stream method
const clientPlaceholder = {
  baseUrl: "",
  http: {
    getDefaultHeaders: () => ({}),
  },
};
const client = clientPlaceholder as unknown as DeerFlowClient;
