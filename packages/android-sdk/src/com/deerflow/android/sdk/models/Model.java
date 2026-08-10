package com.deerflow.android.sdk.models;

/**
 * Model information
 */
public class Model {
    private String name;
    private String display_name;
    private String provider;
    private boolean supports_thinking;
    private boolean supports_vision;
    private Integer max_tokens;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDisplayName() {
        return display_name;
    }

    public void setDisplayName(String display_name) {
        this.display_name = display_name;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public boolean isSupportsThinking() {
        return supports_thinking;
    }

    public void setSupportsThinking(boolean supports_thinking) {
        this.supports_thinking = supports_thinking;
    }

    public boolean isSupportsVision() {
        return supports_vision;
    }

    public void setSupportsVision(boolean supports_vision) {
        this.supports_vision = supports_vision;
    }

    public Integer getMaxTokens() {
        return max_tokens;
    }

    public void setMaxTokens(Integer max_tokens) {
        this.max_tokens = max_tokens;
    }
}

/**
 * Model list response
 */
public class ModelListResponse {
    private List<Model> models;

    public List<Model> getModels() {
        return models;
    }

    public void setModels(List<Model> models) {
        this.models = models;
    }
}
