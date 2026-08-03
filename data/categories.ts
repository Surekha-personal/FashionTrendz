import { allCategories } from "@/data/catalog/categories";
import type { Category } from "@/types/home";

export const categories: Category[] = allCategories.map((c) => ({
  id: c.id,
  name: c.name,
  href: `/${c.slug}`,
  image: c.image,
  imageAlt: c.imageAlt,
}));
