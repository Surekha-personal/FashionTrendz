"use client";

import { useEffect, useState } from "react";
import { ProductCarouselSection } from "@/components/home/ProductCarouselSection";
import { fetchRecentlyViewed } from "@/lib/apiCatalog";
import type { Product } from "@/types/product";

export function RecentlyViewed({ excludeSlug }: { excludeSlug?: string }) {
  const [products, setProducts] = useState<Product[]>([]);

  useEffect(() => {
    // The backend returns most-recent-first for the caller (guest session or
    // signed-in user) and has no exclude-current-product filter, so the page
    // currently being viewed — just recorded by RecentlyViewedTracker — is
    // filtered out client-side instead.
    fetchRecentlyViewed()
      .then((items) => setProducts(items.filter((p) => p.slug !== excludeSlug)))
      .catch(() => setProducts([]));
  }, [excludeSlug]);

  if (products.length === 0) return null;

  return (
    <ProductCarouselSection
      eyebrow="Your History"
      title="Recently Viewed"
      products={products}
    />
  );
}
