import { generateProducts } from "@/data/catalog/generateProducts";
import type { Product } from "@/types/catalog";

export const products: Product[] = generateProducts();

export function getProductBySlug(slug: string): Product | undefined {
  return products.find((p) => p.slug === slug);
}

export function getProductsByCategory(categorySlug: string): Product[] {
  return products.filter((p) => p.category === categorySlug);
}

export function getProductsBySubcategory(
  categorySlug: string,
  subcategorySlug: string
): Product[] {
  return products.filter(
    (p) => p.category === categorySlug && p.subcategory === subcategorySlug
  );
}

export function getProductsOnSale(): Product[] {
  return products.filter((p) => p.discount > 0);
}

export function getRelatedProducts(product: Product, count = 8): Product[] {
  return products
    .filter(
      (p) =>
        p.id !== product.id &&
        (p.subcategory === product.subcategory || p.brandSlug === product.brandSlug)
    )
    .slice(0, count);
}

export function getRecommendedProducts(product: Product, count = 8): Product[] {
  return [...products]
    .filter(
      (p) =>
        p.id !== product.id &&
        p.category === product.category &&
        p.subcategory !== product.subcategory
    )
    .sort(
      (a, b) =>
        b.rating * Math.log(b.reviewCount + 1) -
        a.rating * Math.log(a.reviewCount + 1)
    )
    .slice(0, count);
}

export function getNewArrivals(count = 12): Product[] {
  return products.filter((p) => p.isNew).slice(0, count);
}

export function getBestSellers(count = 12): Product[] {
  return [...products].sort((a, b) => b.reviewCount - a.reviewCount).slice(0, count);
}

export function getTrending(count = 12): Product[] {
  return [...products]
    .sort(
      (a, b) =>
        b.rating * Math.log(b.reviewCount + 1) -
        a.rating * Math.log(a.reviewCount + 1)
    )
    .slice(0, count);
}

export function getTrendingThisWeek(count = 12): Product[] {
  return [...products]
    .sort((a, b) => b.discount - a.discount || b.rating - a.rating)
    .slice(count, count * 2);
}

export function getFlashSaleProducts(count = 12): Product[] {
  return [...products]
    .filter((p) => p.discount >= 30)
    .slice(0, count);
}

export * from "@/data/catalog/brands";
export * from "@/data/catalog/categories";
