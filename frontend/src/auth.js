// Session helpers for the Domain Workbench's Google sign-in.
//
// Flow: Google Identity Services renders the sign-in button and hands back a
// Google ID token; that gets exchanged with auth_api (POST /auth/google) for
// this app's own short-lived session JWT, which is what every other request
// to prompts_api/batch_api sends as `Authorization: Bearer <token>`.

export const AUTH_API_BASE = "http://localhost:8089";
const SESSION_STORAGE_KEY = "workbench.session";

// Set this to the Google OAuth Client ID (Web application type) once it's
// created in Google Cloud Console. Can also be supplied via
// frontend/.env as VITE_GOOGLE_CLIENT_ID=... (picked up automatically by Vite).
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

export function getSession() {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(session) {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // ignore storage failures
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// Drop-in replacement for fetch() that attaches the session token when
// present. Safe to use for any URL — endpoints that don't require auth just
// ignore the extra header.
export async function authFetch(url, options = {}) {
  const session = getSession();
  const headers = new Headers(options.headers || {});
  if (session?.token) {
    headers.set("Authorization", `Bearer ${session.token}`);
  }
  return fetch(url, { ...options, headers });
}

export async function exchangeGoogleIdToken(idToken) {
  const response = await fetch(`${AUTH_API_BASE}/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken })
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Sign-in failed (HTTP ${response.status})`);
  }
  return response.json();
}

export async function verifySession() {
  const session = getSession();
  if (!session?.token) return null;
  try {
    const response = await authFetch(`${AUTH_API_BASE}/auth/me`);
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}
