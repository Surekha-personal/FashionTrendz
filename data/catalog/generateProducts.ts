import { slugify } from "@/utils/format";
import { mulberry32, pick, pickMany, intBetween } from "@/lib/rng";
import { brands } from "@/data/catalog/brands";
import { categories } from "@/data/catalog/categories";
import { imageAt } from "@/data/catalog/imagePool";
import { BEAUTY_PRODUCTS, BEAUTY_ADJECTIVES } from "@/data/catalog/beautyWords";
import {
  COLORS,
  MATERIALS,
  OCCASIONS,
  FITS,
  ADJECTIVES,
  CARE_INSTRUCTIONS,
  RETURN_POLICIES,
  singularNoun,
  sizesForKind,
  type ProductKind,
} from "@/data/catalog/attributes";
import type { Gender, Product, Subcategory } from "@/types/catalog";

const PRODUCTS_PER_SUBCATEGORY = 8;

const KIND_MATERIALS: Partial<Record<ProductKind, readonly string[]>> = {
  footwear: ["Leather", "Suede", "Canvas", "Synthetic Leather", "Mesh"],
  "kids-footwear": ["Canvas", "Synthetic Leather", "Mesh"],
  bag: ["Leather", "Canvas", "Synthetic Leather", "Nylon", "Suede"],
  jewellery: [
    "Gold Plated",
    "Silver Plated",
    "Oxidized Metal",
    "Stainless Steel",
    "Rose Gold Plated",
  ],
  ring: ["Gold Plated", "Silver Plated", "Stainless Steel", "Alloy"],
  accessory: ["Metal", "Acetate", "Leather", "Cotton", "Polyester"],
  "sized-accessory": ["Leather", "Cotton", "Wool Blend"],
};

function kindForSubcategory(categorySlug: string, subName: string): ProductKind {
  if (categorySlug === "beauty") return "beauty";
  if (categorySlug === "jewellery") return subName === "Rings" ? "ring" : "jewellery";
  if (categorySlug === "bags") return "bag";
  if (categorySlug === "accessories") {
    return subName === "Belts" || subName === "Gloves" ? "sized-accessory" : "accessory";
  }
  if (categorySlug === "footwear") return "footwear";
  if (categorySlug === "kids") {
    if (subName === "Footwear") return "kids-footwear";
    if (subName === "Toys & Accessories") return "accessory";
    return "kids-apparel";
  }
  if (categorySlug === "luxury") {
    if (subName.includes("Bag")) return "bag";
    if (subName.includes("Watch")) return "accessory";
    if (subName.includes("Jewellery")) return "jewellery";
    return "apparel";
  }
  return subName === "Jeans" || subName === "Trousers" ? "bottoms" : "apparel";
}

function genderFor(categorySlug: string, subName: string): Gender {
  switch (categorySlug) {
    case "women":
      return "women";
    case "men":
      return "men";
    case "kids":
      return "kids";
    case "beauty":
      return subName === "Men's Grooming" ? "men" : "unisex";
    case "accessories":
      if (subName === "Ties") return "men";
      if (subName === "Hair Accessories") return "women";
      return "unisex";
    case "jewellery":
      return "women";
    case "luxury":
      return subName.includes("Dress") ||
        subName === "Designer Wear" ||
        subName === "Luxury Jewellery"
        ? "women"
        : "unisex";
    default:
      return "unisex";
  }
}

function priceRangeFor(kind: ProductKind, luxury: boolean): [number, number] {
  const base: [number, number] = (() => {
    switch (kind) {
      case "kids-apparel":
        return [499, 2499];
      case "kids-footwear":
        return [799, 2999];
      case "footwear":
        return [1499, 6999];
      case "beauty":
        return [299, 2499];
      case "accessory":
      case "sized-accessory":
        return [499, 3999];
      case "jewellery":
      case "ring":
        return [599, 4999];
      case "bag":
        return [1499, 7999];
      case "bottoms":
        return [1299, 3999];
      default:
        return [999, 4999];
    }
  })();
  return luxury ? [base[0] * 3, base[1] * 4] : base;
}

function buildTitle(
  rng: () => number,
  kind: ProductKind,
  subName: string
): string {
  if (kind === "beauty") {
    const options = BEAUTY_PRODUCTS[subName] ?? ["Beauty Essential"];
    return `${pick(rng, BEAUTY_ADJECTIVES)} ${pick(rng, options)}`;
  }
  const noun = singularNoun(subName);
  const adjective = pick(rng, ADJECTIVES);
  const includesMaterial =
    kind === "apparel" || kind === "bottoms" || kind === "kids-apparel";
  if (includesMaterial) {
    const material = pick(rng, MATERIALS);
    return `${adjective} ${material} ${noun}`;
  }
  return `${adjective} ${noun}`;
}

function buildDescription(
  title: string,
  material: string,
  occasion: string,
  fit: string,
  kind: ProductKind
): string {
  if (kind === "beauty") {
    return `${title} formulated to fit effortlessly into your everyday routine, gentle enough for regular use and made to deliver visible results.`;
  }
  const fitClause = fit === "N/A" ? "" : ` with a ${fit.toLowerCase()} silhouette`;
  const article = /^[aeiou]/i.test(title) ? "An" : "A";
  return `${article} ${title.toLowerCase()} crafted from ${material.toLowerCase()}, designed for ${occasion.toLowerCase()} wear${fitClause}.`;
}

export function generateProducts(): Product[] {
  const products: Product[] = [];
  let globalIndex = 0;

  for (const category of categories) {
    for (const sub of category.subcategories as Subcategory[]) {
      const kind = kindForSubcategory(category.slug, sub.name);
      const gender = genderFor(category.slug, sub.name);
      const isLuxury = category.slug === "luxury";
      const [minPrice, maxPrice] = priceRangeFor(kind, isLuxury);
      const sizes = [...sizesForKind(kind)];
      const materialPool = KIND_MATERIALS[kind] ?? MATERIALS;

      for (let i = 0; i < PRODUCTS_PER_SUBCATEGORY; i++) {
        const seed = category.slug.length * 97 + sub.slug.length * 31 + globalIndex * 7919 + 13;
        const rng = mulberry32(seed);

        const brand = pick(rng, brands);
        const title = buildTitle(rng, kind, sub.name);
        const material = kind === "beauty" ? "N/A" : pick(rng, materialPool);
        const occasion = pick(rng, OCCASIONS);
        const fit =
          kind === "apparel" || kind === "bottoms" || kind === "kids-apparel"
            ? pick(rng, FITS)
            : kind === "footwear" || kind === "kids-footwear"
              ? "True to Size"
              : "N/A";

        const price = Math.round(intBetween(rng, minPrice, maxPrice) / 10) * 10;
        const hasDiscount = rng() < 0.45;
        const discount = hasDiscount
          ? pick(rng, [10, 15, 20, 25, 30, 35, 40, 50])
          : 0;
        const discountedPrice = discount
          ? Math.round((price * (1 - discount / 100)) / 10) * 10
          : price;

        const rating = Math.round((3.5 + rng() * 1.5) * 10) / 10;
        const reviewCount = intBetween(rng, 5, 480);
        const stock = rng() < 0.06 ? 0 : intBetween(rng, 3, 150);
        const colors = pickMany(rng, COLORS, intBetween(rng, 1, 4));
        const imageBase = globalIndex * 3 + category.slug.length;
        const images = Array.from({ length: 4 }, (_, i2) =>
          imageAt(imageBase + i2 * 5, 900)
        );

        const description = buildDescription(title, material, occasion, fit, kind);
        const slug = `${slugify(`${brand.name}-${title}`)}-${globalIndex}`;

        products.push({
          id: `prod-${globalIndex}`,
          slug,
          title,
          brand: brand.name,
          brandSlug: brand.slug,
          category: category.slug,
          categoryName: category.name,
          subcategory: sub.slug,
          subcategoryName: sub.name,
          gender,
          description,
          price,
          discount,
          discountedPrice,
          rating,
          reviewCount,
          stock,
          sizes,
          colors,
          images,
          material,
          fit,
          occasion,
          careInstructions: pick(rng, CARE_INSTRUCTIONS),
          deliveryDays: intBetween(rng, 2, 7),
          returnPolicy: pick(rng, RETURN_POLICIES),
          tags: [
            category.slug,
            sub.slug,
            gender,
            occasion.toLowerCase(),
            brand.slug,
            ...(discount > 0 ? ["sale"] : []),
          ],
          isNew: rng() < 0.15,
        });

        globalIndex++;
      }
    }
  }

  return products;
}
