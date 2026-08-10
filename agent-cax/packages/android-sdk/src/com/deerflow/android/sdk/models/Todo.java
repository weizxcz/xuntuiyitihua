package com.deerflow.android.sdk.models;

/**
 * Todo status
 */
public enum TodoStatus {
    PENDING,
    IN_PROGRESS,
    COMPLETED
}

/**
 * Todo item
 */
public class Todo {
    private String id;
    private String content;
    private TodoStatus status;
    private String activeForm;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public TodoStatus getStatus() {
        return status;
    }

    public void setStatus(TodoStatus status) {
        this.status = status;
    }

    public String getActiveForm() {
        return activeForm;
    }

    public void setActiveForm(String activeForm) {
        this.activeForm = activeForm;
    }
}
