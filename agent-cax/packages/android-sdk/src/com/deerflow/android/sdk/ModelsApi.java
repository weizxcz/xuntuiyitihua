package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * Models API
 */
public class ModelsApi {

    private final HttpClient httpClient;

    public ModelsApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * List available models
     */
    public List<Model> list() throws Exception {
        ModelListResponse response = httpClient.get("/api/models", null, ModelListResponse.class);
        return response != null ? response.getModels() : new ArrayList<>();
    }

    /**
     * Get a model by name
     */
    public Model get(String name) throws Exception {
        return httpClient.get("/api/models/" + name, null, Model.class);
    }
}
