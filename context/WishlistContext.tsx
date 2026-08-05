"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError, apiFetchPaged } from "@/lib/api";
import { apiWishlistItemToLine } from "@/lib/apiAdapters";
import type { ApiWishlistItem } from "@/types/api";
import type { WishlistLine } from "@/types/cart";

interface WishlistContextValue {
  items: WishlistLine[];
  count: number;
  hydrated: boolean;
  isWishlisted: (productId: string) => boolean;
  addToWishlist: (item: Omit<WishlistLine, "addedAt">) => void;
  removeFromWishlist: (productId: string) => void;
  toggleWishlist: (item: Omit<WishlistLine, "addedAt">) => void;
}

const WishlistContext = createContext<WishlistContextValue | null>(null);

// The wishlist is account-only on the backend (IsAuthenticated in
// apps/wishlist/views.py) — there's no guest equivalent to fall back to, so
// signed-out actions prompt sign-in instead of writing anywhere locally.
export function WishlistProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, hydrated: authHydrated } = useAuth();
  const [items, setItems] = useState<WishlistLine[]>([]);
  const [hydrated, setHydrated] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setItems([]);
      return;
    }
    try {
      const { data } = await apiFetchPaged<ApiWishlistItem[]>("/wishlist/");
      setItems(data.map(apiWishlistItemToLine));
    } catch {
      // Keep whatever was last loaded.
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!authHydrated) return;
    refresh().finally(() => setHydrated(true));
  }, [authHydrated, refresh]);

  const isWishlisted = (productId: string) => items.some((i) => i.productId === productId);

  const requireAuth = () => {
    if (isAuthenticated) return true;
    toast.error("Sign in to save items to your wishlist");
    return false;
  };

  const addToWishlist = (item: Omit<WishlistLine, "addedAt">) => {
    if (!requireAuth()) return;
    api
      .post("/wishlist/add/", { product: item.slug })
      .then(() => {
        toast.success("Added to wishlist");
        refresh();
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not add item."));
  };

  const removeFromWishlist = (productId: string) => {
    if (!requireAuth()) return;
    const item = items.find((i) => i.productId === productId);
    if (!item) return;
    api
      .post("/wishlist/remove/", { product: item.slug })
      .then(() => {
        toast("Removed from wishlist");
        refresh();
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not remove item."));
  };

  const toggleWishlist = (item: Omit<WishlistLine, "addedAt">) => {
    if (!requireAuth()) return;
    api
      .post<{ in_wishlist: boolean }>("/wishlist/toggle/", { product: item.slug })
      .then((result) => {
        toast.success(result.in_wishlist ? "Added to wishlist" : "Removed from wishlist");
        refresh();
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not update wishlist."));
  };

  const value = useMemo<WishlistContextValue>(
    () => ({
      items,
      count: items.length,
      hydrated,
      isWishlisted,
      addToWishlist,
      removeFromWishlist,
      toggleWishlist,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, hydrated]
  );

  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>;
}

export function useWishlist() {
  const ctx = useContext(WishlistContext);
  if (!ctx) throw new Error("useWishlist must be used within a WishlistProvider");
  return ctx;
}
