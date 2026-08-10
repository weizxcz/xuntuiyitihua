package com.deerflow.android.sdk.models;

import java.util.List;
import java.util.Map;

/**
 * Run status
 */
public enum RunStatus {
    PENDING,
    RUNNING,
    SUCCESS,
    ERROR,
    CANCELLED
}

/**
 * Run configuration
 */
public class RunConfig {
    private Integer recursion_limit;
    private Map<String, Object> configurable;

    public Integer getRecursionLimit() {
        return recursion_limit;
    }

    public void setRecursionLimit(Integer recursion_limit) {
        this.recursion_limit = recursion_limit;
    }

    public Map<String, Object> getConfigurable() {
        return configurable;
    }

    public void setConfigurable(Map<String, Object> configurable) {
        this.configurable = configurable;
    }
}

/**
 * Run information
 */
public class Run {
    private String run_id;
    private String thread_id;
    private RunStatus status;
    private String created_at;
    private String updated_at;
    private Map<String, Object> metadata;
    private String error;

    public String getRunId() {
        return run_id;
    }

    public void setRunId(String run_id) {
        this.run_id = run_id;
    }

    public String getThreadId() {
        return thread_id;
    }

    public void setThreadId(String thread_id) {
        this.thread_id = thread_id;
    }

    public RunStatus getStatus() {
        return status;
    }

    public void setStatus(RunStatus status) {
        this.status = status;
    }

    public String getCreatedAt() {
        return created_at;
    }

    public void setCreatedAt(String created_at) {
        this.created_at = created_at;
    }

    public String getUpdatedAt() {
        return updated_at;
    }

    public void setUpdatedAt(String updated_at) {
        this.updated_at = updated_at;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }
}

/**
 * Run messages response
 */
public class RunMessagesResponse {
    private List<Message> data;
    private boolean has_more;

    public List<Message> getData() {
        return data;
    }

    public void setData(List<Message> data) {
        this.data = data;
    }

    public boolean isHasMore() {
        return has_more;
    }

    public void setHasMore(boolean has_more) {
        this.has_more = has_more;
    }
}
