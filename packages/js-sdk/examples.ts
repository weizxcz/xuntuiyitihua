/**
 * DeerFlow JS SDK Examples
 *
 * This file demonstrates various usage patterns of the DeerFlow JavaScript SDK.
 */

import { DeerFlowClient, Message } from "./src";

// ============================================================================
// Basic Usage
// ============================================================================

/**
 * Example 1: Basic chat with streaming
 */
async function basicChat() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // Create a new thread
  const thread = await client.threads.create();
  console.log("Created thread:", thread.thread_id);

  // Send a message and stream response
  for await (const event of client.threads.stream(thread.thread_id, {
    messages: [
      {
        type: "human" as const,
        content: "Hello, what can you do?",
      },
    ],
  })) {
    if (event.type === "messages-tuple") {
      for (const msg of event.data) {
        if (msg.type === "ai") {
          console.log("AI:", msg.content);
        }
      }
    }
  }
}

// ============================================================================
// Stateful Conversation
// ============================================================================

/**
 * Example 2: Multi-turn conversation
 */
async function multiTurnConversation() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // Create a thread once
  const thread = await client.threads.create();
  const threadId = thread.thread_id;

  // First message
  await streamMessage(threadId, "What is machine learning?");

  // Second message (context is preserved)
  await streamMessage(threadId, "Can you give me an example?");

  // Third message
  await streamMessage(threadId, "How is it different from deep learning?");
}

async function streamMessage(threadId: string, content: string) {
  const client = new DeerFlowClient({ baseUrl: "http://localhost:8001" });

  for await (const event of client.threads.stream(threadId, {
    messages: [{ type: "human" as const, content }],
  })) {
    if (event.type === "messages-tuple") {
      for (const msg of event.data) {
        if (msg.type === "ai" && typeof msg.content === "string") {
          process.stdout.write(msg.content);
        }
      }
    }
  }
  console.log();
}

// ============================================================================
// File Upload
// ============================================================================

/**
 * Example 3: Upload files and analyze
 */
async function uploadAndAnalyze() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  const thread = await client.threads.create();
  const threadId = thread.thread_id;

  // Upload a file (in Node.js, use fs.createReadStream)
  // In browser, use File API
  const files = [/* File objects */] as File[];

  if (files.length > 0) {
    const uploadResult = await client.uploads.upload(threadId, files);
    console.log("Uploaded files:", uploadResult.files);
  }

  // Send a message about the uploaded files
  for await (const event of client.threads.stream(threadId, {
    messages: [
      {
        type: "human" as const,
        content: "Please analyze the uploaded document.",
      },
    ],
  })) {
    if (event.type === "messages-tuple") {
      for (const msg of event.data) {
        if (msg.type === "ai") {
          console.log("Analysis:", msg.content);
        }
      }
    }
  }
}

// ============================================================================
// Thread Management
// ============================================================================

/**
 * Example 4: List and manage threads
 */
async function manageThreads() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // Search threads
  const threads = await client.threads.search({
    limit: 10,
    sortBy: "updated_at",
    sortOrder: "desc",
  });

  console.log("Recent threads:");
  for (const thread of threads) {
    console.log(`- ${thread.thread_id}: ${thread.values.title || "Untitled"}`);
  }

  // Get thread details
  if (threads.length > 0) {
    const thread = await client.threads.get(threads[0].thread_id);
    console.log("Thread state:", thread.values);
  }

  // Delete a thread
  // await client.threads.delete(threadId);
}

// ============================================================================
// Models
// ============================================================================

/**
 * Example 5: List available models
 */
async function listModels() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  const models = await client.models.list();

  console.log("Available models:");
  for (const model of models) {
    console.log(`- ${model.display_name} (${model.name})`);
    console.log(`  Provider: ${model.provider}`);
    console.log(`  Supports thinking: ${model.supports_thinking}`);
    console.log(`  Supports vision: ${model.supports_vision}`);
  }
}

// ============================================================================
// Memory
// ============================================================================

/**
 * Example 6: Access user memory
 */
async function accessMemory() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // Get memory
  const memory = await client.memory.get();

  console.log("User context:", memory.userContext);
  console.log("Personal context:", memory.personalContext);
  console.log("Top of mind:", memory.topOfMind);
  console.log("Facts:");
  for (const fact of memory.facts) {
    console.log(`  - ${fact.content} (${fact.category})`);
  }

  // Reload memory (re-extract from conversations)
  await client.memory.reload();
}

// ============================================================================
// MCP Servers
// ============================================================================

/**
 * Example 7: Manage MCP servers
 */
async function manageMCP() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // Get MCP config
  const config = await client.mcp.getConfig();
  console.log("MCP Servers:", Object.keys(config.mcp_servers));

  // Update MCP config
  await client.mcp.updateConfig({
    ...config.mcp_servers,
    "new-server": {
      name: "new-server",
      enabled: true,
      type: "stdio",
      command: "node",
      args: ["server.js"],
    },
  });
}

// ============================================================================
// Skills
// ============================================================================

/**
 * Example 8: Manage skills
 */
async function manageSkills() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // List skills
  const skills = await client.skills.list();
  console.log("Available skills:");
  for (const skill of skills) {
    console.log(`- ${skill.name}: ${skill.description} (enabled: ${skill.enabled})`);
  }

  // Enable a skill
  await client.skills.update("my-skill", true);

  // Get skill details
  const skill = await client.skills.get("my-skill");
  console.log("Skill details:", skill);
}

// ============================================================================
// Feedback
// ============================================================================

/**
 * Example 9: Provide feedback on runs
 */
async function provideFeedback() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  const thread = await client.threads.create();
  const threadId = thread.thread_id;

  // Run a conversation
  const result = await client.threads.runAndWait(threadId, {
    messages: [{ type: "human" as const, content: "Hello!" }],
  });

  // Get runs to find the run_id
  const runs = await client.runs.list(threadId);
  if (runs.length > 0) {
    const runId = runs[0].run_id;

    // Provide feedback
    await client.feedback.create(threadId, runId, {
      key: "helpfulness",
      score: 1,
      comment: "Very helpful response!",
    });

    // List feedback
    const feedbacks = await client.feedback.list(threadId, runId);
    console.log("Feedback:", feedbacks);
  }
}

// ============================================================================
// Token Usage
// ============================================================================

/**
 * Example 10: Track token usage
 */
async function trackTokenUsage() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  const thread = await client.threads.create();
  const threadId = thread.thread_id;

  // Have a conversation
  await client.threads.runAndWait(threadId, {
    messages: [{ type: "human" as const, content: "Hello!" }],
  });

  // Get token usage
  const usage = await client.getTokenUsage(threadId);
  console.log("Token usage:");
  console.log(`  Total tokens: ${usage.total_tokens}`);
  console.log(`  Input tokens: ${usage.total_input_tokens}`);
  console.log(`  Output tokens: ${usage.total_output_tokens}`);
  console.log(`  Total runs: ${usage.total_runs}`);
  console.log("  By model:");
  for (const [model, stats] of Object.entries(usage.by_model)) {
    console.log(`    ${model}: ${stats.tokens} tokens in ${stats.runs} runs`);
  }
}

// ============================================================================
// Error Handling
// ============================================================================

/**
 * Example 11: Handle errors
 */
import {
  DeerFlowError,
  AuthenticationError,
  NotFoundError,
  NetworkError,
} from "./src";

async function handleError() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  try {
    // This might fail
    await client.threads.get("non-existent-thread-id");
  } catch (error) {
    if (error instanceof NotFoundError) {
      console.error("Thread not found:", error.message);
    } else if (error instanceof AuthenticationError) {
      console.error("Authentication failed:", error.message);
    } else if (error instanceof NetworkError) {
      console.error("Network error:", error.message);
    } else if (error instanceof DeerFlowError) {
      console.error("DeerFlow error:", error.message);
    } else {
      console.error("Unknown error:", error);
    }
  }
}

// ============================================================================
// Stateless Run (No Thread)
// ============================================================================

/**
 * Example 12: Stateless run without creating a thread
 */
async function statelessRun() {
  const client = new DeerFlowClient({
    baseUrl: "http://localhost:8001",
  });

  // Stream without thread (auto-creates temporary thread)
  const response = await fetch(`${client.baseUrl}/api/runs/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      input: {
        messages: [{ type: "human", content: "Hello!" }],
      },
      config: {
        configurable: {
          assistant_id: "lead_agent",
        },
      },
    }),
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    console.log(chunk);
  }
}

// ============================================================================
// Export examples for documentation
// ============================================================================

export {
  basicChat,
  multiTurnConversation,
  uploadAndAnalyze,
  manageThreads,
  listModels,
  accessMemory,
  manageMCP,
  manageSkills,
  provideFeedback,
  trackTokenUsage,
  handleError,
  statelessRun,
};
