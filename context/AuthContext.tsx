"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import { api, ApiError, cartSession, tokenStore } from "@/lib/api";
import type { ApiAuthResponse, ApiUser } from "@/types/api";

interface RegisterInput {
  email: string;
  password: string;
  confirm_password: string;
  first_name?: string;
  last_name?: string;
}

interface AuthContextValue {
  user: ApiUser | null;
  hydrated: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// After sign-in, folding any guest cart into the account is the backend's
// job — it happens automatically the next time a cart request carries
// X-Cart-Session (apps/cart/views.py CartViewSet.resolve_cart). Firing one
// harmless cart read here is enough to trigger the merge immediately rather
// than waiting for the next page that happens to touch the cart.
async function mergeGuestCartIfAny() {
  const session = cartSession.get();
  if (!session) return;
  try {
    await api.get("/cart/", { cartHeader: true });
  } catch {
    // Non-fatal — the merge will simply happen on the next cart request.
  } finally {
    cartSession.clear();
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const access = tokenStore.getAccess();
    if (!access) {
      setHydrated(true);
      return;
    }
    api
      .get<ApiUser>("/profile/")
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setHydrated(true));
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const data = await api.post<ApiAuthResponse>(
        "/auth/login/",
        { email, password },
        { auth: false }
      );
      tokenStore.set(data.access, data.refresh);
      setUser(data.user);
      await mergeGuestCartIfAny();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not sign in.";
      toast.error(message);
      throw err;
    }
  };

  const register = async (input: RegisterInput) => {
    try {
      await api.post("/auth/register/", input, { auth: false });
      await login(input.email, input.password);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not create your account.";
      toast.error(message);
      throw err;
    }
  };

  const logout = async () => {
    const refresh = tokenStore.getRefresh();
    // Blacklist the refresh token before clearing local state — the request
    // needs the still-present access token to authenticate. Clearing first
    // left this request unauthenticated and it silently failed to revoke
    // anything server-side.
    if (refresh) {
      try {
        await api.post("/auth/logout/", { refresh });
      } catch {
        // Token is cleared client-side regardless of whether the blacklist
        // call succeeds.
      }
    }
    tokenStore.clear();
    setUser(null);
  };

  const value = useMemo<AuthContextValue>(
    () => ({ user, hydrated, isAuthenticated: !!user, login, register, logout }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [user, hydrated]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
