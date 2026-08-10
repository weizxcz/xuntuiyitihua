package com.deerflow.android.sdk;

import com.deerflow.android.sdk.models.*;

import java.util.*;

/**
 * Skills API
 */
public class SkillsApi {

    private final HttpClient httpClient;

    public SkillsApi(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    /**
     * List available skills
     */
    public List<Skill> list() throws Exception {
        SkillListResponse response = httpClient.get("/api/skills", null, SkillListResponse.class);
        return response != null ? response.getSkills() : new ArrayList<>();
    }

    /**
     * Get a skill by name
     */
    public Skill get(String name) throws Exception {
        return httpClient.get("/api/skills/" + name, null, Skill.class);
    }

    /**
     * Update skill enabled state
     */
    public void update(String name, boolean enabled) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("enabled", enabled);
        httpClient.put("/api/skills/" + name, body, Void.class);
    }
}
