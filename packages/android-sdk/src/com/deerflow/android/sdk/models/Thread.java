package com.deerflow.android.sdk.models;

import java.util.List;
import java.util.Map;

/**
 * Thread status
 */
public enum ThreadStatus {
    IDLE,
    BUSY,
    INTERRUPTED,
    ERROR
}

/**
 * Thread information
 */
public class Thread {
    private String thread_id;
    private ThreadStatus status;
    private String created_at;
    private String updated_at;
    private Map<String, Object> metadata;
    private ThreadState values;
    private Map<String, Object> interrupts;

    public String getThreadId() {
        return thread_id;
    }

    public void setThreadId(String thread_id) {
        this.thread_id = thread_id;
    }

    public ThreadStatus getStatus() {
        return status;
    }

    public void setStatus(ThreadStatus status) {
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

    public ThreadState getValues() {
        return values;
    }

    public void setValues(ThreadState values) {
        this.values = values;
    }

    public Map<String, Object> getInterrupts() {
        return interrupts;
    }

    public void setInterrupts(Map<String, Object> interrupts) {
        this.interrupts = interrupts;
    }
}

/**
 * Thread state
 */
public class ThreadState {
    private String title;
    private List<Message> messages;
    private List<String> artifacts;
    private List<Todo> todos;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public List<Message> getMessages() {
        return messages;
    }

    public void setMessages(List<Message> messages) {
        this.messages = messages;
    }

    public List<String> getArtifacts() {
        return artifacts;
    }

    public void setArtifacts(List<String> artifacts) {
        this.artifacts = artifacts;
    }

    public List<Todo> getTodos() {
        return todos;
    }

    public void setTodos(List<Todo> todos) {
        this.todos = todos;
    }
}

/**
 * Thread creation options
 */
public class ThreadCreateOptions {
    private String thread_id;
    private String assistant_id;
    private Map<String, Object> metadata;

    public String getThreadId() {
        return thread_id;
    }

    public void setThreadId(String thread_id) {
        this.thread_id = thread_id;
    }

    public String getAssistantId() {
        return assistant_id;
    }

    public void setAssistantId(String assistant_id) {
        this.assistant_id = assistant_id;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }
}

/**
 * Thread search options
 */
public class ThreadSearchOptions {
    private Map<String, Object> metadata;
    private Integer limit;
    private Integer offset;
    private ThreadStatus status;
    private String sortBy;
    private String sortOrder;

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }

    public Integer getLimit() {
        return limit;
    }

    public void setLimit(Integer limit) {
        this.limit = limit;
    }

    public Integer getOffset() {
        return offset;
    }

    public void setOffset(Integer offset) {
        this.offset = offset;
    }

    public ThreadStatus getStatus() {
        return status;
    }

    public void setStatus(ThreadStatus status) {
        this.status = status;
    }

    public String getSortBy() {
        return sortBy;
    }

    public void setSortBy(String sortBy) {
        this.sortBy = sortBy;
    }

    public String getSortOrder() {
        return sortOrder;
    }

    public void setSortOrder(String sortOrder) {
        this.sortOrder = sortOrder;
    }
}
