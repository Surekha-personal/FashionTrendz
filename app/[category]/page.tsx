import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { ApiError, publicGet } from "@/lib/api";
import { fetchProductListing } from "@/lib/apiCatalog";
import { parseFilterState, type SearchParamsRecord } from "@/lib/filters";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ category: string }>;
  searchParams: Promise<SearchParamsRecord>;
}

interface ApiCategory {
  name: string;
  slug: string;
  subcategory_count: number;
}

async function getCategory(slug: string): Promise<ApiCategory | null> {
  if (slug === "sale") return { name: "Sale", slug: "sale", subcategory_count: 0 };
  try {
    return await publicGet<ApiCategory>(`/categories/${slug}/`, 300);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { category: categorySlug } = await params;
  const category = await getCategory(categorySlug);
  if (!category) return {};
  return {
    title: `${category.name} | Fashion Trendz`,
    description: `Shop the latest ${category.name} collection at Fashion Trendz.`,
  };
}

export default async function CategoryPage({ params, searchParams }: PageProps) {
  const { category: categorySlug } = await params;
  const category = await getCategory(categorySlug);
  if (!category) notFound();

  const sp = await searchParams;
  const state = parseFilterState(sp);
  const extra: Record<string, string> =
    categorySlug === "sale" ? { is_on_sale: "true" } : { category: categorySlug };
  const { facets, items, total, page, totalPages } = await fetchProductListing(
    "/products/",
    state,
    extra
  );

  return (
    <ProductListingLayout
      title={category.name}
      description={
        categorySlug === "sale"
          ? "Discounted picks across every category, updated daily."
          : `Explore ${category.subcategory_count}+ styles across ${category.name.toLowerCase()}.`
      }
      breadcrumbs={[{ label: "Home", href: "/" }, { label: category.name }]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath={`/${categorySlug}`}
      searchParams={sp}
    />
  );
}
