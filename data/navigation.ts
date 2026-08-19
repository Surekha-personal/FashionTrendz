import { categories, saleCategory } from "@/data/catalog/categories";
import type { NavItem, MegaMenuColumn } from "@/types/navigation";
import type { Category } from "@/types/catalog";

function chunk<T>(items: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    result.push(items.slice(i, i + size));
  }
  return result;
}

function columnsFor(category: Category): MegaMenuColumn[] {
  const columnCount = category.subcategories.length > 10 ? 3 : 2;
  const size = Math.ceil(category.subcategories.length / columnCount);
  return chunk(category.subcategories, size).map((group, i) => ({
    heading: i === 0 ? "Shop By Type" : i === 1 ? "Popular Picks" : "More",
    links: group.map((sub) => ({
      label: sub.name,
      href: `/${category.slug}/${sub.slug}`,
    })),
  }));
}

function navItemFor(category: Category): NavItem {
  return {
    label: category.name,
    href: `/${category.slug}`,
    columns: columnsFor(category),
    featured: [
      {
        label: `New In ${category.name}`,
        href: `/${category.slug}?sort=newest`,
        image: category.image,
        imageAlt: `${category.name} new arrivals`,
      },
      {
        label: `Trending in ${category.name}`,
        href: `/${category.slug}?sort=popularity`,
        image: category.image,
        imageAlt: `${category.name} trending picks`,
      },
    ],
  };
}

export const mainNav: NavItem[] = [
  ...categories.map(navItemFor),
  { label: saleCategory.name, href: `/${saleCategory.slug}` },
];
