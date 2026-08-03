import { mulberry32, pick, intBetween } from "@/lib/rng";
import type { Product, Review } from "@/types/catalog";

const REVIEWER_NAMES = [
  "Ananya Rao",
  "Kabir Malhotra",
  "Meera Iyer",
  "Rohan Verma",
  "Simran Kaur",
  "Aditya Nair",
  "Priya Sharma",
  "Arjun Reddy",
  "Neha Kapoor",
  "Vikram Singh",
  "Ishita Bose",
  "Karan Mehta",
  "Divya Menon",
  "Sahil Khanna",
  "Riya Desai",
  "Aman Gupta",
];

const POSITIVE_TITLES = [
  "Exceeded expectations",
  "Great quality for the price",
  "Fits perfectly",
  "Exactly as described",
  "Would buy again",
  "Fast delivery, great product",
];

const MIXED_TITLES = [
  "Good but runs slightly small",
  "Decent quality",
  "Nice but delivery took longer",
  "Good value overall",
];

const POSITIVE_BODIES = [
  "The fabric quality is much better than I expected at this price point. Fits true to size.",
  "Loved the finish and detailing. Looks even better in person than in the photos.",
  "This has become a staple in my wardrobe already. Comfortable and well-stitched.",
  "Packaging was premium and the product matched the description perfectly.",
  "Ordered a size up as suggested and the fit is spot on. Highly recommend.",
];

const MIXED_BODIES = [
  "Quality is good but I'd recommend checking the size chart carefully before ordering.",
  "Product is decent, took a couple of days longer to arrive than expected.",
  "Color is slightly different from the pictures but overall satisfied with the purchase.",
  "Good for the price, though the material feels a bit thinner than anticipated.",
];

export function getReviewsForProduct(product: Product): Review[] {
  const rng = mulberry32(product.id.length * 131 + product.slug.length * 17 + 7);
  const count = Math.min(6, Math.max(2, Math.round(product.reviewCount / 40)));

  return Array.from({ length: count }, (_, i) => {
    const positive = rng() > 0.25;
    const rating = positive ? intBetween(rng, 4, 5) : intBetween(rng, 3, 4);
    const daysAgo = intBetween(rng, 2, 240);
    const date = new Date(Date.now() - daysAgo * 86_400_000)
      .toISOString()
      .slice(0, 10);

    return {
      id: `${product.id}-review-${i}`,
      author: pick(rng, REVIEWER_NAMES),
      rating,
      title: positive ? pick(rng, POSITIVE_TITLES) : pick(rng, MIXED_TITLES),
      body: positive ? pick(rng, POSITIVE_BODIES) : pick(rng, MIXED_BODIES),
      date,
      verified: rng() > 0.2,
    };
  });
}
