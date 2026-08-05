import { NextResponse } from "next/server";
import { publicGet, publicGetPaged } from "@/lib/api";
import type { ApiProductCard, ApiSearchSuggestions } from "@/types/api";

// Thin server-side proxy: reshapes the backend's suggestions + ranked search
// endpoints into the {products, brands, categories} shape SearchBar already
// renders (product thumbnails need the full product-card payload, which the
// lightweight /products/suggestions/ endpoint doesn't carry).
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q") ?? "";

  if (!q.trim()) {
    return NextResponse.json({ products: [], brands: [], categories: [] });
  }

  const [suggestions, searchResults] = await Promise.all([
    publicGet<ApiSearchSuggestions>(`/products/suggestions/?q=${encodeURIComponent(q)}`, 30).catch(
      () => ({ products: [], brands: [], categories: [] }) as ApiSearchSuggestions
    ),
    publicGetPaged<ApiProductCard[]>(`/products/search/?q=${encodeURIComponent(q)}&page_size=6`, 30).catch(
      () => ({ data: [] as ApiProductCard[], pagination: undefined })
    ),
  ]);

  return NextResponse.json({
    products: searchResults.data.slice(0, 6).map((p) => ({
      slug: p.slug,
      title: p.name,
      brand: p.brand?.name ?? "",
      image: p.primary_image?.image ?? "/placeholder-product.svg",
      price: Number(p.selling_price),
    })),
    brands: suggestions.brands.slice(0, 4).map((b) => ({ name: b.label, slug: b.slug })),
    categories: suggestions.categories.slice(0, 4).map((c) => ({
      label: c.label,
      href: `/search?q=${encodeURIComponent(c.label)}`,
    })),
  });
}
