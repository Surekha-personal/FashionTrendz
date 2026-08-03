"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { Minus, Plus, X } from "lucide-react";
import { useCart } from "@/context/CartContext";
import { useWishlist } from "@/context/WishlistContext";
import { formatPrice } from "@/utils/format";
import type { CartLine } from "@/types/cart";

export function CartLineItem({ line }: { line: CartLine }) {
  const { increment, decrement, removeFromCart, saveForLater, moveToCartFromSaved } =
    useCart();
  const { addToWishlist } = useWishlist();

  const moveToWishlist = () => {
    addToWishlist({
      productId: line.productId,
      slug: line.slug,
      name: line.name,
      brand: line.brand,
      image: line.image,
      price: line.price,
      discountedPrice: line.discountedPrice,
    });
    removeFromCart(line.lineId);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20, height: 0, marginBottom: 0 }}
      transition={{ duration: 0.2 }}
      className="flex gap-3"
    >
      <Link
        href={`/product/${line.slug}`}
        className="relative size-20 shrink-0 overflow-hidden rounded-lg bg-muted sm:size-24"
      >
        <Image src={line.image} alt={line.name} fill className="object-cover" />
      </Link>
      <div className="flex flex-1 flex-col gap-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col">
            <span className="text-xs text-muted-foreground">{line.brand}</span>
            <Link
              href={`/product/${line.slug}`}
              className="line-clamp-1 text-sm font-medium hover:text-accent"
            >
              {line.name}
            </Link>
            {(line.size || line.color) && (
              <span className="text-xs text-muted-foreground">
                {[line.size, line.color].filter(Boolean).join(" · ")}
              </span>
            )}
          </div>
          <button
            type="button"
            aria-label="Remove item"
            onClick={() => removeFromCart(line.lineId)}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="mt-auto flex items-center justify-between gap-2">
          {line.savedForLater ? (
            <span className="text-xs text-muted-foreground">
              Qty: {line.quantity}
            </span>
          ) : (
            <div className="flex items-center gap-1 rounded-full border border-border">
              <button
                type="button"
                aria-label="Decrease quantity"
                onClick={() => decrement(line.lineId)}
                className="flex size-6 items-center justify-center rounded-full hover:bg-muted"
              >
                <Minus className="size-3" />
              </button>
              <span className="w-5 text-center text-xs font-medium">
                {line.quantity}
              </span>
              <button
                type="button"
                aria-label="Increase quantity"
                onClick={() => increment(line.lineId)}
                className="flex size-6 items-center justify-center rounded-full hover:bg-muted"
              >
                <Plus className="size-3" />
              </button>
            </div>
          )}
          <span className="text-sm font-semibold">
            {formatPrice(line.discountedPrice * line.quantity)}
          </span>
        </div>
        <div className="flex gap-3 pt-1 text-[11px] font-medium text-muted-foreground">
          {line.savedForLater ? (
            <button
              type="button"
              onClick={() => moveToCartFromSaved(line.lineId)}
              className="hover:text-accent"
            >
              Move to bag
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={() => saveForLater(line.lineId)}
                className="hover:text-accent"
              >
                Save for later
              </button>
              <button type="button" onClick={moveToWishlist} className="hover:text-accent">
                Move to wishlist
              </button>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}
