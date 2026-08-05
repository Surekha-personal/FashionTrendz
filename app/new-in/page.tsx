import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { fetchProductListing } from "@/lib/apiCatalog";
import { parseFilterState, type SearchParamsRecord } from "@/lib/filters";

export const metadata: Metadata = {
  title: "New In | Fashion Trendz",
  description: "The newest arrivals across every category at Fashion Trendz.",
};

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<SearchParamsRecord>;
}

export default async function NewInPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const state = parseFilterState(sp);
  const { facets, items, total, page, totalPages } = await fetchProductListing(
    "/products/",
    state,
    { is_new_arrival: "true" }
  );

  return (
    <ProductListingLayout
      title="New In"
      description="Fresh drops from across Fashion Trendz, updated every week."
      breadcrumbs={[{ label: "Home", href: "/" }, { label: "New In" }]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath="/new-in"
      searchParams={sp}
    />
  );
}
