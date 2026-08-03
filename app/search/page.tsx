import type { Metadata } from "next";
import { products } from "@/data/catalog";
import { searchProducts } from "@/lib/search";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import {
  applyFilters,
  computeFacets,
  paginate,
  parseFilterState,
  sortProducts,
  type SearchParamsRecord,
} from "@/lib/filters";

export const metadata: Metadata = {
  title: "Search | Fashion Trendz",
};

interface PageProps {
  searchParams: Promise<SearchParamsRecord>;
}

export default async function SearchPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const query = Array.isArray(sp.q) ? sp.q[0] : (sp.q ?? "");

  const base = query.trim() ? searchProducts(query, products) : products;
  const state = parseFilterState(sp);
  const filtered = applyFilters(base, state);
  const ordered = sp.sort ? sortProducts(filtered, state.sort) : filtered;
  const { items, page, totalPages, total } = paginate(ordered, state.page);
  const facets = computeFacets(base);

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
