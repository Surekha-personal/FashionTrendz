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
import { api, ApiError, cartSession } from "@/lib/api";
import { apiCartItemToLine } from "@/lib/apiAdapters";
import type { ApiCart, ApiCartSummary } from "@/types/api";
import type { AddToCartInput, CartLine } from "@/types/cart";

interface CartContextValue {
  items: CartLine[];
  activeItems: CartLine[];
  savedItems: CartLine[];
  itemCount: number;
  subtotal: number;
  totalMrp: number;
  totalSavings: number;
  // The backend's authoritative price breakdown (tax, shipping, platform fee,
  // coupon, grand total) — checkout reads this directly rather than
  // re-deriving numbers the server already computed.
  summary: ApiCartSummary | null;
  couponCode: string;
  hydrated: boolean;
  addToCart: (input: AddToCartInput) => Promise<void>;
  removeFromCart: (lineId: string) => Promise<void>;
  updateQuantity: (lineId: string, quantity: number) => Promise<void>;
  increment: (lineId: string) => Promise<void>;
  decrement: (lineId: string) => Promise<void>;
  saveForLater: (lineId: string) => Promise<void>;
  moveToCartFromSaved: (lineId: string) => Promise<void>;
  emptyCart: () => Promise<void>;
  applyCoupon: (code: string) => Promise<string>;
  removeCoupon: () => Promise<void>;
  refresh: () => Promise<void>;
}

const CartContext = createContext<CartContextValue | null>(null);

// crypto.randomUUID() only exists in secure contexts (HTTPS, or localhost) —
// on an HTTP LAN address, or in an older browser, `crypto` is present but
// `randomUUID` is not, and calling it throws "crypto.randomUUID is not a
// function". crypto.getRandomValues() has much broader support (all modern
// browsers, no secure-context restriction) and is enough to build a v4 UUID
// by hand; Math.random is a last-resort fallback for the rare environment
// with no crypto object at all. This id only keys an anonymous guest cart,
// not anything security-sensitive, so a non-cryptographic fallback is fine.
function generateGuestSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
    return [
      hex.slice(0, 4).join(""),
      hex.slice(4, 6).join(""),
      hex.slice(6, 8).join(""),
      hex.slice(8, 10).join(""),
      hex.slice(10, 16).join(""),
    ].join("-");
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

// A cart line is addressed by its variant SKU (unique per cart —
// apps/cart/models.py CartItem.unique_variant_per_cart), so lineId === sku
// throughout. Guest identity travels as a client-minted key in the
// X-Cart-Session header (apps/cart/views.py resolves any caller-supplied
// key into that guest's cart); it's replaced by the JWT once signed in.
//
// Only guests get a key. A signed-in caller has already had their guest
// cart merged (AuthContext.mergeGuestCartIfAny clears the stored key on
// login) — minting a fresh one here regardless of auth state used to make
// every authenticated cart request carry a pointless X-Cart-Session header,
// triggering a no-op merge lookup on every call.
function ensureGuestSession(isAuthenticated: boolean): void {
  if (isAuthenticated) return;
  if (!cartSession.get()) {
    cartSession.set(generateGuestSessionId());
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [cart, setCart] = useState<ApiCart | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const refresh = useCallback(async () => {
    ensureGuestSession(isAuthenticated);
    try {
      const data = await api.get<ApiCart>("/cart/", { cartHeader: true });
      setCart(data);
    } catch {
      // Leave the previous cart state in place rather than blanking the
      // drawer out on a transient network error.
    }
  }, [isAuthenticated]);

  useEffect(() => {
    refresh().finally(() => setHydrated(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runAction = useCallback(
    async (action: () => Promise<unknown>, successMessage?: string) => {
      try {
        await action();
        await refresh();
        if (successMessage) toast.success(successMessage);
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Something went wrong.");
      }
    },
    [refresh]
  );

  const addToCart = async (input: AddToCartInput) => {
    if (!input.variantSku) {
      toast.error("Please select a size and colour");
      return;
    }
    await runAction(
      () =>
        api.post(
          "/cart/add/",
          { product: input.slug, variant: input.variantSku, quantity: input.quantity ?? 1 },
          { cartHeader: true }
        ),
      "Added to bag"
    );
  };

  const removeFromCart = (lineId: string) =>
    runAction(
      () => api.post("/cart/remove/", { variant: lineId }, { cartHeader: true }),
      "Removed from bag"
    );

  const updateQuantity = (lineId: string, quantity: number) =>
    runAction(() => api.post("/cart/update/", { variant: lineId, quantity }, { cartHeader: true }));

  const increment = (lineId: string) =>
    runAction(() => api.post("/cart/increase/", { variant: lineId }, { cartHeader: true }));

  const decrement = (lineId: string) =>
    runAction(() => api.post("/cart/decrease/", { variant: lineId }, { cartHeader: true }));

  const saveForLater = (lineId: string) =>
    runAction(
      () => api.post("/cart/save-for-later/", { variant: lineId }, { cartHeader: true }),
      "Saved for later"
    );

  const moveToCartFromSaved = (lineId: string) =>
    runAction(
      () => api.post("/cart/move-to-bag/", { variant: lineId }, { cartHeader: true }),
      "Moved to bag"
    );

  const emptyCart = () =>
    runAction(
      () => api.post("/cart/clear/", { include_saved: false }, { cartHeader: true }),
      "Bag emptied"
    );

  // Coupon apply/remove throw ApiError straight through instead of going via
  // runAction, since the checkout review step needs the exact backend
  // message ("Add items worth ₹999 or more…") rather than a fixed toast.
  //
  // These go through /coupons/ (apps/coupons), not /cart/apply-coupon/ —
  // the cart module's own apply-coupon action is a documented placeholder
  // that never validates a code or applies a discount.
  const applyCoupon = async (code: string): Promise<string> => {
    const result = await api.post<{ message: string }>("/coupons/apply/", { code });
    await refresh();
    return result.message;
  };

  const removeCoupon = async () => {
    await api.post("/coupons/remove/", {});
    await refresh();
  };

  const value = useMemo<CartContextValue>(() => {
    const activeItems = (cart?.items ?? []).map(apiCartItemToLine);
    const savedItems = (cart?.saved_items ?? []).map(apiCartItemToLine);
    const summary = cart?.summary;

    return {
      items: [...activeItems, ...savedItems],
      activeItems,
      savedItems,
      itemCount: summary?.unit_count ?? 0,
      subtotal: summary ? Number(summary.subtotal) - Number(summary.discount) : 0,
      totalMrp: summary ? Number(summary.subtotal) : 0,
      totalSavings: summary ? Number(summary.discount) : 0,
      summary: summary ?? null,
      couponCode: cart?.coupon_code ?? "",
      hydrated,
      addToCart,
      removeFromCart,
      updateQuantity,
      increment,
      decrement,
      saveForLater,
      moveToCartFromSaved,
      emptyCart,
      applyCoupon,
      removeCoupon,
      refresh,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart, hydrated]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within a CartProvider");
  return ctx;
}
