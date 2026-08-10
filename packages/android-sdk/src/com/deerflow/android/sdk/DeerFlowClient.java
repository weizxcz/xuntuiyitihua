package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.List;
import java.util.Map;

/**
 * DeerFlow Java SDK Client
 *
 * @example
 * <pre>{@code
 * DeerFlowClient client = new DeerFlowClient(
 *     new ClientConfig("http://localhost:8001")
 * );
 *
 * // Create a new thread
 * Thread thread = client.getThreads().create();
 *
 * // Send a message
 * String response = client.getThreads().chat(
 *     thread.getThreadId(),
 *     List.of(new Message(MessageType.HUMAN, "Hello!"))
 * );
 * }</pre>
 */
public class DeerFlowClient {

    private final HttpClient httpClient;
    private final ThreadsApi threads;
    private final RunsApi runs;
    private final UploadsApi uploads;
    private final ModelsApi models;
    private final MemoryApi memory;
    private final McpApi mcp;
    private final SkillsApi skills;
    private final FeedbackApi feedback;
    private final ArtifactsApi artifacts;

    public DeerFlowClient(ClientConfig config) {
        this.httpClient = new HttpClient(config);
        this.threads = new ThreadsApi(this.httpClient);
        this.runs = new RunsApi(this.httpClient);
        this.uploads = new UploadsApi(this.httpClient);
        this.models = new ModelsApi(this.httpClient);
        this.memory = new MemoryApi(this.httpClient);
        this.mcp = new McpApi(this.httpClient);
        this.skills = new SkillsApi(this.httpClient);
        this.feedback = new FeedbackApi(this.httpClient);
        this.artifacts = new ArtifactsApi(this.httpClient);
    }

    public ThreadsApi getThreads() {
        return threads;
    }

    public RunsApi getRuns() {
        return runs;
    }

    public UploadsApi getUploads() {
        return uploads;
    }

    public ModelsApi getModels() {
        return models;
    }

    public MemoryApi getMemory() {
        return memory;
    }

    public McpApi getMcp() {
        return mcp;
    }

    public SkillsApi getSkills() {
        return skills;
    }

    public FeedbackApi getFeedback() {
        return feedback;
    }

    public ArtifactsApi getArtifacts() {
        return artifacts;
    }

    /**
     * Get token usage for a thread
     */
    public TokenUsageResponse getTokenUsage(String threadId) throws Exception {
        return httpClient.get("/api/threads/" + threadId + "/token-usage", null, TokenUsageResponse.class);
    }
}
