// SSR-safe localStorage/sessionStorage JSON helpers. Cart and wishlist are
// backend-API-driven and no longer use this — what's left is the admin
// preview's order list and the in-progress checkout draft.
function read<T>(area: Storage, key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = area.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write<T>(area: Storage, key: string, value: T) {
  if (typeof window === "undefined") return;
  try {
    area.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable or quota exceeded — fail silently, state stays in-memory
  }
}

export const localStore = {
  read: <T>(key: string, fallback: T) => read(window.localStorage, key, fallback),
  write: <T>(key: string, value: T) => write(window.localStorage, key, value),
  remove: (key: string) => {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(key);
  },
};

export const sessionStore = {
  read: <T>(key: string, fallback: T) => read(window.sessionStorage, key, fallback),
  write: <T>(key: string, value: T) => write(window.sessionStorage, key, value),
  remove: (key: string) => {
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem(key);
  },
};

export const STORAGE_KEYS = {
  // orders: read by the admin-preview dashboard only (AdminOrdersPanel via
  // lib/orders.ts) — real checkout goes through the backend API, not here.
  orders: "ft_orders",
  checkoutDraft: "ft_checkout_draft",
} as const;
