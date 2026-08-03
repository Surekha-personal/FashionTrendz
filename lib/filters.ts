import type { FilterFacets, Gender, Product, SortKey } from "@/types/catalog";

export type SearchParamsRecord = Record<string, string | string[] | undefined>;

export interface FilterState {
  brands: string[];
  colors: string[];
  sizes: string[];
  genders: string[];
  materials: string[];
  occasions: string[];
  minPrice?: number;
  maxPrice?: number;
  minDiscount?: number;
  minRating?: number;
  inStockOnly: boolean;
  sort: SortKey;
  page: number;
}

export const PAGE_SIZE = 24;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function csv(value: string | string[] | undefined): string[] {
  const v = first(value);
  return v ? v.split(",").filter(Boolean) : [];
}

const SORT_KEYS: SortKey[] = [
  "newest",
  "popularity",
  "price-asc",
  "price-desc",
  "discount",
  "rating",
];

export function parseFilterState(params: SearchParamsRecord): FilterState {
  const sortParam = first(params.sort);
  const sort = SORT_KEYS.includes(sortParam as SortKey)
    ? (sortParam as SortKey)
    : "newest";

  const minPrice = first(params.minPrice);
  const maxPrice = first(params.maxPrice);
  const minDiscount = first(params.minDiscount);
  const minRating = first(params.minRating);
  const page = Number(first(params.page)) || 1;

  return {
    brands: csv(params.brand),
    colors: csv(params.color),
    sizes: csv(params.size),
    genders: csv(params.gender),
    materials: csv(params.material),
    occasions: csv(params.occasion),
    minPrice: minPrice ? Number(minPrice) : undefined,
    maxPrice: maxPrice ? Number(maxPrice) : undefined,
    minDiscount: minDiscount ? Number(minDiscount) : undefined,
    minRating: minRating ? Number(minRating) : undefined,
    inStockOnly: first(params.inStock) === "1",
    sort,
    page: page > 0 ? page : 1,
  };
}

export function applyFilters(products: Product[], state: FilterState): Product[] {
  return products.filter((p) => {
    if (state.brands.length && !state.brands.includes(p.brandSlug)) return false;
    if (state.colors.length && !p.colors.some((c) => state.colors.includes(c)))
      return false;
    if (state.sizes.length && !p.sizes.some((s) => state.sizes.includes(s)))
      return false;
    if (state.genders.length && !state.genders.includes(p.gender)) return false;
    if (state.materials.length && !state.materials.includes(p.material))
      return false;
    if (state.occasions.length && !state.occasions.includes(p.occasion))
      return false;
    if (state.minPrice !== undefined && p.discountedPrice < state.minPrice)
      return false;
    if (state.maxPrice !== undefined && p.discountedPrice > state.maxPrice)
      return false;
    if (state.minDiscount !== undefined && p.discount < state.minDiscount)
      return false;
    if (state.minRating !== undefined && p.rating < state.minRating) return false;
    if (state.inStockOnly && p.stock <= 0) return false;
    return true;
  });
}

export function sortProducts(products: Product[], sort: SortKey): Product[] {
  const list = [...products];
  switch (sort) {
    case "price-asc":
      return list.sort((a, b) => a.discountedPrice - b.discountedPrice);
    case "price-desc":
      return list.sort((a, b) => b.discountedPrice - a.discountedPrice);
    case "discount":
      return list.sort((a, b) => b.discount - a.discount);
    case "rating":
      return list.sort((a, b) => b.rating - a.rating);
    case "popularity":
      return list.sort((a, b) => b.reviewCount - a.reviewCount);
    case "newest":
    default:
      return list.sort((a, b) => Number(b.isNew) - Number(a.isNew));
  }
}

export function paginate(products: Product[], page: number) {
  const totalPages = Math.max(1, Math.ceil(products.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * PAGE_SIZE;
  return {
    items: products.slice(start, start + PAGE_SIZE),
    page: safePage,
    totalPages,
    total: products.length,
  };
}

export function computeFacets(products: Product[]): FilterFacets {
  const brands = new Set<string>();
  const colors = new Set<string>();
  const sizes = new Set<string>();
  const genders = new Set<Gender>();
  const materials = new Set<string>();
  const occasions = new Set<string>();
  let priceMin = Infinity;
  let priceMax = 0;

  for (const p of products) {
    brands.add(p.brandSlug);
    p.colors.forEach((c) => colors.add(c));
    p.sizes.forEach((s) => sizes.add(s));
    genders.add(p.gender);
    materials.add(p.material);
    occasions.add(p.occasion);
    priceMin = Math.min(priceMin, p.discountedPrice);
    priceMax = Math.max(priceMax, p.discountedPrice);
  }

  return {
    brands: [...brands].sort(),
    colors: [...colors].sort(),
    sizes: [...sizes],
    genders: [...genders].sort(),
    materials: [...materials].sort(),
    occasions: [...occasions].sort(),
    priceMin: Number.isFinite(priceMin) ? priceMin : 0,
    priceMax: priceMax || 0,
  };
}

export function filterAndSort(
  products: Product[],
  params: SearchParamsRecord
) {
  const state = parseFilterState(params);
  const facets = computeFacets(products);
  const filtered = sortProducts(applyFilters(products, state), state.sort);
  const paged = paginate(filtered, state.page);
  return { state, facets, ...paged };
}
