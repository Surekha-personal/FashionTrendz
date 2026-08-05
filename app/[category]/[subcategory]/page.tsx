import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { ApiError, publicGet } from "@/lib/api";
import { fetchProductListing } from "@/lib/apiCatalog";
import { parseFilterState, type SearchParamsRecord } from "@/lib/filters";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ category: string; subcategory: string }>;
  searchParams: Promise<SearchParamsRecord>;
}

interface ApiSubcategory {
  name: string;
  slug: string;
  category: { name: string; slug: string };
}

// Sale sub-pages are curated filter presets rather than real subcategories —
// each maps onto plain ProductFilter query params the backend already knows.
const SALE_PRESETS: Record<string, { label: string; extra: Record<string, string> }> = {
  clearance: { label: "Clearance", extra: { min_discount: "40" } },
  "under-999": { label: "Under ₹999", extra: { max_price: "999" } },
  "under-1999": { label: "Under ₹1,999", extra: { max_price: "1999" } },
  "flat-50-off": { label: "Flat 50% Off", extra: { min_discount: "50" } },
  "last-few-left": { label: "Last Few Left", extra: { availability: "low_stock" } },
};

async function getSubcategory(categorySlug: string, subSlug: string): Promise<ApiSubcategory | null> {
  try {
    const sub = await publicGet<ApiSubcategory>(`/subcategories/${subSlug}/`, 300);
    return sub.category.slug === categorySlug ? sub : null;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { category: categorySlug, subcategory: subSlug } = await params;
  if (categorySlug === "sale") {
    const preset = SALE_PRESETS[subSlug];
    return preset ? { title: `${preset.label} | Sale | Fashion Trendz` } : {};
  }
  const sub = await getSubcategory(categorySlug, subSlug);
  if (!sub) return {};
  return {
    title: `${sub.name} | ${sub.category.name} | Fashion Trendz`,
    description: `Shop ${sub.name} in ${sub.category.name} at Fashion Trendz.`,
  };
}

export default async function SubcategoryPage({ params, searchParams }: PageProps) {
  const { category: categorySlug, subcategory: subSlug } = await params;
  const sp = await searchParams;
  const state = parseFilterState(sp);

  if (categorySlug === "sale") {
    const preset = SALE_PRESETS[subSlug];
    if (!preset) notFound();
    const { facets, items, total, page, totalPages } = await fetchProductListing(
      "/products/",
      state,
      { is_on_sale: "true", ...preset.extra }
    );
    return (
      <ProductListingLayout
        title={preset.label}
        description="Discounted picks across every category, updated daily."
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Sale", href: "/sale" },
          { label: preset.label },
        ]}
        products={items}
        facets={facets}
        total={total}
        page={page}
        totalPages={totalPages}
        basePath={`/sale/${subSlug}`}
        searchParams={sp}
      />
    );
  }

  const sub = await getSubcategory(categorySlug, subSlug);
  if (!sub) notFound();

  const { facets, items, total, page, totalPages } = await fetchProductListing(
    "/products/",
    state,
    { subcategory: subSlug }
  );

  return (
    <ProductListingLayout
      title={sub.name}
      description={`${sub.category.name} · ${sub.name}`}
      breadcrumbs={[
        { label: "Home", href: "/" },
        { label: sub.category.name, href: `/${sub.category.slug}` },
        { label: sub.name },
      ]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath={`/${sub.category.slug}/${sub.slug}`}
      searchParams={sp}
    />
  );
}
