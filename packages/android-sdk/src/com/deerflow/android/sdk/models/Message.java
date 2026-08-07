package com.deerflow.android.sdk.models;

import java.util.List;
import java.util.Map;

/**
 * Message type
 */
public enum MessageType {
    HUMAN,
    AI,
    SYSTEM,
    TOOL
}

/**
 * Tool call
 */
public class ToolCall {
    private String id;
    private String type;
    private FunctionCall function;
    private Map<String, Object> args;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public FunctionCall getFunction() {
        return function;
    }

    public void setFunction(FunctionCall function) {
        this.function = function;
    }

    public Map<String, Object> getArgs() {
        return args;
    }

    public void setArgs(Map<String, Object> args) {
        this.args = args;
    }
}

/**
 * Function call
 */
public class FunctionCall {
    private String name;
    private String arguments;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getArguments() {
        return arguments;
    }

    public void setArguments(String arguments) {
        this.arguments = arguments;
    }
}

/**
 * Message
 */
public class Message {
    private String id;
    private MessageType type;
    private String content;
    private String name;
    private String tool_call_id;
    private List<ToolCall> tool_calls;
    private Map<String, Object> additional_kwargs;

    public Message() {}

    public Message(MessageType type, String content) {
        this.type = type;
        this.content = content;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public MessageType getType() {
        return type;
    }

    public void setType(MessageType type) {
        this.type = type;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getToolCallId() {
        return tool_call_id;
    }

    public void setToolCallId(String tool_call_id) {
        this.tool_call_id = tool_call_id;
    }

    public List<ToolCall> getToolCalls() {
        return tool_calls;
    }

    public void setToolCalls(List<ToolCall> tool_calls) {
        this.tool_calls = tool_calls;
    }

    public Map<String, Object> getAdditionalKwargs() {
        return additional_kwargs;
    }

    public void setAdditionalKwargs(Map<String, Object> additional_kwargs) {
        this.additional_kwargs = additional_kwargs;
    }
}

/**
 * AI message with additional metadata
 */
public class AIMessage extends Message {
    private Map<String, Object> response_metadata;

    public Map<String, Object> getResponseMetadata() {
        return response_metadata;
    }

    public void setResponseMetadata(Map<String, Object> response_metadata) {
        this.response_metadata = response_metadata;
    }
}
