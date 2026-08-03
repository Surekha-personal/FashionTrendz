import { NextResponse } from "next/server";
import { products } from "@/data/catalog";
import {
  searchBrandsByQuery,
  searchCategoriesByQuery,
  searchProducts,
} from "@/lib/search";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q") ?? "";

  if (!q.trim()) {
    return NextResponse.json({ products: [], brands: [], categories: [] });
  }

  const matchedProducts = searchProducts(q, products)
    .slice(0, 6)
    .map((p) => ({
      slug: p.slug,
      title: p.title,
      brand: p.brand,
      image: p.images[0],
      price: p.discountedPrice,
    }));

  return NextResponse.json({
    products: matchedProducts,
    brands: searchBrandsByQuery(q, 4),
    categories: searchCategoriesByQuery(q, 4),
  });
}
