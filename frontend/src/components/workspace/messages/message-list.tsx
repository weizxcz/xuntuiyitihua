import type { Message } from "@langchain/langgraph-sdk";
import type { BaseStream } from "@langchain/langgraph-sdk/react";
import { ChevronUpIcon, Loader2Icon, RefreshCcwIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useArtifacts } from "@/components/workspace/artifacts/context";
import {
  Conversation,
  ConversationContent,
} from "@/components/ai-elements/conversation";
import {
  Reasoning,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getCadScriptMcpBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import {
  buildTokenDebugSteps,
  type TokenUsageInlineMode,
} from "@/core/messages/usage-model";
import {
  extractContentFromMessage,
  extractExecScriptFromMessage,
  extractPresentFilesFromMessage,
  extractTextFromMessage,
  getAssistantTurnCopyData,
  getAssistantTurnUsageMessages,
  getMessageGroups,
  getStreamingMessageLookup,
  hasContent,
  hasExecScript,
  hasPresentFiles,
  hasPresentModel,
  hasReasoning,
  isAssistantMessageGroupStreaming,
} from "@/core/messages/utils";
import { useRehypeSplitWordsIntoSpans } from "@/core/rehype";
import type { Subtask } from "@/core/tasks";
import { useUpdateSubtask } from "@/core/tasks/context";
import {
  derivePendingSubtaskStatus,
  parseSubtaskResult,
} from "@/core/tasks/subtask-result";
import type { AgentThreadState } from "@/core/threads";
import { cn } from "@/lib/utils";

import { ArtifactFileList } from "../artifacts/artifact-file-list";
import { ModelViewerPanel } from "../artifacts/model-viewer";
import { CopyButton } from "../copy-button";
import { StreamingIndicator } from "../streaming-indicator";
import { Tooltip } from "../tooltip";

import { MarkdownContent } from "./markdown-content";
import { MessageGroup } from "./message-group";
import { MessageListItem } from "./message-list-item";
import {
  MessageTokenUsageDebugList,
  MessageTokenUsageList,
} from "./message-token-usage";
import { MessageListSkeleton } from "./skeleton";
import { SubtaskCard } from "./subtask-card";

export const MESSAGE_LIST_DEFAULT_PADDING_BOTTOM = 24;

const LOAD_MORE_HISTORY_THROTTLE_MS = 1200;

function LoadMoreHistoryIndicator({
  isLoading,
  hasMore,
  loadMore,
}: {
  isLoading?: boolean;
  hasMore?: boolean;
  loadMore?: () => void;
}) {
  const { t } = useI18n();
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastLoadRef = useRef(0);

  const throttledLoadMore = useCallback(() => {
    if (!hasMore || isLoading) {
      return;
    }

    const now = Date.now();
    const remaining =
      LOAD_MORE_HISTORY_THROTTLE_MS - (now - lastLoadRef.current);

    if (remaining <= 0) {
      lastLoadRef.current = now;
      loadMore?.();
      return;
    }

    if (timeoutRef.current) {
      return;
    }

    timeoutRef.current = setTimeout(() => {
      timeoutRef.current = null;
      if (!hasMore || isLoading) {
        return;
      }
      lastLoadRef.current = Date.now();
      loadMore?.();
    }, remaining);
  }, [hasMore, isLoading, loadMore]);

  useEffect(() => {
    const element = sentinelRef.current;
    if (!element || !hasMore) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          throttledLoadMore();
        }
      },
      {
        rootMargin: "120px 0px 0px 0px",
      },
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [hasMore, throttledLoadMore]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  if (!hasMore && !isLoading) {
    return null;
  }

  return (
    <div ref={sentinelRef} className="flex w-full justify-center">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-muted-foreground hover:text-foreground rounded-full px-3"
        disabled={(isLoading ?? false) || !hasMore}
        onClick={throttledLoadMore}
      >
        {isLoading ? (
          <>
            <Loader2Icon className="mr-2 size-4 animate-spin" />
            {t.common.loading}
          </>
        ) : (
          <>
            <ChevronUpIcon className="mr-2 size-4" />
            {t.common.loadMore}
          </>
        )}
      </Button>
    </div>
  );
}

export function MessageList({
  className,
  threadId,
  thread,
  paddingBottom = MESSAGE_LIST_DEFAULT_PADDING_BOTTOM,
  tokenUsageInlineMode = "off",
  hasMoreHistory,
  loadMoreHistory,
  isHistoryLoading,
  onRegenerateMessage,
  canRegenerate = false,
}: {
  className?: string;
  threadId: string;
  thread: BaseStream<AgentThreadState>;
  paddingBottom?: number;
  tokenUsageInlineMode?: TokenUsageInlineMode;
  hasMoreHistory?: boolean;
  loadMoreHistory?: () => void;
  isHistoryLoading?: boolean;
  onRegenerateMessage?: (
    messageId: string,
    supersededMessageIds: string[],
  ) => void | Promise<void>;
  canRegenerate?: boolean;
}) {
  const { t } = useI18n();
  const { autoOpen, autoSelect, select, setOpen } = useArtifacts();
  const [turnStartTime, setTurnStartTime] = useState<number | null>(null);
  const prevIsLoading = useRef(thread.isLoading);

  useEffect(() => {
    if (thread.isLoading && !prevIsLoading.current) {
      setTurnStartTime(Date.now());
    }
    prevIsLoading.current = thread.isLoading;
  }, [thread.isLoading]);
  const messages = thread.messages;
  const groupedMessages = getMessageGroups(messages);
  const [regeneratingMessageId, setRegeneratingMessageId] = useState<
    string | null
  >(null);
  const hasActiveAssistantText = useMemo(() => {
    let lastHumanIndex = -1;
    for (let i = groupedMessages.length - 1; i >= 0; i--) {
      if (groupedMessages[i]?.type === "human") {
        lastHumanIndex = i;
        break;
      }
    }
    if (lastHumanIndex === -1) return false;
    return groupedMessages
      .slice(lastHumanIndex)
      .some((g) => g.type === "assistant");
  }, [groupedMessages]);
  const rehypePlugins = useRehypeSplitWordsIntoSpans(thread.isLoading);
  const updateSubtask = useUpdateSubtask();
  const lastGroupIndex = groupedMessages.length - 1;
  const turnUsageMessagesByGroupIndex =
    getAssistantTurnUsageMessages(groupedMessages);
  const tokenDebugSteps = useMemo(
    () => buildTokenDebugSteps(messages, t),
    [messages, t],
  );
  const streamingMessages = useMemo(
    () =>
      getStreamingMessageLookup(
        messages,
        thread.isLoading,
        thread.getMessagesMetadata,
      ),
    [messages, thread.getMessagesMetadata, thread.isLoading],
  );

  const latestAssistantGroupId = useMemo(() => {
    if (thread.isLoading) {
      return null;
    }
    for (let i = groupedMessages.length - 1; i >= 0; i -= 1) {
      const group = groupedMessages[i];
      if (group?.type === "assistant") {
        return group.id;
      }
    }
    return null;
  }, [groupedMessages, thread.isLoading]);

  // Auto-open model file when present_model tool is called
  useEffect(() => {
    if (!thread.isLoading || !autoOpen || !autoSelect) {
      return;
    }
    // Find the last present-model group
    for (let i = groupedMessages.length - 1; i >= 0; i--) {
      const group = groupedMessages[i];
      if (group?.type === "assistant:present-model") {
        const aiMessage = group.messages[0];
        if (
          aiMessage?.type === "ai" &&
          aiMessage.tool_calls?.[0]?.args?.filepath
        ) {
          const filepath = aiMessage.tool_calls[0].args.filepath as string;
          setTimeout(() => {
            select(filepath, true);
            setOpen(true);
          }, 100);
        }
        break;
      }
    }
  }, [thread.isLoading, groupedMessages, autoOpen, autoSelect, select, setOpen]);

  const renderAssistantActions = useCallback(
    (
      messages: Message[],
      isStreaming: boolean,
      enableRegenerateForTurn: boolean,
    ) => {
      const clipboardData = getAssistantTurnCopyData(messages, { isStreaming });
      const regenerateTarget = [...messages]
        .reverse()
        .find((message) => message.type === "ai" && message.id);
      const supersededMessageIds = messages
        .filter((message) => message.type === "ai" && message.id)
        .map((message) => message.id)
        .filter((id): id is string => typeof id === "string");

      if (!clipboardData && !regenerateTarget) {
        return null;
      }

      return (
        <div className="mt-2 flex justify-start gap-1 opacity-0 transition-opacity delay-200 duration-300 group-hover/assistant-turn:opacity-100">
          {clipboardData && <CopyButton clipboardData={clipboardData} />}
          {enableRegenerateForTurn &&
            regenerateTarget?.id &&
            onRegenerateMessage && (
              <Tooltip content={t.common.regenerate}>
                <Button
                  aria-label={t.common.regenerate}
                  size="icon-sm"
                  type="button"
                  variant="ghost"
                  disabled={
                    !canRegenerate ||
                    regeneratingMessageId === regenerateTarget.id
                  }
                  onClick={() => {
                    const targetId = regenerateTarget.id;
                    if (!targetId) {
                      return;
                    }
                    setRegeneratingMessageId(targetId);
                    void Promise.resolve(
                      onRegenerateMessage?.(targetId, supersededMessageIds),
                    ).finally(() => {
                      setRegeneratingMessageId(null);
                    });
                  }}
                >
                  <RefreshCcwIcon
                    className={cn(
                      "size-3",
                      regeneratingMessageId === regenerateTarget.id &&
                        "animate-spin",
                    )}
                  />
                </Button>
              </Tooltip>
            )}
        </div>
      );
    },
    [
      canRegenerate,
      onRegenerateMessage,
      regeneratingMessageId,
      t.common.regenerate,
    ],
  );

  const renderTokenUsage = useCallback(
    ({
      messages,
      turnUsageMessages,
      inlineDebug = true,
      debugMessageIds,
    }: {
      messages: Message[];
      turnUsageMessages?: Message[] | null;
      inlineDebug?: boolean;
      debugMessageIds?: string[];
    }) => {
      if (tokenUsageInlineMode === "per_turn") {
        return (
          <MessageTokenUsageList
            enabled={true}
            isLoading={thread.isLoading}
            messages={turnUsageMessages ?? []}
          />
        );
      }

      if (tokenUsageInlineMode === "step_debug" && inlineDebug) {
        const messageIds = new Set(
          debugMessageIds ??
            messages
              .filter((message) => message.type === "ai")
              .map((message) => message.id)
              .filter((id): id is string => typeof id === "string"),
        );
        return (
          <MessageTokenUsageDebugList
            enabled={true}
            isLoading={thread.isLoading}
            steps={tokenDebugSteps.filter((step) =>
              messageIds.has(step.messageId),
            )}
          />
        );
      }

      return null;
    },
    [thread.isLoading, tokenDebugSteps, tokenUsageInlineMode],
  );

  if (thread.isThreadLoading && messages.length === 0) {
    return <MessageListSkeleton />;
  }

  return (
    <Conversation
      className={cn("flex size-full flex-col justify-center", className)}
    >
      <ConversationContent className="mx-auto w-full max-w-(--container-width-md) gap-8 pt-8">
        <LoadMoreHistoryIndicator
          isLoading={isHistoryLoading}
          hasMore={hasMoreHistory}
          loadMore={loadMoreHistory}
        />
        {groupedMessages.map((group, groupIndex) => {
          const turnUsageMessages = turnUsageMessagesByGroupIndex[groupIndex];
          const groupIsLoading =
            thread.isLoading && groupIndex === lastGroupIndex;

          if (group.type === "human" || group.type === "assistant") {
            return (
              <div
                key={group.id}
                className={cn(
                  "w-full",
                  group.type === "assistant" && "group/assistant-turn",
                )}
              >
                {group.messages.map((msg) => {
                  return (
                    <MessageListItem
                      key={`${group.id}/${msg.id}`}
                      message={msg}
                      isLoading={
                        thread.isLoading &&
                        groupIndex === groupedMessages.length - 1
                      }
                      threadId={threadId}
                      showCopyButton={group.type !== "assistant"}
                      turnStartTime={
                        groupIndex === groupedMessages.length - 1
                          ? turnStartTime
                          : null
                      }
                    />
                  );
                })}
                {renderTokenUsage({
                  messages: group.messages,
                  turnUsageMessages,
                })}
                {group.type === "assistant" &&
                  renderAssistantActions(
                    group.messages,
                    isAssistantMessageGroupStreaming(
                      group.messages,
                      streamingMessages,
                    ),
                    group.id === latestAssistantGroupId,
                  )}
              </div>
            );
          } else if (group.type === "assistant:clarification") {
            const message = group.messages[0];
            if (message && hasContent(message)) {
              return (
                <div key={group.id} className="w-full">
                  <MarkdownContent
                    content={extractContentFromMessage(message)}
                    isLoading={thread.isLoading}
                    rehypePlugins={rehypePlugins}
                  />
                  {renderTokenUsage({
                    messages: group.messages,
                    turnUsageMessages,
                  })}
                </div>
              );
            }
            return null;
          } else if (group.type === "assistant:present-files") {
            const files: string[] = [];
            for (const message of group.messages) {
              if (hasPresentFiles(message)) {
                const presentFiles = extractPresentFilesFromMessage(message);
                files.push(...presentFiles);
              }
            }
            return (
              <div className="w-full" key={group.id}>
                {group.messages[0] && hasContent(group.messages[0]) && (
                  <MarkdownContent
                    content={extractContentFromMessage(group.messages[0])}
                    isLoading={thread.isLoading}
                    rehypePlugins={rehypePlugins}
                    className="mb-4"
                  />
                )}
                <ArtifactFileList files={files} threadId={threadId} />
                {renderTokenUsage({
                  messages: group.messages,
                  turnUsageMessages,
                })}
              </div>
            );
          } else if (group.type === "assistant:present-model") {
            const models: string[] = [];
            for (const message of group.messages) {
              if (hasPresentModel(message) && message.type === "ai") {
                const filepath = message.tool_calls?.[0]?.args?.filepath;
                if (filepath) {
                  models.push(filepath as string);
                }
              }
            }
            return (
              <div className="w-full" key={group.id}>
                {group.messages[0] && hasContent(group.messages[0]) && (
                  <MarkdownContent
                    content={extractContentFromMessage(group.messages[0])}
                    isLoading={thread.isLoading}
                    rehypePlugins={rehypePlugins}
                    className="mb-4"
                  />
                )}
                <ArtifactFileList files={models} threadId={threadId} isModel={true} />
                {renderTokenUsage({
                  messages: group.messages,
                  turnUsageMessages,
                })}
              </div>
            );
          } else if (group.type === "assistant:exec-script") {
            const firstMessage = group.messages[0];
            const execScriptInfo = firstMessage ? extractExecScriptFromMessage(firstMessage) : null;
            if (!execScriptInfo) return null;

            // 获取 exec_script 工具调用的 tool_call_id 作为唯一标识
            const toolCallId = firstMessage?.tool_calls?.find((tc) => tc.name === "exec_script")?.id;

            return (
              <div className="w-full" key={group.id}>
                {firstMessage && hasContent(firstMessage) && (
                  <MarkdownContent
                    content={extractContentFromMessage(firstMessage)}
                    isLoading={thread.isLoading}
                    rehypePlugins={rehypePlugins}
                    className="mb-4"
                  />
                )}
                <ExecScriptCard
                  threadId={threadId}
                  toolCallId={toolCallId}
                  script={execScriptInfo.script}
                  needYh={execScriptInfo.need_yh ?? true}
                />
                {renderTokenUsage({
                  messages: group.messages,
                  turnUsageMessages,
                })}
              </div>
            );
          } else if (group.type === "assistant:subagent") {
            const tasks = new Set<Subtask>();
            for (const message of group.messages) {
              if (message.type === "ai") {
                for (const toolCall of message.tool_calls ?? []) {
                  if (toolCall.name === "task") {
                    const taskId = toolCall.id;
                    if (!taskId) {
                      continue;
                    }
                    const status = derivePendingSubtaskStatus(
                      taskId,
                      group.messages,
                      groupIsLoading,
                    );
                    const task: Subtask = {
                      id: taskId,
                      subagent_type: toolCall.args.subagent_type,
                      description: toolCall.args.description,
                      prompt: toolCall.args.prompt,
                      status,
                      ...(status === "failed"
                        ? { error: t.subtasks.failed }
                        : {}),
                    };
                    updateSubtask(task);
                    tasks.add(task);
                  }
                }
              } else if (message.type === "tool") {
                const taskId = message.tool_call_id;
                if (taskId) {
                  const parsed = parseSubtaskResult(
                    extractTextFromMessage(message),
                    message.additional_kwargs,
                  );
                  updateSubtask({ id: taskId, ...parsed });
                }
              }
            }

            const results: React.ReactNode[] = [];
            const subagentDebugMessageIds: string[] = [];
            if (tasks.size > 0) {
              results.push(
                <div
                  key="subtask-count"
                  className="text-muted-foreground pt-2 text-sm font-normal"
                >
                  {t.subtasks.executing(tasks.size)}
                </div>,
              );
            }
            for (const message of group.messages.filter(
              (message) => message.type === "ai",
            )) {
              if (hasReasoning(message)) {
                results.push(
                  <MessageGroup
                    key={"thinking-group-" + message.id}
                    messages={[message]}
                    isLoading={groupIsLoading}
                    tokenDebugSteps={tokenDebugSteps.filter(
                      (step) => step.messageId === message.id,
                    )}
                    showTokenDebugSummaries={
                      tokenUsageInlineMode === "step_debug"
                    }
                  />,
                );
              } else if (message.id) {
                subagentDebugMessageIds.push(message.id);
              }
              const taskIds = message.tool_calls?.flatMap((toolCall) =>
                toolCall.name === "task" && toolCall.id ? [toolCall.id] : [],
              );
              for (const taskId of taskIds ?? []) {
                results.push(
                  <SubtaskCard
                    key={"task-group-" + taskId}
                    taskId={taskId}
                    isLoading={groupIsLoading}
                  />,
                );
              }
            }
            return (
              <div
                key={"subtask-group-" + group.id}
                className="relative z-1 flex flex-col gap-2"
              >
                {results}
                {renderTokenUsage({
                  messages: group.messages,
                  turnUsageMessages,
                  debugMessageIds: subagentDebugMessageIds,
                })}
              </div>
            );
          }
          return (
            <div key={"group-" + group.id} className="w-full">
              <MessageGroup
                messages={group.messages}
                isLoading={thread.isLoading}
                tokenDebugSteps={tokenDebugSteps.filter((step) =>
                  group.messages.some(
                    (message) => message.id === step.messageId,
                  ),
                )}
                showTokenDebugSummaries={tokenUsageInlineMode === "step_debug"}
              />
              {renderTokenUsage({
                messages: group.messages,
                turnUsageMessages,
                inlineDebug: false,
              })}
            </div>
          );
        })}
        {thread.isLoading && !hasActiveAssistantText && (
          <div className="w-full">
            <Reasoning isStreaming={true} startTimeProp={turnStartTime}>
              <ReasoningTrigger hasContent={false} />
            </Reasoning>
          </div>
        )}
        <div style={{ height: `${paddingBottom}px` }} />
      </ConversationContent>
    </Conversation>
  );
}

// 执行脚本卡片组件
function ExecScriptCard({
  threadId,
  toolCallId,
  script,
  needYh,
}: {
  threadId: string;
  toolCallId?: string;
  script: string;
  needYh: boolean;
}) {
  const { select: selectArtifact, setOpen: setArtifactsOpen, setArtifacts } = useArtifacts();
  const [status, setStatus] = useState<"idle" | "executing" | "success" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  // 使用唯一的虚拟文件路径来存储脚本代码
  const scriptArtifactPath = useMemo(() =>
    `script:${threadId}:${toolCallId ?? Date.now()}.py`,
    [threadId, toolCallId]
  );

  // 初始化脚本代码到 artifacts 系统
  useEffect(() => {
    // 将脚本代码作为一个虚拟 artifact 注册
    setArtifacts((prev = []) => {
      if (!prev.includes(scriptArtifactPath)) {
        // 将脚本内容存储到 sessionStorage 以便后续读取
        sessionStorage.setItem(scriptArtifactPath, script);
        return [...prev, scriptArtifactPath];
      }
      return prev;
    });
  }, [scriptArtifactPath, script, setArtifacts]);

  // 执行脚本并获取模型 URL
  const executeScript = useCallback(async () => {
    if (status === "executing" || status === "success") {
      return;
    }

    setStatus("executing");

    try {
      // 使用简化的直接 HTTP 接口，无需 MCP 协议
      const response = await fetch(`${getCadScriptMcpBaseURL()}/api/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scripts: [{
            script_type: needYh ? "modeling" : "sketch",
            script_content: script,
            should_execute: true
          }],
          model_path: `${threadId}/model.yha`,
          need_yh: needYh
        })
      });

      const result = await response.json();
      // 检查返回的 success 字段来判断执行结果
      if (result.success === false) {
        // 执行失败
        const errorMsg = result.error ?? "脚本执行失败";
        setError(errorMsg);
        setStatus("failed");

        // 自动将错误信息发送给大模型，让它帮助调试
        const feedbackMessage = `脚本执行失败，错误信息：${errorMsg}\n\n脚本内容：\n\`\`\`python\n${script}\n\`\`\`\n\n请检查脚本内容并尝试修复。`;

        // 使用 fetch 发送用户消息给大模型
        const chatResponse = await fetch(`/api/threads/${threadId}/runs/wait`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: [{
              type: "human",
              content: feedbackMessage
            }]
          })
        });

        // 不阻塞 UI，忽略发送失败的错误
        if (!chatResponse.ok) {
          console.error("Failed to send feedback to model:", await chatResponse.text());
        }
      } else if (result.file_url) {
        // 执行成功，直接选中 file_url 作为 artifact
        setFileUrl(result.file_url);
        selectArtifact(result.file_url, true);
        setArtifactsOpen(true);
        setStatus("success");
      } else {
        // 其他情况
        setError("脚本执行成功但未返回文件 URL");
        setStatus("failed");
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "执行失败";
      setError(errorMsg);
      setStatus("failed");

      // 执行失败时自动发送错误给大模型
      const feedbackMessage = `脚本执行失败，错误信息：${errorMsg}\n\n脚本内容：\n\`\`\`python\n${script}\n\`\`\`\n\n请检查并尝试修复。`;

      fetch(`/api/threads/${threadId}/runs/wait`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{
            type: "human",
            content: feedbackMessage
          }]
        })
      }).catch(() => {
        // 忽略发送失败
      });
    }
  }, [threadId, needYh, script, status, selectArtifact, setArtifactsOpen]);

  const handleExecuteClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    void executeScript();
  }, [executeScript]);

  const handleViewCodeClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    selectArtifact(scriptArtifactPath, true);
    setArtifactsOpen(true);
  }, [scriptArtifactPath, selectArtifact, setArtifactsOpen]);

  const handleCardClick = useCallback(() => {
    if (status === "success" && fileUrl) {
      selectArtifact(fileUrl, true);
      setArtifactsOpen(true);
    }
  }, [status, fileUrl, selectArtifact, setArtifactsOpen]);

  return (
    <Card className="cursor-pointer" onClick={handleCardClick}>
      <CardHeader className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 pr-2 pl-1">
        <div className="flex items-center gap-2">
          <CardTitle className="min-w-0 leading-tight">
            <div className="min-w-0">执行脚本</div>
          </CardTitle>
          <CardDescription className="text-xs">
            {status === "executing" && "正在执行..."}
            {status === "success" && "执行成功"}
            {status === "failed" && <span className="text-destructive">{error}</span>}
            {status === "idle" && "点击执行运行脚本"}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={handleViewCodeClick}
            title="在右侧打开代码"
          >
            查看代码
          </Button>
          <Button
            size="sm"
            variant={status === "success" ? "default" : "secondary"}
            onClick={handleExecuteClick}
            disabled={status === "executing" || status === "success"}
          >
            {status === "executing" ? (
              <Loader2Icon className="size-3 animate-spin" />
            ) : status === "success" ? (
              "已执行"
            ) : (
              "执行"
            )}
          </Button>
        </div>
      </CardHeader>
      <div className="px-4 pb-4">
        <ScrollArea className="h-[200px]">
          <pre className="text-xs bg-muted p-4 rounded-md overflow-auto whitespace-pre-wrap break-all">
            <code>{script}</code>
          </pre>
        </ScrollArea>
      </div>
    </Card>
  );
}
