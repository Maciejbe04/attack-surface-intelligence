export type AuthUser = {
  id: number;
  username: string;
  role: string;
  mfa_enabled: boolean;
};

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Kept for compatibility; CSRF is disabled by default on the API. */
export async function ensureCsrf(): Promise<string> {
  return getCookie("csrftoken") || "";
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers, credentials: "include" });
}
