"use client";

import { useMemo, useState } from "react";
import { Heart, Loader2, ShoppingBag } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useCart } from "@/context/CartContext";
import { useWishlist } from "@/context/WishlistContext";
import { COLOR_HEX } from "@/lib/colors";
import { cn } from "@/lib/utils";
import type { ProductVariantOption } from "@/types/product";

interface ProductOptionsProps {
  productId: string;
  slug: string;
  name: string;
  brand: string;
  image: string;
  price: number;
  discountedPrice: number;
  sizes: string[];
  colors: string[];
  stock: number;
  // Real colour/size -> SKU + stock data, from the product detail or
  // quick-view endpoint. Add to Bag is disabled until this has loaded,
  // since the backend cart addresses a line by variant SKU, not by a plain
  // size/colour pair.
  variants?: ProductVariantOption[];
  onAdded?: () => void;
}

export function ProductOptions({
  productId,
  slug,
  name,
  brand,
  image,
  price,
  discountedPrice,
  sizes,
  colors,
  stock,
  variants,
  onAdded,
}: ProductOptionsProps) {
  const { addToCart } = useCart();
  const { isWishlisted, toggleWishlist } = useWishlist();
  const [selectedSize, setSelectedSize] = useState<string>();
  const [selectedColor, setSelectedColor] = useState<string>(colors[0] ?? "");
  const wishlisted = isWishlisted(productId);
  const outOfStock = stock <= 0;
  const requiresSize = sizes.length > 0 && sizes[0] !== "One Size";
  const [adding, setAdding] = useState(false);

  const matchedVariant = useMemo(() => {
    if (!variants) return undefined;
    return variants.find(
      (v) =>
        (!requiresSize || v.size === selectedSize) &&
        (colors.length === 0 || v.color === selectedColor)
    );
  }, [variants, selectedSize, selectedColor, requiresSize, colors.length]);

  const addToBag = async () => {
    if (requiresSize && !selectedSize) {
      toast.error("Please select a size");
      return;
    }
    if (variants && !matchedVariant) {
      toast.error("That combination isn't available");
      return;
    }
    if (matchedVariant && matchedVariant.availableStock <= 0) {
      toast.error("That combination is out of stock");
      return;
    }
    setAdding(true);
    try {
      await addToCart({
        productId,
        slug,
        name,
        brand,
        image,
        price,
        discountedPrice,
        size: selectedSize,
        color: selectedColor || undefined,
        variantSku: matchedVariant?.sku,
      });
      onAdded?.();
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {colors.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">
            Color{selectedColor ? `: ${selectedColor}` : ""}
          </span>
          <div className="flex flex-wrap gap-2">
            {colors.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={color}
                onClick={() => setSelectedColor(color)}
                className={cn(
                  "size-8 rounded-full border-2 transition-all",
                  selectedColor === color
                    ? "border-accent ring-2 ring-accent/30"
                    : "border-border"
                )}
                style={{ backgroundColor: COLOR_HEX[color] ?? "#cccccc" }}
              />
            ))}
          </div>
        </div>
      )}

      {requiresSize && (
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">Size</span>
          <div className="flex flex-wrap gap-2">
            {sizes.map((size) => {
              // Only judge a size "unavailable" once real variant data has
              // loaded — before that (e.g. quick view still fetching) every
              // size stays selectable rather than flashing as sold out.
              const unavailable =
                variants !== undefined &&
                !variants.some(
                  (v) =>
                    v.size === size &&
                    (colors.length === 0 || v.color === selectedColor) &&
                    v.availableStock > 0
                );
              return (
                <button
                  key={size}
                  type="button"
                  disabled={unavailable}
                  onClick={() => setSelectedSize(size)}
                  className={cn(
                    "min-w-11 rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
                    unavailable
                      ? "cursor-not-allowed border-border text-muted-foreground/50 line-through"
                      : selectedSize === size
                        ? "border-foreground bg-foreground text-background"
                        : "border-border text-foreground/80 hover:border-foreground/40"
                  )}
                >
                  {size}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <Button
          size="lg"
          className="h-12 flex-1 text-base font-semibold tracking-wide"
          disabled={
            outOfStock || adding || (variants !== undefined && variants.length === 0)
          }
          onClick={addToBag}
        >
          {adding ? (
            <Loader2 className="animate-spin" />
          ) : (
            <ShoppingBag />
          )}
          {outOfStock ? "Out of Stock" : adding ? "Adding…" : "Add to Bag"}
        </Button>
        <Button
          size="lg"
          variant="outline"
          className="h-12 w-12 shrink-0 transition-transform active:scale-90"
          aria-label={wishlisted ? "Remove from wishlist" : "Add to wishlist"}
          onClick={() =>
            toggleWishlist({ productId, slug, name, brand, image, price, discountedPrice })
          }
        >
          <Heart className={cn("transition-all", wishlisted && "fill-accent text-accent")} />
        </Button>
      </div>

      {stock > 0 && stock <= 10 && (
        <p className="text-xs font-medium text-accent">
          Only {stock} left — order soon
        </p>
      )}
    </div>
  );
}
