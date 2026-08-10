package com.deerflow.android.sdk.utils;

import org.json.JSONArray;
import org.json.JSONObject;

import java.lang.reflect.*;
import java.util.*;

/**
 * JSON utility for serialization/deserialization
 */
public class JsonUtils {

    /**
     * Serialize object to JSON string
     */
    public static String toJson(Object obj) {
        if (obj == null) {
            return "null";
        }

        if (obj instanceof String) {
            return "\"" + escapeString((String) obj) + "\"";
        }

        if (obj instanceof Number || obj instanceof Boolean) {
            return obj.toString();
        }

        if (obj instanceof Map) {
            Map<?, ?> map = (Map<?, ?>) obj;
            StringBuilder sb = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (entry.getValue() == null) {
                    continue;
                }
                if (!first) {
                    sb.append(",");
                }
                sb.append("\"").append(escapeString(entry.getKey().toString())).append("\"");
                sb.append(toJson(entry.getValue()));
                first = false;
            }
            sb.append("}");
            return sb.toString();
        }

        if (obj instanceof List) {
            List<?> list = (List<?>) obj;
            StringBuilder sb = new StringBuilder("[");
            boolean first = true;
            for (Object item : list) {
                if (!first) {
                    sb.append(",");
                }
                sb.append(toJson(item));
                first = false;
            }
            sb.append("]");
            return sb.toString();
        }

        if (obj.getClass().isArray()) {
            return toJson(Arrays.asList((Object[]) obj));
        }

        // Try to use reflection for POJOs
        return objectToJson(obj);
    }

    /**
     * Deserialize JSON string to object
     */
    @SuppressWarnings("unchecked")
    public static <T> T fromJson(String json, Class<T> clazz) {
        try {
            JSONObject jsonObject = new JSONObject(json);
            return jsonToObject(jsonObject, clazz);
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse JSON: " + e.getMessage(), e);
        }
    }

    /**
     * Escape string for JSON
     */
    private static String escapeString(String str) {
        if (str == null) {
            return "";
        }
        return str
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    /**
     * Convert object to JSON using reflection
     */
    private static String objectToJson(Object obj) {
        if (obj == null) {
            return "null";
        }

        JSONObject json = new JSONObject();
        Class<?> clazz = obj.getClass();

        // Get all fields including parent classes
        while (clazz != null && clazz != Object.class) {
            for (Field field : clazz.getDeclaredFields()) {
                field.setAccessible(true);
                try {
                    // Skip static and transient fields
                    int modifiers = field.getModifiers();
                    if (Modifier.isStatic(modifiers) || Modifier.isTransient(modifiers)) {
                        continue;
                    }

                    String fieldName = field.getName();
                    // Skip fields starting with underscore or lowercase (typically private)
                    if (fieldName.startsWith("_") || (fieldName.length() > 0 && Character.isLowerCase(fieldName.charAt(0)))) {
                        // For POJOs, we want to include all fields
                    }

                    Object value = field.get(obj);
                    if (value != null) {
                        json.put(fieldName, value);
                    }
                } catch (IllegalAccessException e) {
                    // Skip inaccessible fields
                }
            }
            clazz = clazz.getSuperclass();
        }

        // Also try getters
        for (Method method : obj.getClass().getMethods()) {
            if (method.getName().startsWith("get") && method.getParameterCount() == 0) {
                String propertyName = method.getName().substring(3);
                if (propertyName.length() > 0) {
                    propertyName = Character.toLowerCase(propertyName.charAt(0)) + propertyName.substring(1);
                }
                try {
                    Object value = method.invoke(obj);
                    if (value != null) {
                        json.put(propertyName, value);
                    }
                } catch (Exception e) {
                    // Skip
                }
            }
        }

        return json.toString();
    }

    /**
     * Convert JSONObject to typed object
     */
    @SuppressWarnings("unchecked")
    private static <T> T jsonToObject(JSONObject json, Class<T> clazz) {
        if (json == null || json == JSONObject.NULL) {
            return null;
        }

        try {
            if (clazz == String.class) {
                return clazz.cast(json.toString());
            }

            if (clazz == Integer.class || clazz == int.class) {
                return clazz.cast(json.optInt());
            }

            if (clazz == Long.class || clazz == long.class) {
                return clazz.cast(json.optLong());
            }

            if (clazz == Double.class || clazz == double.class) {
                return clazz.cast(json.optDouble());
            }

            if (clazz == Float.class || clazz == float.class) {
                return clazz.cast((float) json.optDouble());
            }

            if (clazz == Boolean.class || clazz == boolean.class) {
                return clazz.cast(json.optBoolean());
            }

            if (clazz == Map.class) {
                return clazz.cast(toMap(json));
            }

            if (clazz == List.class) {
                return clazz.cast(toList(json));
            }

            // Create instance of the class
            T instance = clazz.getDeclaredConstructor().newInstance();
            for (Field field : clazz.getDeclaredFields()) {
                field.setAccessible(true);
                String fieldName = field.getName();
                if (json.has(fieldName)) {
                    Object value = getValue(json, fieldName, field.getType());
                    if (value != null) {
                        field.set(instance, value);
                    }
                }
            }
            return instance;
        } catch (Exception e) {
            throw new RuntimeException("Failed to create object: " + e.getMessage(), e);
        }
    }

    /**
     * Get value from JSON with type conversion
     */
    @SuppressWarnings("unchecked")
    private static Object getValue(JSONObject json, String key, Class<?> type) {
        Object value = json.opt(key);
        if (value == null || value == JSONObject.NULL) {
            return null;
        }

        if (value instanceof JSONObject) {
            if (Map.class.isAssignableFrom(type)) {
                return toMap((JSONObject) value);
            }
            // Try to convert to the target class
            try {
                return jsonToObject((JSONObject) value, type);
            } catch (Exception e) {
                return value;
            }
        }

        if (value instanceof JSONArray) {
            if (List.class.isAssignableFrom(type)) {
                return toList((JSONArray) value);
            }
            return value;
        }

        return value;
    }

    /**
     * Convert JSONObject to Map
     */
    private static Map<String, Object> toMap(JSONObject json) {
        Map<String, Object> map = new HashMap<>();
        for (String key : json.keySet()) {
            Object value = json.opt(key);
            if (value instanceof JSONObject) {
                value = toMap((JSONObject) value);
            } else if (value instanceof JSONArray) {
                value = toList((JSONArray) value);
            }
            map.put(key, value);
        }
        return map;
    }

    /**
     * Convert JSONArray to List
     */
    private static List<Object> toList(JSONArray array) {
        List<Object> list = new ArrayList<>();
        for (int i = 0; i < array.length(); i++) {
            Object value = array.opt(i);
            if (value instanceof JSONObject) {
                value = toMap((JSONObject) value);
            } else if (value instanceof JSONArray) {
                value = toList((JSONArray) value);
            }
            list.add(value);
        }
        return list;
    }
}
