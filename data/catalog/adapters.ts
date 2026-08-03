import type { Product as CatalogProduct } from "@/types/catalog";
import type { Product as CardProduct } from "@/types/product";

// Bridges the rich catalog model to the ProductCard view model so
// ProductCard (and everything built on it) stays untouched.
export function toCardProduct(p: CatalogProduct): CardProduct {
  return {
    id: p.id,
    slug: p.slug,
    name: p.title,
    brand: p.brand,
    price: p.discountedPrice,
    compareAtPrice: p.discount > 0 ? p.price : undefined,
    image: p.images[0],
    hoverImage: p.images[1],
    imageAlt: `${p.title} by ${p.brand}`,
    rating: p.rating,
    reviewCount: p.reviewCount,
    isNew: p.isNew,
    sizes: p.sizes,
    colors: p.colors,
    stock: p.stock,
    description: p.description,
  };
}

export function toCardProducts(list: CatalogProduct[]): CardProduct[] {
  return list.map(toCardProduct);
}
