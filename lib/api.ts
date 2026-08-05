// Thin client for the Django backend. Every response from that API is
// enveloped as {success, message, data, pagination?} (see the backend's
// apps/core/responses.py) — this unwraps that envelope and normalises
// failures into one ApiError type so callers never touch the wire shape.

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(
  /\/+$/,
  ""
);

const ACCESS_KEY = "ft_access_token";
const REFRESH_KEY = "ft_refresh_token";
const CART_SESSION_KEY = "ft_cart_session";

export class ApiError extends Error {
  status: number;
  errors: Record<string, string[]>;

  constructor(message: string, status: number, errors: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errors = errors;
  }
}

export interface Envelope<T> {
  success: boolean;
  message: string;
  data: T;
  pagination?: {
    count: number;
    page: number;
    page_size: number;
    total_pages: number;
    next: string | null;
    previous: string | null;
  };
}

// -- Tokens and guest cart session -----------------------------------------

export const tokenStore = {
  getAccess: () => (typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY)),
  getRefresh: () => (typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY)),
  set: (access: string, refresh: string) => {
    if (typeof window === "undefined") return;
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  setAccess: (access: string) => {
    if (typeof window === "undefined") return;
    localStorage.setItem(ACCESS_KEY, access);
  },
  clear: () => {
    if (typeof window === "undefined") return;
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

// Guest cart identity. The backend merges this cart into the user's cart the
// moment it sees the header on an authenticated request (apps/cart/views.py).
export const cartSession = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem(CART_SESSION_KEY)),
  set: (key: string) => {
    if (typeof window === "undefined") return;
    localStorage.setItem(CART_SESSION_KEY, key);
  },
  clear: () => {
    if (typeof window === "undefined") return;
    localStorage.removeItem(CART_SESSION_KEY);
  },
};

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  auth?: boolean; // attach Authorization header (default true)
  cartHeader?: boolean; // attach X-Cart-Session header (default false)
  skipRefresh?: boolean; // internal: prevent infinite refresh loop
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return null;

  const res = await fetch(`${API_BASE}/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    tokenStore.clear();
    return null;
  }
  const json = (await res.json()) as Envelope<{ access: string; refresh?: string }>;
  const access = json.data?.access;
  if (!access) return null;
  // SIMPLE_JWT has ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION enabled,
  // so the refresh response carries a new refresh token and blacklists the
  // old one. Store it too, or the next refresh reuses a blacklisted token.
  if (json.data?.refresh) {
    tokenStore.set(access, json.data.refresh);
  } else {
    tokenStore.setAccess(access);
  }
  return access;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, cartHeader = false, skipRefresh = false, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  if (body !== undefined) finalHeaders.set("Content-Type", "application/json");

  if (auth) {
    const access = tokenStore.getAccess();
    if (access) finalHeaders.set("Authorization", `Bearer ${access}`);
  }
  if (cartHeader) {
    const session = cartSession.get();
    if (session) finalHeaders.set("X-Cart-Session", session);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    credentials: "include", // carries the guest-cart session cookie fallback
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // Access token expired: refresh once and retry, transparently to the caller.
  if (res.status === 401 && auth && !skipRefresh && tokenStore.getRefresh()) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, skipRefresh: true });
    }
  }

  if (res.status === 204) return undefined as T;

  const json = (await res.json().catch(() => null)) as Envelope<T> | null;

  if (!res.ok || !json || json.success === false) {
    const message = json?.message ?? `Request failed with status ${res.status}`;
    throw new ApiError(message, res.status, (json as { errors?: Record<string, string[]> })?.errors ?? {});
  }

  // List endpoints hoist pagination alongside data; callers that need it read
  // apiFetchPaged instead.
  return json.data;
}

export async function apiFetchPaged<T>(
  path: string,
  options: RequestOptions = {}
): Promise<{ data: T; pagination: Envelope<T>["pagination"] }> {
  const { body, auth = true, cartHeader = false, headers, ...rest } = options;
  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  if (body !== undefined) finalHeaders.set("Content-Type", "application/json");
  if (auth) {
    const access = tokenStore.getAccess();
    if (access) finalHeaders.set("Authorization", `Bearer ${access}`);
  }
  if (cartHeader) {
    const session = cartSession.get();
    if (session) finalHeaders.set("X-Cart-Session", session);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 204) return { data: undefined as T, pagination: undefined };

  const json = (await res.json().catch(() => null)) as Envelope<T> | null;
  if (!res.ok || !json || json.success === false) {
    const message = json?.message ?? `Request failed with status ${res.status}`;
    throw new ApiError(message, res.status, (json as { errors?: Record<string, string[]> })?.errors ?? {});
  }
  return { data: json.data, pagination: json.pagination };
}

// Convenience wrappers.
export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE", body }),
};

// Server Components have no localStorage/cookies to send a bearer token, so
// public reads (catalog, search) go through a bare fetch instead of apiFetch.
export async function publicGet<T>(path: string, revalidate = 60): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { next: { revalidate } });
  const json = (await res.json().catch(() => null)) as Envelope<T> | null;
  if (!res.ok || !json || json.success === false) {
    throw new ApiError(json?.message ?? `Request failed with status ${res.status}`, res.status);
  }
  return json.data;
}

export async function publicGetPaged<T>(
  path: string,
  revalidate = 60
): Promise<{ data: T; pagination: Envelope<T>["pagination"] }> {
  const res = await fetch(`${API_BASE}${path}`, { next: { revalidate } });
  const json = (await res.json().catch(() => null)) as Envelope<T> | null;
  if (!res.ok || !json || json.success === false) {
    throw new ApiError(json?.message ?? `Request failed with status ${res.status}`, res.status);
  }
  return { data: json.data, pagination: json.pagination };
}
