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
import type { AddToCartInput, CartLine } from "@/types/cart";

const MAX_QTY = 10;

function makeLineId(productId: string, size?: string, color?: string) {
  return [productId, size ?? "_", color ?? "_"].join("::");
}

interface CartContextValue {
  items: CartLine[];
  activeItems: CartLine[];
  savedItems: CartLine[];
  itemCount: number;
  subtotal: number;
  totalMrp: number;
  totalSavings: number;
  hydrated: boolean;
  addToCart: (input: AddToCartInput) => void;
  removeFromCart: (lineId: string) => void;
  updateQuantity: (lineId: string, quantity: number) => void;
  increment: (lineId: string) => void;
  decrement: (lineId: string) => void;
  saveForLater: (lineId: string) => void;
  moveToCartFromSaved: (lineId: string) => void;
  emptyCart: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartLine[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setItems(localStore.read(STORAGE_KEYS.cart, []));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) localStore.write(STORAGE_KEYS.cart, items);
  }, [items, hydrated]);

  const addToCart = (input: AddToCartInput) => {
    const lineId = makeLineId(input.productId, input.size, input.color);
    const qty = input.quantity ?? 1;

    setItems((prev) => {
      const existing = prev.find((i) => i.lineId === lineId && !i.savedForLater);
      if (existing) {
        return prev.map((i) =>
          i.lineId === lineId && !i.savedForLater
            ? { ...i, quantity: Math.min(i.quantity + qty, MAX_QTY) }
            : i
        );
      }
      const newLine: CartLine = {
        lineId,
        productId: input.productId,
        slug: input.slug,
        name: input.name,
        brand: input.brand,
        image: input.image,
        price: input.price,
        discountedPrice: input.discountedPrice,
        size: input.size,
        color: input.color,
        quantity: Math.min(qty, MAX_QTY),
        savedForLater: false,
      };
      return [newLine, ...prev];
    });

    toast.success("Added to bag", {
      description: [input.size, input.color].filter(Boolean).join(" · ") || undefined,
    });
  };

  const removeFromCart = (lineId: string) => {
    setItems((prev) => prev.filter((i) => i.lineId !== lineId));
    toast("Removed from bag");
  };

  const updateQuantity = (lineId: string, quantity: number) => {
    if (quantity <= 0) {
      removeFromCart(lineId);
      return;
    }
    setItems((prev) =>
      prev.map((i) =>
        i.lineId === lineId ? { ...i, quantity: Math.min(quantity, MAX_QTY) } : i
      )
    );
  };

  const increment = (lineId: string) => {
    setItems((prev) =>
      prev.map((i) =>
        i.lineId === lineId
          ? { ...i, quantity: Math.min(i.quantity + 1, MAX_QTY) }
          : i
      )
    );
  };

  const decrement = (lineId: string) => {
    const line = items.find((i) => i.lineId === lineId);
    if (line && line.quantity <= 1) {
      removeFromCart(lineId);
      return;
    }
    setItems((prev) =>
      prev.map((i) =>
        i.lineId === lineId ? { ...i, quantity: Math.max(i.quantity - 1, 1) } : i
      )
    );
  };

  const saveForLater = (lineId: string) => {
    setItems((prev) =>
      prev.map((i) => (i.lineId === lineId ? { ...i, savedForLater: true } : i))
    );
    toast.success("Saved for later");
  };

  const moveToCartFromSaved = (lineId: string) => {
    setItems((prev) =>
      prev.map((i) => (i.lineId === lineId ? { ...i, savedForLater: false } : i))
    );
    toast.success("Moved to bag");
  };

  const emptyCart = () => {
    setItems((prev) => prev.filter((i) => i.savedForLater));
    toast("Bag emptied");
  };

  const value = useMemo<CartContextValue>(() => {
    const activeItems = items.filter((i) => !i.savedForLater);
    const savedItems = items.filter((i) => i.savedForLater);
    const itemCount = activeItems.reduce((sum, i) => sum + i.quantity, 0);
    const subtotal = activeItems.reduce(
      (sum, i) => sum + i.discountedPrice * i.quantity,
      0
    );
    const totalMrp = activeItems.reduce((sum, i) => sum + i.price * i.quantity, 0);

    return {
      items,
      activeItems,
      savedItems,
      itemCount,
      subtotal,
      totalMrp,
      totalSavings: totalMrp - subtotal,
      hydrated,
      addToCart,
      removeFromCart,
      updateQuantity,
      increment,
      decrement,
      saveForLater,
      moveToCartFromSaved,
      emptyCart,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, hydrated]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within a CartProvider");
  return ctx;
}
