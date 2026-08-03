"use client";

import { useState } from "react";
import { Heart, ShoppingBag } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useCart } from "@/context/CartContext";
import { useWishlist } from "@/context/WishlistContext";
import { cn } from "@/lib/utils";

const COLOR_HEX: Record<string, string> = {
  Black: "#111111",
  White: "#f5f5f5",
  Navy: "#1f2a44",
  Beige: "#e8dcc8",
  Olive: "#6b6f42",
  Maroon: "#5c1a26",
  Mustard: "#d9a441",
  "Blush Pink": "#f3c9cd",
  Ivory: "#f4f1e8",
  Charcoal: "#36454f",
  Emerald: "#0f6b4c",
  Rust: "#b0532a",
  Lavender: "#c8b8e8",
  Teal: "#1f6f6b",
  Camel: "#c19a6b",
  "Grey Melange": "#9a9a9a",
  Wine: "#5e1f30",
  "Sky Blue": "#8ecae6",
  Coral: "#e8735c",
  Sand: "#dcc7a1",
};

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
  onAdded,
}: ProductOptionsProps) {
  const { addToCart } = useCart();
  const { isWishlisted, toggleWishlist } = useWishlist();
  const [selectedSize, setSelectedSize] = useState<string>();
  const [selectedColor, setSelectedColor] = useState<string>(colors[0] ?? "");
  const wishlisted = isWishlisted(productId);
  const outOfStock = stock <= 0;
  const requiresSize = sizes.length > 0 && sizes[0] !== "One Size";

  const addToBag = () => {
    if (requiresSize && !selectedSize) {
      toast.error("Please select a size");
      return;
    }
    addToCart({
      productId,
      slug,
      name,
      brand,
      image,
      price,
      discountedPrice,
      size: selectedSize,
      color: selectedColor || undefined,
    });
    onAdded?.();
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
            {sizes.map((size) => (
              <button
                key={size}
                type="button"
                onClick={() => setSelectedSize(size)}
                className={cn(
                  "min-w-11 rounded-lg border px-3 py-2 text-sm",
                  selectedSize === size
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border text-foreground/80 hover:border-foreground/40"
                )}
              >
                {size}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <Button
          size="lg"
          className="flex-1"
          disabled={outOfStock}
          onClick={addToBag}
        >
          <ShoppingBag />
          {outOfStock ? "Out of Stock" : "Add to Bag"}
        </Button>
        <Button
          size="lg"
          variant="outline"
          onClick={() =>
            toggleWishlist({ productId, slug, name, brand, image, price, discountedPrice })
          }
        >
          <Heart className={cn(wishlisted && "fill-accent text-accent")} />
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
