package com.deerflow.android.sdk.models;

import java.util.List;

/**
 * Stream mode
 */
public enum StreamMode {
    VALUES,
    MESSAGES,
    MESSAGES_TUPLE,
    MESSAGES_LAST,
    CUSTOM,
    UPDATES,
    EVENTS,
    DEBUG,
    TASKS,
    CHECKPOINTS
}

/**
 * Token usage information
 */
public class TokenUsage {
    private int input_tokens;
    private int output_tokens;
    private int total_tokens;

    public int getInputTokens() {
        return input_tokens;
    }

    public void setInputTokens(int input_tokens) {
        this.input_tokens = input_tokens;
    }

    public int getOutputTokens() {
        return output_tokens;
    }

    public void setOutputTokens(int output_tokens) {
        this.output_tokens = output_tokens;
    }

    public int getTotalTokens() {
        return total_tokens;
    }

    public void setTotalTokens(int total_tokens) {
        this.total_tokens = total_tokens;
    }
}

/**
 * Token usage response
 */
public class TokenUsageResponse {
    private String thread_id;
    private int total_tokens;
    private int total_input_tokens;
    private int total_output_tokens;
    private int total_runs;
    private Map<String, ModelTokenUsage> by_model;
    private Map<String, Integer> by_caller;

    public String getThreadId() {
        return thread_id;
    }

    public void setThreadId(String thread_id) {
        this.thread_id = thread_id;
    }

    public int getTotalTokens() {
        return total_tokens;
    }

    public void setTotalTokens(int total_tokens) {
        this.total_tokens = total_tokens;
    }

    public int getTotalInputTokens() {
        return total_input_tokens;
    }

    public void setTotalInputTokens(int total_input_tokens) {
        this.total_input_tokens = total_input_tokens;
    }

    public int getTotalOutputTokens() {
        return total_output_tokens;
    }

    public void setTotalOutputTokens(int total_output_tokens) {
        this.total_output_tokens = total_output_tokens;
    }

    public int getTotalRuns() {
        return total_runs;
    }

    public void setTotalRuns(int total_runs) {
        this.total_runs = total_runs;
    }

    public Map<String, ModelTokenUsage> getByModel() {
        return by_model;
    }

    public void setByModel(Map<String, ModelTokenUsage> by_model) {
        this.by_model = by_model;
    }

    public Map<String, Integer> getByCaller() {
        return by_caller;
    }

    public void setByCaller(Map<String, Integer> by_caller) {
        this.by_caller = by_caller;
    }
}

/**
 * Model token usage
 */
public class ModelTokenUsage {
    private int tokens;
    private int runs;

    public int getTokens() {
        return tokens;
    }

    public void setTokens(int tokens) {
        this.tokens = tokens;
    }

    public int getRuns() {
        return runs;
    }

    public void setRuns(int runs) {
        this.runs = runs;
    }
}
