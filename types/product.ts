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
}
