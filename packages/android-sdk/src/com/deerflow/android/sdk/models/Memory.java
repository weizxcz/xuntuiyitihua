package com.deerflow.android.sdk.models;

import java.util.List;
import java.util.Map;

/**
 * Memory category
 */
public enum MemoryCategory {
    PREFERENCE,
    KNOWLEDGE,
    CONTEXT,
    BEHAVIOR,
    GOAL
}

/**
 * Memory source
 */
public enum MemorySource {
    USER_INPUT,
    AUTO_EXTRACT,
    SYSTEM
}

/**
 * Memory fact
 */
public class MemoryFact {
    private String id;
    private String content;
    private MemoryCategory category;
    private float confidence;
    private String created_at;
    private MemorySource source;

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

    public MemoryCategory getCategory() {
        return category;
    }

    public void setCategory(MemoryCategory category) {
        this.category = category;
    }

    public float getConfidence() {
        return confidence;
    }

    public void setConfidence(float confidence) {
        this.confidence = confidence;
    }

    public String getCreatedAt() {
        return created_at;
    }

    public void setCreatedAt(String created_at) {
        this.created_at = created_at;
    }

    public MemorySource getSource() {
        return source;
    }

    public void setSource(MemorySource source) {
        this.source = source;
    }
}

/**
 * Memory data
 */
public class MemoryData {
    private String userContext;
    private String personalContext;
    private List<String> topOfMind;
    private String recentMonths;
    private String earlierContext;
    private String longTermBackground;
    private List<MemoryFact> facts;

    public String getUserContext() {
        return userContext;
    }

    public void setUserContext(String userContext) {
        this.userContext = userContext;
    }

    public String getPersonalContext() {
        return personalContext;
    }

    public void setPersonalContext(String personalContext) {
        this.personalContext = personalContext;
    }

    public List<String> getTopOfMind() {
        return topOfMind;
    }

    public void setTopOfMind(List<String> topOfMind) {
        this.topOfMind = topOfMind;
    }

    public String getRecentMonths() {
        return recentMonths;
    }

    public void setRecentMonths(String recentMonths) {
        this.recentMonths = recentMonths;
    }

    public String getEarlierContext() {
        return earlierContext;
    }

    public void setEarlierContext(String earlierContext) {
        this.earlierContext = earlierContext;
    }

    public String getLongTermBackground() {
        return longTermBackground;
    }

    public void setLongTermBackground(String longTermBackground) {
        this.longTermBackground = longTermBackground;
    }

    public List<MemoryFact> getFacts() {
        return facts;
    }

    public void setFacts(List<MemoryFact> facts) {
        this.facts = facts;
    }
}
