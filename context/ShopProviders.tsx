"use client";

import type { ReactNode } from "react";
import { CartProvider } from "@/context/CartContext";
import { WishlistProvider } from "@/context/WishlistContext";
import { CheckoutProvider } from "@/context/CheckoutContext";

export function ShopProviders({ children }: { children: ReactNode }) {
  return (
    <CartProvider>
      <WishlistProvider>
        <CheckoutProvider>{children}</CheckoutProvider>
      </WishlistProvider>
    </CartProvider>
  );
}
