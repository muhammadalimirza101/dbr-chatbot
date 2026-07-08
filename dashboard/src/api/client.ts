/**
 * API client with JWT auth: access token in memory, refresh token in
 * sessionStorage. On 401 it refreshes once and retries; on refresh failure
 * the auth listener logs the user out.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

let accessToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem("dbr_refresh");
}

export function storeRefreshToken(token: string | null): void {
  if (token === null) sessionStorage.removeItem("dbr_refresh");
  else sessionStorage.setItem("dbr_refresh", token);
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!response.ok) return false;
  const data = await response.json();
  setAccessToken(data.access_token);
  storeRefreshToken(data.refresh_token);
  return true;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retried = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && typeof options.body === "string") {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401 && !retried) {
    if (await tryRefresh()) return request<T>(path, options, true);
    onUnauthorized?.();
    throw new ApiError(401, "Session expired");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: "DELETE" }),
  /** multipart upload (no JSON content-type) */
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

export function wsUrl(): string {
  return `${API_BASE.replace(/^http/, "ws")}/conversations/ws`;
}
