package com.deerflow.android.sdk.models;

import java.util.List;
import java.util.Map;

/**
 * MCP server type
 */
public enum MCPServerType {
    STDIO,
    SSE,
    HTTP
}

/**
 * MCP server configuration
 */
public class MCPServer {
    private String name;
    private boolean enabled;
    private MCPServerType type;
    private String command;
    private List<String> args;
    private Map<String, String> env;
    private String url;
    private Map<String, String> headers;
    private String description;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public MCPServerType getType() {
        return type;
    }

    public void setType(MCPServerType type) {
        this.type = type;
    }

    public String getCommand() {
        return command;
    }

    public void setCommand(String command) {
        this.command = command;
    }

    public List<String> getArgs() {
        return args;
    }

    public void setArgs(List<String> args) {
        this.args = args;
    }

    public Map<String, String> getEnv() {
        return env;
    }

    public void setEnv(Map<String, String> env) {
        this.env = env;
    }

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    public void setHeaders(Map<String, String> headers) {
        this.headers = headers;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}

/**
 * MCP config response
 */
public class MCPConfigResponse {
    private Map<String, MCPServer> mcp_servers;

    public Map<String, MCPServer> getMcpServers() {
        return mcp_servers;
    }

    public void setMcpServers(Map<String, MCPServer> mcp_servers) {
        this.mcp_servers = mcp_servers;
    }
}
