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
import { localStore, STORAGE_KEYS } from "@/lib/storage";
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

export function WishlistProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<WishlistLine[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setItems(localStore.read(STORAGE_KEYS.wishlist, []));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) localStore.write(STORAGE_KEYS.wishlist, items);
  }, [items, hydrated]);

  const isWishlisted = (productId: string) =>
    items.some((i) => i.productId === productId);

  const addToWishlist = (item: Omit<WishlistLine, "addedAt">) => {
    setItems((prev) => {
      if (prev.some((i) => i.productId === item.productId)) return prev;
      return [{ ...item, addedAt: Date.now() }, ...prev];
    });
    toast.success("Added to wishlist");
  };

  const removeFromWishlist = (productId: string) => {
    setItems((prev) => prev.filter((i) => i.productId !== productId));
    toast("Removed from wishlist");
  };

  const toggleWishlist = (item: Omit<WishlistLine, "addedAt">) => {
    if (isWishlisted(item.productId)) removeFromWishlist(item.productId);
    else addToWishlist(item);
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

  return (
    <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>
  );
}

export function useWishlist() {
  const ctx = useContext(WishlistContext);
  if (!ctx) throw new Error("useWishlist must be used within a WishlistProvider");
  return ctx;
}
