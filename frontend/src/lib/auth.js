import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./apiClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    // C3: разчитаме на httpOnly cookie за автентикация. Извикваме /auth/me
    // безусловно — ако няма cookie, backend ще върне 401.
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      // Изчистваме всякакъв стар localStorage токен (миграция от старата схема).
      try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email, password, remember = false) => {
    const { data } = await api.post("/auth/login", { email, password, remember: !!remember });
    // If 2FA is enabled, backend returns a challenge instead of a token
    if (data.requires_2fa) {
      return { requires_2fa: true, challenge_token: data.challenge_token };
    }
    // C3: cookies са вече зададени от backend.  Премахваме евентуални стари
    // localStorage стойности, за да не се ползва Bearer fallback излишно.
    try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  const verifyTwoFactor = async (challenge_token, code) => {
    const { data } = await api.post("/auth/2fa/verify", { challenge_token, code });
    try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  // Passkey-based login (alternative to password). Reuses the same
  // backend session/cookie flow as `login`, so post-success the rest
  // of the app behaves identically.
  const loginWithPasskey = async (email) => {
    const { authenticateWithPasskey } = await import("./passkey");
    const data = await authenticateWithPasskey(email);
    try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  // Passkey-as-2FA — user already typed password, backend issued a 2FA
  // challenge_token, and instead of a TOTP code the user can prove
  // identity with a passkey.
  const verifyTwoFactorWithPasskey = async (challenge_token) => {
    const { passkeyAsTwoFactor } = await import("./passkey");
    const data = await passkeyAsTwoFactor(challenge_token);
    try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  const register = async (fields) => {
    const { data } = await api.post("/auth/register", {
      ...fields,
      terms_accepted: !!fields.terms_accepted,
      terms_version: "v1",
    });
    try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (_e) { /* ignore */ }
    try { localStorage.removeItem("autobid_token"); } catch (_e) { /* ignore */ }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, verifyTwoFactor, loginWithPasskey, verifyTwoFactorWithPasskey }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function formatError(err) {
  const d = err?.response?.data?.detail;
  if (!d) return err?.message || "Възникна грешка";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  if (d?.msg) return d.msg;
  return String(d);
}
