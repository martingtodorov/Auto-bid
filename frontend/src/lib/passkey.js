/**
 * WebAuthn / FIDO2 passkey client helpers.
 *
 * Wraps `@simplewebauthn/browser` and our backend endpoints so the rest
 * of the app talks to passkeys with a small flat API:
 *
 *   isPasskeySupported()                    → bool
 *   hasPasskey(email)                       → { has: bool }
 *   getReauthStatus()                       → { recent: bool, fresh_for_sec: number }
 *   verifyReauth(password)                  → { ok: true } / throws
 *   registerPasskey()                       → { ok: true } / throws — auto-named
 *   renamePasskey(id, name)                 → { ok: true } / throws
 *   removePasskey(id)                       → { ok: true } / throws
 *   authenticateWithPasskey(email?)         → user shape / throws
 *
 * Add/remove operations rely on the session's `recent_auth_at` timestamp.
 * If `getReauthStatus().recent` is false the UI MUST gate the action
 * behind `verifyReauth(password)`; otherwise the backend will respond
 * 401 with header `X-Reauth-Required: 1` and the user-facing message
 * "Необходимо е скорошно потвърждаване с парола.".
 */

import { startRegistration, startAuthentication, browserSupportsWebAuthn } from "@simplewebauthn/browser";
import { api } from "./apiClient";

export const isPasskeySupported = () => {
  try {
    return browserSupportsWebAuthn();
  } catch {
    return false;
  }
};

export async function hasPasskey(email) {
  if (!email) return { has: false };
  try {
    const { data } = await api.get("/auth/passkey/has-passkey", { params: { email } });
    return data;
  } catch {
    return { has: false };
  }
}

const _msg = (e, fallback) => e?.response?.data?.detail || e?.message || fallback;

export async function getReauthStatus() {
  const { data } = await api.get("/auth/passkey/reauth-status");
  return data; // { recent, fresh_for_sec?, window_seconds }
}

export async function verifyReauth(password) {
  const { data } = await api.post("/auth/passkey/reauth", { password });
  return data; // { ok: true, fresh_for_sec }
}

export async function registerPasskey() {
  // Backend derives the device name from the User-Agent. No password
  // here either — the recent-auth window covers it. If the window has
  // expired the call returns 401 + `X-Reauth-Required` header and the
  // caller must run `verifyReauth(password)` first.
  const { data: begin } = await api.post("/auth/passkey/register-begin", {});
  const opts = typeof begin.options === "string" ? JSON.parse(begin.options) : begin.options;
  let cred;
  try {
    cred = await startRegistration({ optionsJSON: opts });
  } catch (e) {
    if (e?.name === "InvalidStateError") {
      throw new Error("Този passkey вече е регистриран за акаунта.");
    }
    if (e?.name === "NotAllowedError") {
      throw new Error("Регистрацията беше отказана.");
    }
    throw new Error(e?.message || "Passkey регистрацията се провали.");
  }
  const { data } = await api.post("/auth/passkey/register-finish", { credential: cred });
  return data; // { ok: true, credential_id, device_name }
}

export async function renamePasskey(credentialId, name) {
  const { data } = await api.post(
    `/auth/passkey/rename/${encodeURIComponent(credentialId)}`,
    { name },
  );
  return data; // { ok: true, device_name }
}

export async function authenticateWithPasskey(email) {
  const { data: begin } = await api.post("/auth/passkey/authenticate-begin", {
    email: email || null,
  });
  const opts = typeof begin.options === "string" ? JSON.parse(begin.options) : begin.options;
  let assertion;
  try {
    assertion = await startAuthentication({ optionsJSON: opts });
  } catch (e) {
    if (e?.name === "NotAllowedError") {
      throw new Error("Удостоверяването беше отказано.");
    }
    throw new Error(e?.message || "Passkey удостоверяването се провали.");
  }
  const { data } = await api.post("/auth/passkey/authenticate-finish", { credential: assertion });
  return data;
}

export async function passkeyAsTwoFactor(challengeToken) {
  const { data: begin } = await api.post("/auth/passkey/2fa-begin", {
    challenge_token: challengeToken,
  });
  const opts = typeof begin.options === "string" ? JSON.parse(begin.options) : begin.options;
  let assertion;
  try {
    assertion = await startAuthentication({ optionsJSON: opts });
  } catch (e) {
    throw new Error(_msg(e, "Удостоверяването беше отказано."));
  }
  const { data } = await api.post(
    "/auth/passkey/2fa-finish",
    { credential: assertion },
    { params: { challenge_token: challengeToken } }
  );
  return data;
}

export async function listPasskeys() {
  const { data } = await api.get("/auth/passkey/list");
  return data.items || [];
}

export async function removePasskey(credentialId) {
  // Recent-auth window covers authorisation; the password parameter is
  // intentionally not sent. Backend will 401 with `X-Reauth-Required: 1`
  // when the window has lapsed.
  await api.post(`/auth/passkey/remove/${encodeURIComponent(credentialId)}`, {});
}
