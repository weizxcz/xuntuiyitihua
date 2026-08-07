package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * Feedback API
 */
public class FeedbackApi {

    private final HttpClient httpClient;

    public FeedbackApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * Create feedback for a run
     */
    public Feedback create(String threadId, String runId, FeedbackCreateOptions options) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("key", options.getKey());
        body.put("score", options.getScore());
        body.put("comment", options.getComment());
        return httpClient.post("/api/threads/" + threadId + "/runs/" + runId + "/feedback", body, Feedback.class);
    }

    /**
     * Get feedback for a run
     */
    public List<Feedback> list(String threadId, String runId) throws Exception {
        @SuppressWarnings("unchecked")
        List<Feedback> result = (List<Feedback>) (Object) httpClient.get(
            "/api/threads/" + threadId + "/runs/" + runId + "/feedback", null, Object.class);
        return result != null ? result : new ArrayList<>();
    }

    /**
     * Delete feedback
     */
    public void delete(String threadId, String runId, String feedbackId) throws Exception {
        httpClient.delete("/api/threads/" + threadId + "/runs/" + runId + "/feedback/" + feedbackId, Void.class);
    }
}
