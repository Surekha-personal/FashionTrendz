export interface ProductVariantOption {
  sku: string;
  color: string;
  colorCode?: string;
  size: string;
  availableStock: number;
}

export interface Product {
  id: string;
  slug: string;
  name: string;
  brand: string;
  price: number;
  compareAtPrice?: number;
  image: string;
  hoverImage?: string;
  imageAlt: string;
  rating?: number;
  reviewCount?: number;
  isNew?: boolean;
  sizes?: string[];
  colors?: string[];
  stock?: number;
  description?: string;
  // Present once a product's full detail/quick-view payload has loaded from
  // the API. Listing cards don't carry this — the backend keeps card
  // responses lean — so it's undefined until ProductCard's quick view or the
  // PDP fetches the detail endpoint.
  variants?: ProductVariantOption[];
}
