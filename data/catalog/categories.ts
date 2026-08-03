import { slugify } from "@/utils/format";
import { imageAt } from "@/data/catalog/imagePool";
import type { Category, Subcategory } from "@/types/catalog";

function subs(names: string[]): Subcategory[] {
  return names.map((name) => ({ name, slug: slugify(name) }));
}

interface CategorySeed {
  name: string;
  imageIndex: number;
  subcategories: string[];
}

const CATEGORY_SEEDS: CategorySeed[] = [
  {
    name: "Women",
    imageIndex: 0,
    subcategories: [
      "Dresses",
      "Tops",
      "Shirts",
      "T-Shirts",
      "Jeans",
      "Trousers",
      "Skirts",
      "Co-ords",
      "Ethnic Wear",
      "Sarees",
      "Kurtas",
      "Jackets",
      "Blazers",
      "Loungewear",
      "Nightwear",
      "Sportswear",
    ],
  },
  {
    name: "Men",
    imageIndex: 9,
    subcategories: [
      "T-Shirts",
      "Shirts",
      "Jeans",
      "Trousers",
      "Shorts",
      "Jackets",
      "Blazers",
      "Ethnic Wear",
      "Kurtas",
      "Sportswear",
      "Innerwear",
      "Sweaters",
      "Suits",
      "Nightwear",
    ],
  },
  {
    name: "Kids",
    imageIndex: 12,
    subcategories: [
      "Boys Clothing",
      "Girls Clothing",
      "Infant Wear",
      "School Uniforms",
      "Ethnic Wear",
      "Winter Wear",
      "Footwear",
      "Toys & Accessories",
    ],
  },
  {
    name: "Beauty",
    imageIndex: 13,
    subcategories: [
      "Skincare",
      "Makeup",
      "Haircare",
      "Fragrance",
      "Bath & Body",
      "Tools & Brushes",
      "Men's Grooming",
      "Wellness",
    ],
  },
  {
    name: "Accessories",
    imageIndex: 14,
    subcategories: [
      "Sunglasses",
      "Watches",
      "Belts",
      "Wallets",
      "Caps & Hats",
      "Scarves",
      "Hair Accessories",
      "Ties",
      "Gloves",
    ],
  },
  {
    name: "Footwear",
    imageIndex: 15,
    subcategories: [
      "Sneakers",
      "Heels",
      "Flats",
      "Sandals",
      "Boots",
      "Formal Shoes",
      "Sports Shoes",
      "Flip Flops",
    ],
  },
  {
    name: "Bags",
    imageIndex: 16,
    subcategories: [
      "Handbags",
      "Tote Bags",
      "Backpacks",
      "Clutches",
      "Sling Bags",
      "Travel Bags",
      "Laptop Bags",
      "Wallets",
    ],
  },
  {
    name: "Jewellery",
    imageIndex: 17,
    subcategories: [
      "Necklaces",
      "Earrings",
      "Rings",
      "Bracelets",
      "Bangles",
      "Anklets",
      "Jewellery Sets",
      "Nose Pins",
    ],
  },
  {
    name: "Luxury",
    imageIndex: 18,
    subcategories: [
      "Luxury Dresses",
      "Luxury Bags",
      "Luxury Watches",
      "Luxury Jewellery",
      "Designer Wear",
      "Limited Edition",
    ],
  },
];

export const categories: Category[] = CATEGORY_SEEDS.map((seed) => {
  const slug = slugify(seed.name);
  return {
    id: `cat-${slug}`,
    name: seed.name,
    slug,
    image: imageAt(seed.imageIndex, 700),
    imageAlt: `${seed.name} collection`,
    subcategories: subs(seed.subcategories),
  };
});

// Sale is a cross-cutting discount view, not a product-owning category.
export const saleCategory: Category = {
  id: "cat-sale",
  name: "Sale",
  slug: "sale",
  image: imageAt(2, 700),
  imageAlt: "Sale collection",
  subcategories: subs([
    "Clearance",
    "Under ₹999",
    "Under ₹1999",
    "Flat 50% Off",
    "Last Few Left",
  ]),
};

export const allCategories: Category[] = [...categories, saleCategory];

export function getCategoryBySlug(slug: string) {
  return allCategories.find((c) => c.slug === slug);
}

export function getSubcategoryBySlug(categorySlug: string, subSlug: string) {
  const category = getCategoryBySlug(categorySlug);
  return category?.subcategories.find((s) => s.slug === subSlug);
}
