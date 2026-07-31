/**
 * HTTP Client for DeerFlow API
 */

import type { ClientConfig } from "./types";

export class HttpClient {
  private baseUrl: string;
  private authToken?: string;
  private userId?: string;
  private timeout: number;

  constructor(config: ClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "");
    this.authToken = config.authToken;
    this.userId = config.userId;
    this.timeout = config.timeout ?? 30000;
  }

  /**
   * Build a request URL with optional query parameters
   */
  private buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
    const url = new URL(`${this.baseUrl}${path}`);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }
    return url.toString();
  }

  /**
   * Get default headers for requests
   */
  getDefaultHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (this.authToken) {
      headers["Authorization"] = `Bearer ${this.authToken}`;
    }

    return headers;
  }

  /**
   * Get headers with CSRF token for state-changing requests
   */
  private getAuthHeaders(): Record<string, string> {
    const headers = this.getDefaultHeaders();
    // CSRF token handling is done at the browser level via cookies
    // This is for internal API calls
    if (this.authToken) {
      headers["X-Internal-Auth"] = this.authToken;
    }
    return headers;
  }

  /**
   * Handle response errors
   */
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      let errorData: unknown;
      try {
        errorData = await response.json();
      } catch {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const message = (errorData as { detail?: string })?.detail || `HTTP ${response.status}`;
      throw new Error(message);
    }

    // Handle empty responses
    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      return {} as T;
    }

    return response.json() as Promise<T>;
  }

  /**
   * Fetch with timeout
   */
  private async fetchWithTimeout(url: string, options: RequestInit = {}): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: options.signal || controller.signal,
      });
      return response;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * GET request
   */
  async get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const url = this.buildUrl(path, params);
    const response = await this.fetchWithTimeout(url, {
      method: "GET",
      headers: this.getDefaultHeaders(),
    });
    return this.handleResponse<T>(response);
  }

  /**
   * POST request
   */
  async post<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
    const response = await this.fetchWithTimeout(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.getAuthHeaders(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return this.handleResponse<T>(response);
  }

  /**
   * PUT request
   */
  async put<T>(path: string, body?: unknown): Promise<T> {
    const response = await this.fetchWithTimeout(`${this.baseUrl}${path}`, {
      method: "PUT",
      headers: this.getAuthHeaders(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return this.handleResponse<T>(response);
  }

  /**
   * DELETE request
   */
  async delete<T>(path: string): Promise<T> {
    const response = await this.fetchWithTimeout(`${this.baseUrl}${path}`, {
      method: "DELETE",
      headers: this.getAuthHeaders(),
    });
    return this.handleResponse<T>(response);
  }

  /**
   * Upload files (multipart/form-data)
   */
  async upload<T>(path: string, formData: FormData): Promise<T> {
    const response = await this.fetchWithTimeout(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {},
      body: formData,
    });
    return this.handleResponse<T>(response);
  }

  /**
   * Download file as blob
   */
  async download(path: string): Promise<Blob> {
    const response = await this.fetchWithTimeout(`${this.baseUrl}${path}`, {
      method: "GET",
      headers: this.getDefaultHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Download failed: ${response.status}`);
    }

    return response.blob();
  }

  /**
   * Get the base URL
   */
  getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * SSE stream request
   */
  async stream(path: string, body?: unknown, onEvent?: (event: string, data: unknown) => void): Promise<void> {
    const url = `${this.baseUrl}${path}`;

    const response = await fetch(url, {
      method: "POST",
      headers: this.getAuthHeaders(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (onEvent) {
            try {
              const parsed = JSON.parse(data);
              onEvent("message", parsed);
            } catch {
              onEvent("message", data);
            }
          }
        }
      }
    }
  }
}
