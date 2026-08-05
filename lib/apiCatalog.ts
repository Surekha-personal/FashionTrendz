// Builds the query string the backend's ProductFilter (apps/products/filters.py)
// expects from the frontend's FilterState, and adapts the /products/filters/
// facets payload into the FilterFacets shape ProductFilters already renders.

import { publicGet, publicGetPaged } from "@/lib/api";
import { apiProductCardsToProducts } from "@/lib/apiAdapters";
import { PAGE_SIZE, type FilterState } from "@/lib/filters";
import type { ApiFacets, ApiProductCard } from "@/types/api";
import type { FilterFacets, Gender, SortKey } from "@/types/catalog";
import type { Product } from "@/types/product";

// The frontend's marketing genders (women/men/kids/unisex) don't line up with
// the backend's demographic field (male/female/unisex/other/undisclosed) —
// "kids" is a category on this backend, not a gender. Best-effort map; "kids"
// has no equivalent so it's dropped rather than sent as a value the API
// would silently ignore.
const GENDER_TO_API: Partial<Record<Gender, string>> = {
  women: "female",
  men: "male",
  unisex: "unisex",
};

const SORT_TO_API: Record<SortKey, string> = {
  newest: "newest",
  popularity: "popularity",
  "price-asc": "price_low",
  "price-desc": "price_high",
  discount: "discount",
  rating: "rating",
};

export function buildProductQuery(
  filters: FilterState,
  extra: Record<string, string> = {}
): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.brands.length) params.set("brand", filters.brands.join(","));
  if (filters.colors.length) params.set("color", filters.colors.join(","));
  if (filters.sizes.length) params.set("size", filters.sizes.join(","));
  if (filters.materials.length) params.set("material", filters.materials.join(","));
  if (filters.occasions.length) params.set("occasion", filters.occasions.join(","));
  const genders = filters.genders.map((g) => GENDER_TO_API[g as Gender]).filter(Boolean);
  if (genders.length) params.set("gender", genders.join(","));
  if (filters.minPrice !== undefined) params.set("min_price", String(filters.minPrice));
  if (filters.maxPrice !== undefined) params.set("max_price", String(filters.maxPrice));
  if (filters.minDiscount !== undefined) params.set("min_discount", String(filters.minDiscount));
  if (filters.minRating !== undefined) params.set("min_rating", String(filters.minRating));
  if (filters.inStockOnly) params.set("in_stock", "true");
  params.set("sort", SORT_TO_API[filters.sort] ?? "newest");
  params.set("page", String(filters.page));
  params.set("page_size", String(PAGE_SIZE));
  for (const [key, value] of Object.entries(extra)) params.set(key, value);
  return params;
}

export function apiFacetsToFilterFacets(f: ApiFacets): FilterFacets {
  return {
    brands: f.brands.map((b) => b.slug),
    colors: f.colors.map((c) => c.color),
    sizes: f.sizes.map((s) => s.size),
    // The facets endpoint doesn't enumerate genders or occasions (they're
    // fixed backend choices, not counted per result set) — offered as the
    // full static lists instead of narrowing to "what's in this result set".
    genders: ["women", "men", "unisex"],
    materials: f.materials.map((m) => m.material),
    occasions: [
      "casual",
      "formal",
      "party",
      "wedding",
      "festive",
      "sports",
      "lounge",
      "beach",
      "work",
    ],
    priceMin: Math.floor(Number(f.price.min)),
    priceMax: Math.ceil(Number(f.price.max)) || 10000,
  };
}

export interface ListingResult {
  items: Product[];
  facets: FilterFacets;
  total: number;
  page: number;
  totalPages: number;
}

export async function fetchProductListing(
  path: string,
  filters: FilterState,
  extra: Record<string, string> = {}
): Promise<ListingResult> {
  const query = buildProductQuery(filters, extra);
  const [listing, facetsRaw] = await Promise.all([
    publicGetPaged<ApiProductCard[]>(`${path}?${query.toString()}`, 30),
    publicGet<ApiFacets>(`${path}filters/?${query.toString()}`, 60).catch(
      () => null as ApiFacets | null
    ),
  ]);

  return {
    items: apiProductCardsToProducts(listing.data),
    facets: facetsRaw
      ? apiFacetsToFilterFacets(facetsRaw)
      : { brands: [], colors: [], sizes: [], genders: [], materials: [], occasions: [], priceMin: 0, priceMax: 10000 },
    total: listing.pagination?.count ?? listing.data.length,
    page: listing.pagination?.page ?? 1,
    totalPages: listing.pagination?.total_pages ?? 1,
  };
}
