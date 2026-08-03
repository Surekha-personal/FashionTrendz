import { brands } from "@/data/catalog/brands";
import { categories } from "@/data/catalog/categories";
import type { Product } from "@/types/catalog";

export const POPULAR_SEARCHES = [
  "Dresses",
  "Sneakers",
  "Sarees",
  "Handbags",
  "Sunglasses",
  "Jeans",
  "Kurtas",
  "Watches",
  "Jackets",
  "Jewellery",
];

function normalize(value: string) {
  return value.toLowerCase().trim();
}

export function searchProducts(query: string, products: Product[]): Product[] {
  const q = normalize(query);
  if (!q) return [];

  const scored = products
    .map((p) => {
      const title = normalize(p.title);
      const brand = normalize(p.brand);
      const category = normalize(p.categoryName);
      const subcategory = normalize(p.subcategoryName);
      let score = 0;
      if (title.startsWith(q)) score += 6;
      else if (title.includes(q)) score += 4;
      if (brand.includes(q)) score += 3;
      if (subcategory.includes(q)) score += 2;
      if (category.includes(q)) score += 1;
      if (p.tags.some((t) => t.includes(q))) score += 1;
      return { p, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);

  return scored.map((entry) => entry.p);
}

export interface CategoryMatch {
  label: string;
  href: string;
}

export function searchBrandsByQuery(query: string, limit = 5) {
  const q = normalize(query);
  if (!q) return [];
  return brands.filter((b) => normalize(b.name).includes(q)).slice(0, limit);
}

export function searchCategoriesByQuery(query: string, limit = 5): CategoryMatch[] {
  const q = normalize(query);
  if (!q) return [];
  const matches: CategoryMatch[] = [];

  for (const category of categories) {
    if (normalize(category.name).includes(q)) {
      matches.push({ label: category.name, href: `/${category.slug}` });
    }
    for (const sub of category.subcategories) {
      if (normalize(sub.name).includes(q)) {
        matches.push({
          label: `${sub.name} in ${category.name}`,
          href: `/${category.slug}/${sub.slug}`,
        });
      }
    }
    if (matches.length >= limit) break;
  }

  return matches.slice(0, limit);
}
