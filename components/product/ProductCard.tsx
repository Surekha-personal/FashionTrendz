"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { Heart, Eye } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Rating } from "@/components/common/Rating";
import { Modal } from "@/components/common/Modal";
import { ProductOptions } from "@/components/product/ProductOptions";
import { useWishlist } from "@/context/WishlistContext";
import { formatPrice } from "@/utils/format";
import { cn } from "@/lib/utils";
import type { Product } from "@/types/product";

export function ProductCard({ product }: { product: Product }) {
  const { isWishlisted, toggleWishlist } = useWishlist();
  const [quickViewOpen, setQuickViewOpen] = useState(false);
  const {
    id,
    name,
    brand,
    price,
    compareAtPrice,
    image,
    hoverImage,
    imageAlt,
    rating,
    reviewCount,
    isNew,
    slug,
    sizes,
    colors,
    stock,
    description,
  } = product;
  const discount =
    compareAtPrice && compareAtPrice > price
      ? Math.round(((compareAtPrice - price) / compareAtPrice) * 100)
      : null;
  const wishlisted = isWishlisted(id);

  const onWishlistClick = (e: React.MouseEvent) => {
    e.preventDefault();
    toggleWishlist({
      productId: id,
      slug,
      name,
      brand,
      image,
      price: compareAtPrice ?? price,
      discountedPrice: price,
    });
  };

  return (
    <>
      <motion.div
        whileHover={{ y: -4 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
      >
        <Card className="group relative gap-3 p-0 shadow-sm transition-shadow hover:shadow-lg">
          <Link href={`/product/${slug}`} className="block">
            <div className="relative aspect-[3/4] w-full overflow-hidden rounded-t-xl bg-muted">
              <Image
                src={image}
                alt={imageAlt}
                fill
                sizes="(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw"
                className={cn(
                  "object-cover transition-opacity duration-300",
                  hoverImage && "group-hover:opacity-0"
                )}
              />
              {hoverImage && (
                <Image
                  src={hoverImage}
                  alt={imageAlt}
                  fill
                  sizes="(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw"
                  className="object-cover opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                />
              )}
              <div className="absolute top-2 left-2 flex flex-col gap-1">
                {isNew && <Badge>New</Badge>}
                {discount && <Badge variant="secondary">{discount}% OFF</Badge>}
              </div>
              <button
                type="button"
                aria-label={wishlisted ? "Remove from wishlist" : "Add to wishlist"}
                onClick={onWishlistClick}
                className="absolute top-2 right-2 flex size-8 items-center justify-center rounded-full bg-background/80 text-foreground backdrop-blur-sm transition-colors hover:text-accent"
              >
                <Heart
                  className={cn(
                    "size-4 transition-colors",
                    wishlisted && "fill-accent text-accent"
                  )}
                />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  setQuickViewOpen(true);
                }}
                className="absolute inset-x-2 bottom-2 flex translate-y-2 items-center justify-center gap-1.5 rounded-lg bg-background/95 py-2 text-xs font-medium opacity-0 backdrop-blur-sm transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100"
              >
                <Eye className="size-3.5" />
                Quick View
              </button>
            </div>
            <div className="flex flex-col gap-0.5 px-3 pb-3">
              <span className="text-xs font-medium text-muted-foreground">
                {brand}
              </span>
              <span className="truncate text-sm text-foreground">{name}</span>
              {typeof rating === "number" && (
                <Rating value={rating} count={reviewCount} className="py-0.5" />
              )}
              <div className="flex items-center gap-2 pt-1">
                <span className="text-sm font-semibold">
                  {formatPrice(price)}
                </span>
                {compareAtPrice && (
                  <span className="text-xs text-muted-foreground line-through">
                    {formatPrice(compareAtPrice)}
                  </span>
                )}
              </div>
            </div>
          </Link>
        </Card>
      </motion.div>

      <Modal
        open={quickViewOpen}
        onOpenChange={setQuickViewOpen}
        title={name}
        description={brand}
        size="lg"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="relative aspect-[3/4] overflow-hidden rounded-xl bg-muted">
            <Image src={image} alt={imageAlt} fill className="object-cover" />
          </div>
          <div className="flex flex-col gap-3">
            {typeof rating === "number" && (
              <Rating value={rating} count={reviewCount} />
            )}
            <div className="flex items-center gap-2">
              <span className="text-xl font-semibold">{formatPrice(price)}</span>
              {compareAtPrice && (
                <span className="text-sm text-muted-foreground line-through">
                  {formatPrice(compareAtPrice)}
                </span>
              )}
              {discount && <Badge variant="secondary">{discount}% OFF</Badge>}
            </div>
            {description && (
              <p className="line-clamp-3 text-sm text-muted-foreground">
                {description}
              </p>
            )}
            <Link
              href={`/product/${slug}`}
              onClick={() => setQuickViewOpen(false)}
              className="text-xs font-medium text-accent hover:underline"
            >
              View full details
            </Link>
            <ProductOptions
              productId={id}
              slug={slug}
              name={name}
              brand={brand}
              image={image}
              price={compareAtPrice ?? price}
              discountedPrice={price}
              sizes={sizes ?? []}
              colors={colors ?? []}
              stock={stock ?? 99}
              onAdded={() => setQuickViewOpen(false)}
            />
          </div>
        </div>
      </Modal>
    </>
  );
}
