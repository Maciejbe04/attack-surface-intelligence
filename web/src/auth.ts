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

export async function ensureCsrf(): Promise<string> {
  const existing = getCookie("csrftoken");
  if (existing) return existing;
  const response = await fetch("/api/auth/csrf/", { credentials: "include" });
  if (!response.ok) throw new Error("Could not initialize CSRF");
  const data = (await response.json()) as { csrfToken: string };
  return getCookie("csrftoken") || data.csrfToken;
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (init.method && init.method.toUpperCase() !== "GET") {
    const csrf = await ensureCsrf();
    headers.set("X-CSRFToken", csrf);
  }
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers, credentials: "include" });
}
