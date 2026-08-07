package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * Memory API
 */
public class MemoryApi {

    private final HttpClient httpClient;

    public MemoryApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * Get memory data
     */
    public MemoryData get() throws Exception {
        return httpClient.get("/api/memory", null, MemoryData.class);
    }

    /**
     * Reload memory
     */
    public void reload() throws Exception {
        httpClient.post("/api/memory/reload", null, Void.class);
    }

    /**
     * Get memory config
     */
    public Map<String, Object> getConfig() throws Exception {
        @SuppressWarnings("unchecked")
        Map<String, Object> result = (Map<String, Object>) (Object) httpClient.get(
            "/api/memory/config", null, Object.class);
        return result != null ? result : new HashMap<>();
    }
}
