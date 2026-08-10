package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * Runs API
 */
public class RunsApi {

    private final HttpClient httpClient;

    public RunsApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * List runs for a thread
     */
    public List<Run> list(String threadId) throws Exception {
        @SuppressWarnings("unchecked")
        List<Run> result = (List<Run>) (Object) httpClient.get(
            "/api/threads/" + threadId + "/runs", null, Object.class);
        return result != null ? result : new ArrayList<>();
    }

    /**
     * Get a run by ID
     */
    public Run get(String threadId, String runId) throws Exception {
        return httpClient.get("/api/threads/" + threadId + "/runs/" + runId, null, Run.class);
    }

    /**
     * Cancel a run
     */
    public void cancel(String threadId, String runId) throws Exception {
        httpClient.post("/api/threads/" + threadId + "/runs/" + runId + "/cancel", null, Void.class);
    }

    /**
     * Get run messages
     */
    public RunMessagesResponse getMessages(String threadId, String runId, Long beforeSeq) throws Exception {
        Map<String, Object> params = new HashMap<>();
        params.put("before_seq", beforeSeq);
        return httpClient.get("/api/threads/" + threadId + "/runs/" + runId + "/messages",
                             params, RunMessagesResponse.class);
    }
}
