package com.deerflow.android.sdk.models;

import java.util.List;
import java.util.Map;

/**
 * Client configuration
 */
public class ClientConfig {
    private final String baseUrl;
    private final String authToken;
    private final String userId;
    private final long timeout;

    public ClientConfig(String baseUrl) {
        this(baseUrl, null, null, 30000L);
    }

    public ClientConfig(String baseUrl, String authToken, String userId, long timeout) {
        this.baseUrl = baseUrl.replaceAll("/$", "");
        this.authToken = authToken;
        this.userId = userId;
        this.timeout = timeout;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public String getAuthToken() {
        return authToken;
    }

    public String getUserId() {
        return userId;
    }

    public long getTimeout() {
        return timeout;
    }
}
