import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { fetchProductListing } from "@/lib/apiCatalog";
import { parseFilterState, type SearchParamsRecord } from "@/lib/filters";

export const metadata: Metadata = {
  title: "Search | Fashion Trendz",
};

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<SearchParamsRecord>;
}

export default async function SearchPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const query = Array.isArray(sp.q) ? sp.q[0] : (sp.q ?? "");
  const state = parseFilterState(sp);

  // The sidebar filters compose with free text through the same ProductFilter
  // (?q= narrows, doesn't rank) — using it here keeps facets, sort and
  // pagination consistent with every other listing page instead of juggling
  // the separate ranked /products/search/ endpoint.
  const { items, facets, page, totalPages, total } = await fetchProductListing(
    "/products/",
    state,
    query.trim() ? { q: query.trim() } : {}
  );

  return (
    <ProductListingLayout
      title={query ? `Results for "${query}"` : "Search Fashion Trendz"}
      description={
        query
          ? `${total} ${total === 1 ? "product" : "products"} found`
          : "Search across products, brands and categories."
      }
      breadcrumbs={[{ label: "Home", href: "/" }, { label: "Search" }]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath="/search"
      searchParams={sp}
      emptyMessage={
        query
          ? `No results for "${query}". Try a different keyword or clear filters.`
          : "Type in the search bar above to find products, brands and categories."
      }
    />
  );
}
