import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./apiClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = localStorage.getItem("autobid_token");
    if (!token) { setUser(null); setLoading(false); return; }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (e) {
      localStorage.removeItem("autobid_token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    // If 2FA is enabled, backend returns a challenge instead of a token
    if (data.requires_2fa) {
      return { requires_2fa: true, challenge_token: data.challenge_token };
    }
    localStorage.setItem("autobid_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const verifyTwoFactor = async (challenge_token, code) => {
    const { data } = await api.post("/auth/2fa/verify", { challenge_token, code });
    localStorage.setItem("autobid_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const register = async (email, password, name) => {
    const { data } = await api.post("/auth/register", { email, password, name });
    localStorage.setItem("autobid_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("autobid_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, verifyTwoFactor }}>
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
