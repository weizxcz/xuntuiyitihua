package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * MCP API
 */
public class McpApi {

    private final HttpClient httpClient;

    public McpApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * Get MCP config
     */
    public Map<String, MCPServer> getConfig() throws Exception {
        MCPConfigResponse response = httpClient.get("/api/mcp/config", null, MCPConfigResponse.class);
        return response != null ? response.getMcpServers() : new HashMap<>();
    }

    /**
     * Update MCP config
     */
    public void updateConfig(Map<String, MCPServer> servers) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("mcp_servers", servers);
        httpClient.put("/api/mcp/config", body, Void.class);
    }
}
