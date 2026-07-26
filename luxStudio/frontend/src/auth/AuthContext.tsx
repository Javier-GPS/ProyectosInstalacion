import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export interface AuthUser {
  id: number;
  company_name: string;
  email: string;
  name: string;
  role: 'ADMIN' | 'USER';
  is_active: boolean;
  must_reset_password: boolean;
}

export type AuthFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  authFetch: AuthFetch;
}

const TOKEN_KEY = 'lux-studio-auth-token';
const PORTAL_MESSAGE_TYPE = 'salvi:auth';
const PORTAL_ORIGINS = (import.meta.env.VITE_PORTAL_ORIGINS || 'http://localhost:3000,http://localhost,http://127.0.0.1:3000,http://127.0.0.1').split(',').map((origin: string) => origin.trim());
const AuthContext = createContext<AuthContextValue | null>(null);

const authHeaders = (token: string) => ({
  Authorization: `Bearer ${token}`,
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    setLoading(true);
    fetch('/api/auth/me', { headers: authHeaders(token) })
      .then(async response => {
        if (!response.ok) throw new Error('Session expired');
        setUser(await response.json());
      })
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

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || 'auth.loginFailed');
    }
    const data = await response.json();
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
    setUser(data.user);
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    if (!token) throw new Error('auth.sessionExpired');
    const response = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || 'auth.changePasswordFailed');
    }
    setUser(await response.json());
  }, [token]);

  const authFetch = useCallback<AuthFetch>((input, init = {}) => {
    if (!token) throw new Error('auth.sessionExpired');
    return fetch(input, {
      ...init,
      headers: {
        ...(init.headers || {}),
        ...authHeaders(token),
      },
    });
  }, [token]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    token,
    loading,
    login,
    logout,
    changePassword,
    authFetch,
  }), [user, token, loading, login, logout, changePassword, authFetch]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
