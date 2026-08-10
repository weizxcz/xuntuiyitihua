package com.deerflow.android.sdk.models;

/**
 * Base exception for all DeerFlow SDK errors
 */
public class DeerFlowException extends Exception {
    private final Integer statusCode;

    public DeerFlowException(String message, Throwable cause, Integer statusCode) {
        super(message, cause);
        this.statusCode = statusCode;
    }

    public Integer getStatusCode() {
        return statusCode;
    }
}

/**
 * Authentication failed exception
 */
class AuthenticationException extends DeerFlowException {
    public AuthenticationException(String message) {
        super(message, null, 401);
    }
}

/**
 * Resource not found exception
 */
class NotFoundException extends DeerFlowException {
    public NotFoundException(String message) {
        super(message, null, 404);
    }
}

/**
 * Network exception
 */
class NetworkException extends DeerFlowException {
    public NetworkException(String message, Throwable cause) {
        super(message, cause, null);
    }
}

/**
 * Timeout exception
 */
class TimeoutException extends DeerFlowException {
    public TimeoutException(String message) {
        super(message, null, null);
    }
}
