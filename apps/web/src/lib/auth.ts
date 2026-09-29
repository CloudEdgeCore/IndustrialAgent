/** 登录令牌（localStorage + 订阅，用于 useSyncExternalStore）。 */

const TOKEN_KEY = "industrial_agent_token";

const listeners = new Set<() => void>();

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  listeners.forEach((listener) => listener());
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  listeners.forEach((listener) => listener());
}

export function subscribeToken(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
