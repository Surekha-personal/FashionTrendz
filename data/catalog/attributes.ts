export const COLORS = [
  "Black",
  "White",
  "Navy",
  "Beige",
  "Olive",
  "Maroon",
  "Mustard",
  "Blush Pink",
  "Ivory",
  "Charcoal",
  "Emerald",
  "Rust",
  "Lavender",
  "Teal",
  "Camel",
  "Grey Melange",
  "Wine",
  "Sky Blue",
  "Coral",
  "Sand",
] as const;

export const CLOTHING_SIZES = ["XS", "S", "M", "L", "XL", "XXL"] as const;
export const WAIST_SIZES = ["28", "30", "32", "34", "36", "38"] as const;
export const SHOE_SIZES = ["6", "7", "8", "9", "10", "11"] as const;
export const KIDS_SIZES = [
  "2-3Y",
  "4-5Y",
  "6-7Y",
  "8-9Y",
  "10-11Y",
  "12-13Y",
] as const;
export const KIDS_SHOE_SIZES = ["8C", "10C", "12C", "1Y", "2Y", "3Y"] as const;
export const LETTER_SIZES = ["S", "M", "L"] as const;
export const RING_SIZES = ["6", "7", "8", "9", "10"] as const;
export const ONE_SIZE = ["One Size"] as const;

export const MATERIALS = [
  "Cotton",
  "Linen",
  "Silk",
  "Denim",
  "Wool",
  "Leather",
  "Polyester Blend",
  "Viscose",
  "Satin",
  "Chiffon",
  "Georgette",
  "Rayon",
  "Cotton Blend",
  "Suede",
  "Velvet",
  "Knit",
  "Nylon",
  "Canvas",
] as const;

export const OCCASIONS = [
  "Casual",
  "Formal",
  "Party",
  "Festive",
  "Wedding",
  "Sportswear",
  "Vacation",
  "Everyday",
  "Office Wear",
  "Loungewear",
] as const;

export const FITS = [
  "Regular Fit",
  "Slim Fit",
  "Relaxed Fit",
  "Oversized Fit",
  "Skinny Fit",
  "Straight Fit",
  "Tailored Fit",
  "Bodycon Fit",
] as const;

export const ADJECTIVES = [
  "Classic",
  "Relaxed",
  "Tailored",
  "Printed",
  "Embroidered",
  "Solid",
  "Striped",
  "Textured",
  "Quilted",
  "Ribbed",
  "Structured",
  "Floral",
  "Minimal",
  "Signature",
  "Everyday",
  "Premium",
  "Essential",
  "Statement",
  "Handcrafted",
  "Contemporary",
  "Draped",
  "Layered",
] as const;

export const CARE_INSTRUCTIONS = [
  "Machine wash cold, do not bleach, tumble dry low.",
  "Hand wash separately in cold water, dry in shade.",
  "Dry clean only for best results.",
  "Machine wash with like colors, iron on low heat.",
  "Wipe clean with a soft, dry cloth.",
  "Hand wash recommended, do not wring, dry flat.",
] as const;

export const RETURN_POLICIES = [
  "7-day easy returns",
  "10-day easy returns",
  "14-day easy returns",
  "15-day easy returns, no questions asked",
] as const;

// Product-type nouns that read wrong in the plural subcategory form.
const SINGULAR_OVERRIDES: Record<string, string> = {
  Dresses: "Dress",
  Tops: "Top",
  Shirts: "Shirt",
  "T-Shirts": "T-Shirt",
  Skirts: "Skirt",
  Jackets: "Jacket",
  Blazers: "Blazer",
  Sweaters: "Sweater",
  Kurtas: "Kurta",
  Sarees: "Saree",
  Necklaces: "Necklace",
  Rings: "Ring",
  Bracelets: "Bracelet",
  Bangles: "Bangle",
  Anklets: "Anklet",
  "Nose Pins": "Nose Pin",
  Handbags: "Handbag",
  "Tote Bags": "Tote Bag",
  Backpacks: "Backpack",
  Clutches: "Clutch",
  "Sling Bags": "Sling Bag",
  "Travel Bags": "Travel Bag",
  "Laptop Bags": "Laptop Bag",
  Watches: "Watch",
  Belts: "Belt",
  Wallets: "Wallet",
  "Caps & Hats": "Cap",
  Scarves: "Scarf",
  "Hair Accessories": "Hair Accessory",
  Ties: "Tie",
  Suits: "Suit",
};

export function singularNoun(subcategoryName: string) {
  return SINGULAR_OVERRIDES[subcategoryName] ?? subcategoryName;
}

export type ProductKind =
  | "apparel"
  | "bottoms"
  | "kids-apparel"
  | "footwear"
  | "kids-footwear"
  | "beauty"
  | "accessory"
  | "sized-accessory"
  | "jewellery"
  | "ring"
  | "bag";

export function sizesForKind(kind: ProductKind): readonly string[] {
  switch (kind) {
    case "apparel":
      return CLOTHING_SIZES;
    case "bottoms":
      return WAIST_SIZES;
    case "kids-apparel":
      return KIDS_SIZES;
    case "footwear":
      return SHOE_SIZES;
    case "kids-footwear":
      return KIDS_SHOE_SIZES;
    case "sized-accessory":
      return LETTER_SIZES;
    case "ring":
      return RING_SIZES;
    default:
      return ONE_SIZE;
  }
}
