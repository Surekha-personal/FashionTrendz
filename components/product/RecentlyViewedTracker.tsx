"use client";

import { useEffect } from "react";
import { recordRecentlyViewed } from "@/lib/recentlyViewed";

interface RecentlyViewedTrackerProps {
  slug: string;
  title: string;
  brand: string;
  image: string;
  price: number;
  discountedPrice: number;
}

export function RecentlyViewedTracker(props: RecentlyViewedTrackerProps) {
  useEffect(() => {
    recordRecentlyViewed(props);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.slug]);

  return null;
}
