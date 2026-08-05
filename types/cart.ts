export interface CartLine {
  lineId: string;
  productId: string;
  slug: string;
  name: string;
  brand: string;
  image: string;
  price: number;
  discountedPrice: number;
  size?: string;
  color?: string;
  quantity: number;
  savedForLater: boolean;
}

export interface AddToCartInput {
  productId: string;
  slug: string;
  name: string;
  brand: string;
  image: string;
  price: number;
  discountedPrice: number;
  size?: string;
  color?: string;
  quantity?: number;
  // SKU of the chosen variant. Required by the backend cart (a line is a
  // colour/size variant, not a bare product) — ProductOptions resolves this
  // from the product's variants before calling addToCart.
  variantSku?: string;
}

export interface WishlistLine {
  productId: string;
  slug: string;
  name: string;
  brand: string;
  image: string;
  price: number;
  discountedPrice: number;
  addedAt: number;
}
