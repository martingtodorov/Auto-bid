/**
 * WebAuthn / FIDO2 passkey client helpers.
 *
 * Wraps `@simplewebauthn/browser` and our backend endpoints so the rest
 * of the app talks to passkeys with a flat 4-method API:
 *
 *   isPasskeySupported()         → bool
 *   hasPasskey(email)            → { has: bool }
 *   registerPasskey(name, pwd)   → { ok: true } / throws
 *   authenticateWithPasskey(email?) → user-shape on success / throws
 *
 * All errors propagate the backend `detail` string (or a generic fallback)
 * so the calling component can `setErr(e.message)`.
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

export async function registerPasskey(deviceName, password) {
  // Server enforces re-auth via password — same as remove flow.
  const { data: begin } = await api.post("/auth/passkey/register-begin", {
    device_name: deviceName, password,
  });
  // `options_to_json` returns a JSON string.
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
  await api.post("/auth/passkey/register-finish", { credential: cred, device_name: deviceName });
  return { ok: true };
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
  return data; // { token, csrf_token, user }
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

export async function removePasskey(credentialId, password) {
  await api.post(`/auth/passkey/remove/${encodeURIComponent(credentialId)}`, { password });
}
