package com.deerflow.android.sdk.models;

/**
 * Feedback information
 */
public class Feedback {
    private String feedback_id;
    private String run_id;
    private String key;
    private float score;
    private String comment;
    private String created_at;
    private String updated_at;

    public String getFeedbackId() {
        return feedback_id;
    }

    public void setFeedbackId(String feedback_id) {
        this.feedback_id = feedback_id;
    }

    public String getRunId() {
        return run_id;
    }

    public void setRunId(String run_id) {
        this.run_id = run_id;
    }

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    public float getScore() {
        return score;
    }

    public void setScore(float score) {
        this.score = score;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
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
}

/**
 * Feedback creation options
 */
public class FeedbackCreateOptions {
    private String key;
    private float score;
    private String comment;

    public String getKey() {
        return key;
    }

    public void setKey(String key) {
        this.key = key;
    }

    public float getScore() {
        return score;
    }

    public void setScore(float score) {
        this.score = score;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }
}
