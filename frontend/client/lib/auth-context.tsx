"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  getMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  resolveApiUrl,
  setAccessToken,
  type LoginResponse,
  type User,
} from "@/lib/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, turnstileToken?: string | null) => Promise<LoginResponse | void>;
  register: (email: string, password: string, name?: string, turnstileToken?: string | null) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  register: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session on mount — relies on httpOnly cookie sent automatically
  useEffect(() => {
    const restoreSession = async () => {
      try {
        // Attempt to refresh using the httpOnly cookie (no localStorage needed)
        const res = await fetch(resolveApiUrl("/api/v1/auth/refresh"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include", // sends httpOnly refresh_token cookie
          body: JSON.stringify({}),
        });
        if (!res.ok) throw new Error("Session invalide");
        const data = await res.json();
        setAccessToken(data.access_token);
        const me = await getMe();
        setUser(me);
      } catch {
        localStorage.removeItem("refresh_token"); // cleanup legacy storage
      } finally {
        setLoading(false);
      }
    };
    restoreSession();
  }, []);

  const login = useCallback(async (email: string, password: string, turnstileToken?: string | null): Promise<LoginResponse | void> => {
    const result = await apiLogin(email, password, turnstileToken);
    // Only fetch user if login is fully complete (not a 2FA partial)
    if (!result?.requires_2fa) {
      const me = await getMe();
      setUser(me);
    }
    return result;
  }, []);

  const register = useCallback(
    async (email: string, password: string, name?: string, turnstileToken?: string | null) => {
      await apiRegister(email, password, name, turnstileToken);
      const me = await getMe();
      setUser(me);
    },
    []
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
