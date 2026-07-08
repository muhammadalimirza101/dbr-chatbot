import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  getRefreshToken,
  setAccessToken,
  setUnauthorizedHandler,
  storeRefreshToken,
} from "../api/client";
import type { User } from "../api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setAccessToken(null);
    storeRefreshToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    // resume session from refresh token
    (async () => {
      try {
        if (getRefreshToken()) {
          const me = await api.get<User>("/auth/me");
          setUser(me);
        }
      } catch {
        logout();
      } finally {
        setLoading(false);
      }
    })();
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.post<{ access_token: string; refresh_token: string }>(
      "/auth/login",
      { email, password },
    );
    setAccessToken(tokens.access_token);
    storeRefreshToken(tokens.refresh_token);
    setUser(await api.get<User>("/auth/me"));
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
