import { brands as catalogBrands } from "@/data/catalog/brands";
import type { Brand } from "@/types/home";

export const brands: Brand[] = catalogBrands.slice(0, 12).map((b) => ({
  id: b.id,
  name: b.name,
  href: `/search?brand=${b.slug}`,
}));
