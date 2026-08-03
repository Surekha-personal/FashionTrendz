"use client";

import { useEffect, useState } from "react";
import { ProductCarouselSection } from "@/components/home/ProductCarouselSection";
import { getRecentlyViewed, type RecentlyViewedEntry } from "@/lib/recentlyViewed";
import type { Product } from "@/types/product";

function toCardProduct(entry: RecentlyViewedEntry): Product {
  return {
    id: entry.slug,
    slug: entry.slug,
    name: entry.title,
    brand: entry.brand,
    price: entry.discountedPrice,
    compareAtPrice: entry.price > entry.discountedPrice ? entry.price : undefined,
    image: entry.image,
    imageAlt: `${entry.title} by ${entry.brand}`,
  };
}

export function RecentlyViewed({ excludeSlug }: { excludeSlug?: string }) {
  const [entries, setEntries] = useState<RecentlyViewedEntry[]>([]);

  useEffect(() => {
    setEntries(getRecentlyViewed(excludeSlug));
  }, [excludeSlug]);

  if (entries.length === 0) return null;

  return (
    <ProductCarouselSection
      eyebrow="Your History"
      title="Recently Viewed"
      products={entries.map(toCardProduct)}
    />
  );
}
