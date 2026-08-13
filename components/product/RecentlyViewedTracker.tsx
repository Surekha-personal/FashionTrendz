"use client";

import { useEffect } from "react";
import { recordRecentlyViewed } from "@/lib/apiCatalog";

export function RecentlyViewedTracker({ slug }: { slug: string }) {
  useEffect(() => {
    recordRecentlyViewed(slug);
  }, [slug]);

  return null;
}
