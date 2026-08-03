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
