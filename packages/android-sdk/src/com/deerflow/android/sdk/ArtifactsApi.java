package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.io.IOException;

/**
 * Artifacts API
 */
public class ArtifactsApi {

    private final HttpClient httpClient;

    public ArtifactsApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * Get an artifact by path
     */
    public byte[] get(String threadId, String artifactPath) throws Exception {
        return httpClient.download("/api/threads/" + threadId + "/artifacts/" + artifactPath);
    }

    /**
     * Download an artifact
     */
    public void download(String threadId, String artifactPath, String filename) throws Exception {
        byte[] bytes = get(threadId, artifactPath);
        // Save file - implement based on your requirements
        // This is a placeholder
        if (bytes.length == 0) {
            throw new IOException("Empty artifact data");
        }
    }
}
