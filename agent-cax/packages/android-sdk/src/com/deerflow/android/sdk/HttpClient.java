package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;
import com.deerflow.android.sdk.utils.JsonUtils;

import okhttp3.*;
import okhttp3.MediaType;
import okhttp3.RequestBody;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/**
 * HTTP Client for DeerFlow API using OkHttp
 */
public class HttpClient {

    private final OkHttpClient client;
    private final String baseUrl;
    private final String authToken;
    private final String userId;

    public HttpClient(ClientConfig config) {
        this.baseUrl = config.getBaseUrl().replaceAll("/$", "");
        this.authToken = config.getAuthToken();
        this.userId = config.getUserId();

        this.client = new OkHttpClient.Builder()
                .connectTimeout(config.getTimeout(), TimeUnit.MILLISECONDS)
                .readTimeout(config.getTimeout(), TimeUnit.MILLISECONDS)
                .writeTimeout(config.getTimeout(), TimeUnit.MILLISECONDS)
                .build();
    }

    /**
     * Get default headers for requests
     */
    private Headers getDefaultHeaders() {
        Headers.Builder builder = new Headers.Builder()
                .add("Content-Type", "application/json");
        if (authToken != null) {
            builder.add("Authorization", "Bearer " + authToken);
        }
        return builder.build();
    }

    /**
     * Get auth headers for state-changing requests
     */
    private Headers getAuthHeaders() {
        Headers.Builder builder = new Headers.Builder();
        builder.add("Content-Type", "application/json");
        if (authToken != null) {
            builder.add("Authorization", "Bearer " + authToken);
            builder.add("X-Internal-Auth", authToken);
        }
        return builder.build();
    }

    /**
     * Handle response and throw exception on error
     */
    private <T> T handleResponse(Response response, Class<T> clazz) throws Exception {
        if (!response.isSuccessful()) {
            String errorBody = response.body() != null ? response.body().string() : "";
            String message = errorBody.isEmpty() ? "HTTP " + response.code() : errorBody;

            switch (response.code()) {
                case 401:
                    throw new AuthenticationException(message);
                case 404:
                    throw new NotFoundException(message);
                default:
                    throw new DeerFlowException(message, null, response.code());
            }
        }

        String body = response.body() != null ? response.body().string() : "";
        if (clazz == String.class) {
            return clazz.cast(body);
        }
        return JsonUtils.fromJson(body, clazz);
    }

    /**
     * GET request
     */
    public <T> T get(String path, Map<String, Object> params, Class<T> clazz) throws Exception {
        String url = buildUrl(path, params);
        Request request = new Request.Builder()
                .url(url)
                .get()
                .headers(getDefaultHeaders())
                .build();

        try (Response response = client.newCall(request).execute()) {
            return handleResponse(response, clazz);
        }
    }

    /**
     * POST request
     */
    public <T> T post(String path, Object body, Class<T> clazz) throws Exception {
        String jsonBody = body != null ? JsonUtils.toJson(body) : "{}";
        RequestBody requestBody = RequestBody.create(jsonBody, MediaType.parse("application/json"));

        Request request = new Request.Builder()
                .url(baseUrl + path)
                .post(requestBody)
                .headers(getAuthHeaders())
                .build();

        try (Response response = client.newCall(request).execute()) {
            return handleResponse(response, clazz);
        }
    }

    /**
     * PUT request
     */
    public <T> T put(String path, Object body, Class<T> clazz) throws Exception {
        String jsonBody = body != null ? JsonUtils.toJson(body) : "{}";
        RequestBody requestBody = RequestBody.create(jsonBody, MediaType.parse("application/json"));

        Request request = new Request.Builder()
                .url(baseUrl + path)
                .put(requestBody)
                .headers(getAuthHeaders())
                .build();

        try (Response response = client.newCall(request).execute()) {
            return handleResponse(response, clazz);
        }
    }

    /**
     * DELETE request
     */
    public <T> T delete(String path, Class<T> clazz) throws Exception {
        Request request = new Request.Builder()
                .url(baseUrl + path)
                .delete()
                .headers(getAuthHeaders())
                .build();

        try (Response response = client.newCall(request).execute()) {
            return handleResponse(response, clazz);
        }
    }

    /**
     * Upload file
     */
    public <T> T upload(String path, File file, Class<T> clazz) throws Exception {
        RequestBody fileBody = RequestBody.create(file, MediaType.parse("application/octet-stream"));
        RequestBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("files", file.getName(), fileBody)
                .build();

        Request.Builder requestBuilder = new Request.Builder()
                .url(baseUrl + path)
                .post(requestBody);

        if (authToken != null) {
            requestBuilder.addHeader("Authorization", "Bearer " + authToken);
        }

        try (Response response = client.newCall(requestBuilder.build()).execute()) {
            return handleResponse(response, clazz);
        }
    }

    /**
     * Download file as bytes
     */
    public byte[] download(String path) throws Exception {
        Request request = new Request.Builder()
                .url(baseUrl + path)
                .get()
                .headers(getDefaultHeaders())
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new DeerFlowException("Download failed: " + response.code(), null, response.code());
            }
            byte[] bytes = response.body() != null ? response.body().bytes() : new byte[0];
            if (bytes.length == 0) {
                throw new IOException("Empty response");
            }
            return bytes;
        }
    }

    /**
     * Stream request with callback
     */
    public void stream(String path, Object body, BiConsumer<String, String> onEvent) throws Exception {
        String jsonBody = body != null ? JsonUtils.toJson(body) : "{}";
        RequestBody requestBody = RequestBody.create(jsonBody, MediaType.parse("application/json"));

        Request request = new Request.Builder()
                .url(baseUrl + path)
                .post(requestBody)
                .headers(getAuthHeaders())
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new DeerFlowException("Stream request failed: " + response.code(), null, response.code());
            }

            if (response.body() == null) {
                throw new IOException("Empty response body");
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(response.body().byteStream()))) {
                String currentEvent = "";
                String line;

                while ((line = reader.readLine()) != null) {
                    if (line.startsWith("event: ")) {
                        currentEvent = line.substring(7).trim();
                    } else if (line.startsWith("data: ")) {
                        String data = line.substring(6);
                        onEvent.accept(currentEvent, data);
                    }
                }
            }
        }
    }

    /**
     * Build URL with query parameters
     */
    private String buildUrl(String path, Map<String, Object> params) {
        StringBuilder urlBuilder = new StringBuilder(baseUrl + path);
        if (params != null && !params.isEmpty()) {
            List<String> pairs = new ArrayList<>();
            for (Map.Entry<String, Object> entry : params.entrySet()) {
                if (entry.getValue() != null) {
                    try {
                        String encoded = java.net.URLEncoder.encode(entry.getValue().toString(), "UTF-8");
                        pairs.add(entry.getKey() + "=" + encoded);
                    } catch (Exception e) {
                        pairs.add(entry.getKey() + "=" + entry.getValue());
                    }
                }
            }
            if (!pairs.isEmpty()) {
                urlBuilder.append("?").append(String.join("&", pairs));
            }
        }
        return urlBuilder.toString();
    }

    /**
     * Get base URL
     */
    public String getBaseUrl() {
        return baseUrl;
    }
}
