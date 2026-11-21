export type AuthUser = {
  id: number;
  username: string;
  role: string;
  mfa_enabled: boolean;
};

const SESSION_KEY = "surfacex.sessionid";
const SESSION_EXPIRED_EVENT = "surfacex:session-expired";

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Kept for compatibility; CSRF is disabled by default on the API. */
export async function ensureCsrf(): Promise<string> {
  return getCookie("csrftoken") || "";
}

export function getSessionId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY) || localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function setSessionId(sessionid: string | null | undefined): void {
  try {
    if (!sessionid) {
      sessionStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    sessionStorage.setItem(SESSION_KEY, sessionid);
    localStorage.setItem(SESSION_KEY, sessionid);
  } catch {
    /* private mode / blocked storage */
  }
}

export function clearSessionId(): void {
  setSessionId(null);
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
  const sessionid = getSessionId();
  if (sessionid && !headers.has("X-Sessionid")) {
    headers.set("X-Sessionid", sessionid);
  }
  return fetch(input, { ...init, headers, credentials: "include" });
}

let sessionCheckInFlight: Promise<boolean> | null = null;

async function fetchMe(): Promise<{ authenticated: boolean; user?: AuthUser } | null> {
  try {
    const response = await apiFetch("/api/auth/me/");
    if (!response.ok) return null;
    return (await response.json()) as { authenticated: boolean; user?: AuthUser };
  } catch {
    return null;
  }
}

/**
 * Confirm the browser session is really gone before kicking the UI to login.
 * A single blip must not wipe a valid session.
 */
export async function confirmSessionLost(): Promise<boolean> {
  if (sessionCheckInFlight) return sessionCheckInFlight;
  sessionCheckInFlight = (async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    const first = await fetchMe();
    if (first == null) return false;
    if (first.authenticated) return false;
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    const second = await fetchMe();
    if (second == null) return false;
    const lost = !second.authenticated;
    if (lost) clearSessionId();
    return lost;
  })().finally(() => {
    sessionCheckInFlight = null;
  });
  return sessionCheckInFlight;
}

/** Soft signal: verify with /api/auth/me before clearing the UI session. */
export function emitSessionExpired(): void {
  if (typeof window === "undefined") return;
  void confirmSessionLost().then((lost) => {
    if (lost) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  });
}

export function onSessionExpired(handler: () => void): () => void {
  window.addEventListener(SESSION_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
}
