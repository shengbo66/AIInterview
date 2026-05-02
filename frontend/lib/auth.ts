/**
 * Cognito Hosted UI auth helper.
 *
 * Flow:
 *   1. User visits any page → getAccessToken() returns stored token or null
 *   2. If null → redirectToLogin() bounces to Cognito Hosted UI
 *   3. After login, Cognito redirects to /auth/callback?code=xxxx
 *   4. Callback page calls exchangeCodeForTokens() and stores result in sessionStorage
 *   5. All API calls add Authorization: Bearer <access_token>
 */

const COGNITO_DOMAIN =
  process.env.NEXT_PUBLIC_COGNITO_DOMAIN ??
  "https://interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com";
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? "54ljqt6asmevn1qchrbb0in8r1";

function redirectUri(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/auth/callback`;
}

function logoutUri(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/`;
}

export function isAuthEnabled(): boolean {
  // If either config is missing, disable auth (local dev without Cognito)
  return Boolean(COGNITO_DOMAIN && CLIENT_ID);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("access_token");
}

export function getIdToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("id_token");
}

export function getUserEmail(): string | null {
  const id = getIdToken();
  if (!id) return null;
  try {
    const payload = JSON.parse(atob(id.split(".")[1]));
    return payload.email ?? null;
  } catch {
    return null;
  }
}

export function redirectToLogin(): void {
  const url = new URL(`${COGNITO_DOMAIN}/login`);
  url.searchParams.set("client_id", CLIENT_ID);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("redirect_uri", redirectUri());
  window.location.assign(url.toString());
}

export function logout(): void {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("id_token");
  sessionStorage.removeItem("refresh_token");
  const url = new URL(`${COGNITO_DOMAIN}/logout`);
  url.searchParams.set("client_id", CLIENT_ID);
  url.searchParams.set("logout_uri", logoutUri());
  window.location.assign(url.toString());
}

export async function exchangeCodeForTokens(code: string): Promise<void> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: CLIENT_ID,
    code,
    redirect_uri: redirectUri(),
  });
  const resp = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Token exchange failed: ${resp.status} ${text}`);
  }
  const data = await resp.json();
  sessionStorage.setItem("access_token", data.access_token);
  sessionStorage.setItem("id_token", data.id_token);
  if (data.refresh_token) {
    sessionStorage.setItem("refresh_token", data.refresh_token);
  }
}

export function authHeaders(): HeadersInit {
  const t = getAccessToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/**
 * Check if the access token is expired (or about to expire in 60s).
 * Returns true if token is missing or expired.
 */
function isTokenExpired(): boolean {
  const token = getAccessToken();
  if (!token) return true;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const exp = payload.exp;
    if (!exp) return true;
    // Refresh 60s before actual expiry
    return Date.now() / 1000 > exp - 60;
  } catch {
    return true;
  }
}

/**
 * Refresh the access token using the stored refresh_token.
 * Returns true if refresh succeeded, false if user must re-login.
 */
async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = typeof window !== "undefined"
    ? sessionStorage.getItem("refresh_token")
    : null;
  if (!refreshToken) return false;

  try {
    const body = new URLSearchParams({
      grant_type: "refresh_token",
      client_id: CLIENT_ID,
      refresh_token: refreshToken,
    });
    const resp = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    sessionStorage.setItem("access_token", data.access_token);
    if (data.id_token) sessionStorage.setItem("id_token", data.id_token);
    return true;
  } catch {
    return false;
  }
}

/**
 * Ensure a valid access token is available. Auto-refreshes if expired.
 * Returns the token, or null if refresh failed (caller should redirect to login).
 */
export async function ensureValidToken(): Promise<string | null> {
  if (!isTokenExpired()) return getAccessToken();
  const ok = await refreshAccessToken();
  return ok ? getAccessToken() : null;
}
