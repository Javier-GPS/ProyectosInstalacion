import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { GisUser } from '../types';

interface AuthContextValue {
  user: GisUser | null;
  token: string | null;
  loading: boolean;
  logout: () => void;
  authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

const TOKEN_KEY = 'gis-auth-token';
const PORTAL_MESSAGE_TYPE = 'salvi:auth';
const PORTAL_ORIGINS = (import.meta.env.VITE_PORTAL_ORIGINS || 'http://localhost:3000,http://localhost,http://127.0.0.1:3000,http://127.0.0.1').split(',').map((origin: string) => origin.trim());
const AuthContext = createContext<AuthContextValue | null>(null);

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` });

export const GisAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<GisUser | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    setLoading(true);
    fetch('/api/auth/me', { headers: authHeaders(token) })
      .then(async r => { if (!r.ok) throw new Error('Session expired'); setUser(await r.json()); })
      .catch(() => logout())
      .finally(() => setLoading(false));
  }, [token, logout]);

  useEffect(() => {
    const receivePortalToken = (event: MessageEvent<{ type?: string; token?: string }>) => {
      if (!PORTAL_ORIGINS.includes(event.origin) || event.source !== window.parent || event.data?.type !== PORTAL_MESSAGE_TYPE) return;
      if (!event.data.token) return;
      localStorage.setItem(TOKEN_KEY, event.data.token);
      setToken(event.data.token);
    };
    window.addEventListener('message', receivePortalToken);
    return () => window.removeEventListener('message', receivePortalToken);
  }, []);

  const authFetch = useCallback((input: RequestInfo | URL, init: RequestInit = {}) => {
    if (!token) throw new Error('No token');
    return fetch(input, { ...init, headers: { ...init.headers, ...authHeaders(token) } });
  }, [token]);

  const value = useMemo<AuthContextValue>(() => ({ user, token, loading, logout, authFetch }), [user, token, loading, logout, authFetch]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within GisAuthProvider');
  return ctx;
};
