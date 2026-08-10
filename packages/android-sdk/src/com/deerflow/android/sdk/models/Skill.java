package com.deerflow.android.sdk.models;

import java.util.List;

/**
 * Skill information
 */
public class Skill {
    private String name;
    private String description;
    private boolean enabled;
    private String category;
    private List<String> allowed_tools;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public List<String> getAllowedTools() {
        return allowed_tools;
    }

    public void setAllowedTools(List<String> allowed_tools) {
        this.allowed_tools = allowed_tools;
    }
}

/**
 * Skill list response
 */
public class SkillListResponse {
    private List<Skill> skills;

    public List<Skill> getSkills() {
        return skills;
    }

    public void setSkills(List<Skill> skills) {
        this.skills = skills;
    }
}
