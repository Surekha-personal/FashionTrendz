"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { ShoppingBag, X } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCart } from "@/context/CartContext";
import { useWishlist } from "@/context/WishlistContext";
import { formatPrice } from "@/utils/format";
import type { WishlistLine } from "@/types/cart";

export function WishlistCard({ item }: { item: WishlistLine }) {
  const { addToCart } = useCart();
  const { removeFromWishlist } = useWishlist();
  const discount =
    item.price > item.discountedPrice
      ? Math.round(((item.price - item.discountedPrice) / item.price) * 100)
      : null;

  const moveToCart = () => {
    addToCart({
      productId: item.productId,
      slug: item.slug,
      name: item.name,
      brand: item.brand,
      image: item.image,
      price: item.price,
      discountedPrice: item.discountedPrice,
    });
    removeFromWishlist(item.productId);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <Card className="group relative gap-3 p-0 shadow-sm transition-shadow hover:shadow-lg">
        <Link href={`/product/${item.slug}`} className="block">
          <div className="relative aspect-[3/4] w-full overflow-hidden rounded-t-xl bg-muted">
            <Image
              src={item.image}
              alt={item.name}
              fill
              sizes="(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw"
              className="object-cover transition-transform duration-300 group-hover:scale-105"
            />
            {discount && (
              <Badge variant="secondary" className="absolute top-2 left-2">
                {discount}% OFF
              </Badge>
            )}
          </div>
          <div className="flex flex-col gap-0.5 px-3 pt-3">
            <span className="text-xs font-medium text-muted-foreground">
              {item.brand}
            </span>
            <span className="truncate text-sm text-foreground">{item.name}</span>
            <div className="flex items-center gap-2 pt-1">
              <span className="text-sm font-semibold">
                {formatPrice(item.discountedPrice)}
              </span>
              {discount && (
                <span className="text-xs text-muted-foreground line-through">
                  {formatPrice(item.price)}
                </span>
              )}
            </div>
          </div>
        </Link>
        <div className="flex items-center gap-2 px-3 pb-3">
          <Button size="sm" className="flex-1" onClick={moveToCart}>
            <ShoppingBag className="size-3.5" />
            Move to Bag
          </Button>
          <button
            type="button"
            aria-label="Remove from wishlist"
            onClick={() => removeFromWishlist(item.productId)}
            className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
      </Card>
    </motion.div>
  );
}
