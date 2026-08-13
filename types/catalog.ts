export type Gender = "women" | "men" | "kids" | "unisex";

export interface Brand {
  id: string;
  name: string;
  slug: string;
}

export interface Subcategory {
  name: string;
  slug: string;
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  image: string;
  imageAlt: string;
  subcategories: Subcategory[];
}

export interface Review {
  id: string;
  author: string;
  rating: number;
  title: string;
  body: string;
  date: string;
  verified: boolean;
}

export interface Product {
  id: string;
  slug: string;
  title: string;
  brand: string;
  brandSlug: string;
  category: string;
  categoryName: string;
  subcategory: string;
  subcategoryName: string;
  gender: Gender;
  description: string;
  price: number;
  discount: number;
  discountedPrice: number;
  rating: number;
  reviewCount: number;
  stock: number;
  sizes: string[];
  colors: string[];
  images: string[];
  material: string;
  fit: string;
  occasion: string;
  careInstructions: string;
  deliveryDays: number;
  returnPolicy: string;
  tags: string[];
  isNew: boolean;
}

export interface FilterFacets {
  brands: string[];
  colors: string[];
  sizes: string[];
  genders: Gender[];
  materials: string[];
  occasions: string[];
  priceMin: number;
  priceMax: number;
  // Backend-facet brand slug -> display name (e.g. /products/filters/ already
  // returns {name, slug, product_count} per brand). Optional so the older
  // client-side computeFacets() in lib/filters.ts, which has no names to
  // offer, doesn't need to supply it.
  brandNames?: Record<string, string>;
}

export type SortKey =
  | "newest"
  | "popularity"
  | "price-asc"
  | "price-desc"
  | "discount"
  | "rating";
