package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.io.File;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.*;

/**
 * Uploads API
 */
public class UploadsApi {

    private final HttpClient httpClient;

    public UploadsApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * Upload files to a thread
     */
    public UploadResponse upload(String threadId, File file) throws Exception {
        return httpClient.upload("/api/threads/" + threadId + "/uploads", file, UploadResponse.class);
    }

    /**
     * List uploaded files for a thread
     */
    public List<UploadFile> list(String threadId) throws Exception {
        UploadListResponse response = httpClient.get(
            "/api/threads/" + threadId + "/uploads/list", null, UploadListResponse.class);
        return response != null ? response.getFiles() : new ArrayList<>();
    }

    /**
     * Delete an uploaded file
     */
    public void delete(String threadId, String filename) throws Exception {
        String encodedFilename = URLEncoder.encode(filename, StandardCharsets.UTF_8.name());
        httpClient.delete("/api/threads/" + threadId + "/uploads/" + encodedFilename, Void.class);
    }
}
