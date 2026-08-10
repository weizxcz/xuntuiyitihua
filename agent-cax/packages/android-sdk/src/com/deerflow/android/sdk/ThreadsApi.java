package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;
import com.deerflow.android.sdk.utils.JsonUtils;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.*;
import java.util.function.BiConsumer;

/**
 * Threads API
 */
public class ThreadsApi {

    private final HttpClient httpClient;

    public ThreadsApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * Create a new thread
     */
    public Thread create(ThreadCreateOptions options) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("thread_id", options != null ? options.getThreadId() : null);
        body.put("assistant_id", options != null ? options.getAssistantId() : null);
        body.put("metadata", options != null ? options.getMetadata() : null);
        return httpClient.post("/api/threads", body, Thread.class);
    }

    /**
     * Create a new thread with no options
     */
    public Thread create() throws Exception {
        return create(null);
    }

    /**
     * Get a thread by ID
     */
    public Thread get(String threadId) throws Exception {
        return httpClient.get("/api/threads/" + threadId, null, Thread.class);
    }

    /**
     * Update a thread
     */
    public Thread update(String threadId, Map<String, Object> metadata) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("metadata", metadata);
        return httpClient.put("/api/threads/" + threadId, body, Thread.class);
    }

    /**
     * Delete a thread
     */
    public void delete(String threadId) throws Exception {
        httpClient.delete("/api/threads/" + threadId, Void.class);
    }

    /**
     * Search threads
     */
    public List<Thread> search(ThreadSearchOptions options) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("metadata", options != null ? options.getMetadata() : null);
        body.put("limit", options != null ? options.getLimit() : null);
        body.put("offset", options != null ? options.getOffset() : null);
        body.put("status", options != null ? options.getStatus() : null);
        body.put("sort_by", options != null ? options.getSortBy() : null);
        body.put("sort_order", options != null ? options.getSortOrder() : null);

        @SuppressWarnings("unchecked")
        List<Thread> result = (List<Thread>) (Object) httpClient.post("/api/threads/search", body, Object.class);
        return result != null ? result : new ArrayList<>();
    }

    /**
     * Update thread state
     */
    public void updateState(String threadId, Map<String, Object> state) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("values", state);
        httpClient.post("/api/threads/" + threadId + "/state", body, Void.class);
    }

    /**
     * Get thread state
     */
    public ThreadState getState(String threadId) throws Exception {
        return httpClient.get("/api/threads/" + threadId + "/state", null, ThreadState.class);
    }

    /**
     * Get thread history
     */
    public List<ThreadState> getHistory(String threadId, Integer limit) throws Exception {
        Map<String, Object> params = new HashMap<>();
        params.put("limit", limit);
        @SuppressWarnings("unchecked")
        List<ThreadState> result = (List<ThreadState>) (Object) httpClient.get(
            "/api/threads/" + threadId + "/history", params, Object.class);
        return result != null ? result : new ArrayList<>();
    }

    /**
     * Stream a thread run
     */
    public void stream(String threadId, List<Message> messages,
                       List<StreamMode> streamModes, BiConsumer<String, Object> onEvent) throws Exception {
        List<String> modeStrings = new ArrayList<>();
        if (streamModes != null) {
            for (StreamMode mode : streamModes) {
                modeStrings.add(mode.name().toLowerCase().replace("_", "-"));
            }
        } else {
            modeStrings.add("values");
            modeStrings.add("messages");
            modeStrings.add("custom");
        }

        Map<String, Object> body = new HashMap<>();
        Map<String, Object> input = new HashMap<>();
        input.put("messages", messages);
        body.put("input", input);
        body.put("context", Collections.singletonMap("thread_id", threadId));
        body.put("stream_mode", modeStrings);

        httpClient.stream("/api/threads/" + threadId + "/runs/stream", body, onEvent);
    }

    /**
     * Stream a thread run with default stream modes
     */
    public void stream(String threadId, List<Message> messages, BiConsumer<String, Object> onEvent) throws Exception {
        stream(threadId, messages, null, onEvent);
    }

    /**
     * Run a thread and wait for completion
     */
    public ThreadState runAndWait(String threadId, List<Message> messages) throws Exception {
        Map<String, Object> body = new HashMap<>();
        Map<String, Object> input = new HashMap<>();
        input.put("messages", messages);
        body.put("input", input);
        return httpClient.post("/api/threads/" + threadId + "/runs/wait", body, ThreadState.class);
    }

    /**
     * Regenerate from a specific message
     */
    public void regenerate(String threadId, String messageId) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("message_id", messageId);
        httpClient.post("/api/threads/" + threadId + "/runs/regenerate/prepare", body, Void.class);
    }

    /**
     * Send a message and get the full response (non-streaming)
     */
    public String chat(String threadId, List<Message> messages) throws Exception {
        final StringBuilder result = new StringBuilder();
        final String[] lastId = {""};

        stream(threadId, messages, (event, data) -> {
            try {
                if ("messages-tuple".equals(event)) {
                    JSONObject json = new JSONObject(data.toString());
                    if (json.has("data")) {
                        JSONObject dataObj = json.getJSONObject("data");
                        String content = dataObj.optString("content", "");
                        String id = dataObj.optString("id", "");
                        if (!content.isEmpty() && !id.isEmpty()) {
                            result.append(content);
                            lastId[0] = id;
                        }
                    }
                }
            } catch (Exception e) {
                // Skip invalid JSON
            }
        });

        return result.toString();
    }
}
