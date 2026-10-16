import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, clearSession, hasSession, saveSession } from './api';
import type { User } from './types';

type AuthValue = { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => void; reloadUser: () => Promise<void> };
const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const reloadUser = useCallback(async () => {
    if (!hasSession()) { setUser(null); return; }
    const response = await api.get<User>('/auth/me');
    setUser(response.data);
  }, []);

  useEffect(() => {
    reloadUser().catch(() => { clearSession(); setUser(null); }).finally(() => setLoading(false));
  }, [reloadUser]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post('/auth/login', { email, password });
    saveSession(response.data.access_token, response.data.refresh_token);
    setUser(await api.get<User>('/auth/me').then((item) => item.data));
  }, []);
  const logout = useCallback(() => { clearSession(); setUser(null); }, []);
  const value = useMemo(() => ({ user, loading, login, logout, reloadUser }), [user, loading, login, logout, reloadUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is missing');
  return value;
}
