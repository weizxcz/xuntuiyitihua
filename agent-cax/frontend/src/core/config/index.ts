import { env } from "@/env";

function getBaseOrigin() {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  // Fallback for SSR
  return "http://localhost:2026";
}

export function getBackendBaseURL() {
  if (env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    return new URL(env.NEXT_PUBLIC_BACKEND_BASE_URL, getBaseOrigin())
      .toString()
      .replace(/\/+$/, "");
  } else {
    return "";
  }
}

export function getLangGraphBaseURL(isMock?: boolean) {
  console.log(
    "env.NEXT_PUBLIC_LANGGRAPH_BASE_URL",
    env.NEXT_PUBLIC_LANGGRAPH_BASE_URL,
  );
  if (env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
    return new URL(
      env.NEXT_PUBLIC_LANGGRAPH_BASE_URL,
      getBaseOrigin(),
    ).toString();
  } else if (isMock) {
    if (typeof window !== "undefined") {
      return `${window.location.origin}/mock/api`;
    }
    return "http://localhost:3000/mock/api";
  } else {
    // LangGraph SDK requires a full URL, construct it from current origin
    if (typeof window !== "undefined") {
      return `${window.location.origin}/api/langgraph`;
    }
    // Fallback for SSR
    return "http://localhost:2026/api/langgraph";
  }
}

/**
 * 获取 CAD Script MCP 服务器的 HTTP 端点 URL
 * 可以通过环境变量 NEXT_PUBLIC_CAD_SCRIPT_MCP_URL 配置
 * 默认值为 http://127.0.0.1:8310
 */
export function getCadScriptMcpBaseURL() {
  if (env.NEXT_PUBLIC_CAD_SCRIPT_MCP_URL) {
    return new URL(env.NEXT_PUBLIC_CAD_SCRIPT_MCP_URL, getBaseOrigin())
      .toString()
      .replace(/\/+$/, "");
  } else {
    // 默认值
    return "http://127.0.0.1:8310";
  }
}
