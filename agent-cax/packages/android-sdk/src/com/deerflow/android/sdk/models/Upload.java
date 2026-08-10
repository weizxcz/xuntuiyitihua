package com.deerflow.android.sdk.models;

import java.util.List;

/**
 * Upload file status
 */
public enum UploadFileStatus {
    UPLOADING,
    UPLOADED,
    ERROR
}

/**
 * Upload file information
 */
public class UploadFile {
    private String filename;
    private long size;
    private String path;
    private UploadFileStatus status;
    private String error;

    public String getFilename() {
        return filename;
    }

    public void setFilename(String filename) {
        this.filename = filename;
    }

    public long getSize() {
        return size;
    }

    public void setSize(long size) {
        this.size = size;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public UploadFileStatus getStatus() {
        return status;
    }

    public void setStatus(UploadFileStatus status) {
        this.status = status;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }
}

/**
 * Upload response
 */
public class UploadResponse {
    private boolean success;
    private List<UploadFile> files;

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public List<UploadFile> getFiles() {
        return files;
    }

    public void setFiles(List<UploadFile> files) {
        this.files = files;
    }
}

/**
 * Upload list response
 */
public class UploadListResponse {
    private List<UploadFile> files;

    public List<UploadFile> getFiles() {
        return files;
    }

    public void setFiles(List<UploadFile> files) {
        this.files = files;
    }
}
