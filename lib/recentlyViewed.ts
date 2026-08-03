import { localStore, STORAGE_KEYS } from "@/lib/storage";

export interface RecentlyViewedEntry {
  slug: string;
  title: string;
  brand: string;
  image: string;
  price: number;
  discountedPrice: number;
  viewedAt: number;
}

const MAX_ENTRIES = 12;

export function recordRecentlyViewed(entry: Omit<RecentlyViewedEntry, "viewedAt">) {
  const list = localStore.read<RecentlyViewedEntry[]>(STORAGE_KEYS.recentlyViewed, []);
  const next = [
    { ...entry, viewedAt: Date.now() },
    ...list.filter((i) => i.slug !== entry.slug),
  ].slice(0, MAX_ENTRIES);
  localStore.write(STORAGE_KEYS.recentlyViewed, next);
}

export function getRecentlyViewed(excludeSlug?: string): RecentlyViewedEntry[] {
  const list = localStore.read<RecentlyViewedEntry[]>(STORAGE_KEYS.recentlyViewed, []);
  return excludeSlug ? list.filter((i) => i.slug !== excludeSlug) : list;
}
