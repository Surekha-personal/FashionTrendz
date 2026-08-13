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

// Turns a collection slug into a readable label when the caller (e.g. the
// homepage's Editor's Picks CTA) doesn't have the collection's display title
// on hand — just its slug. Generic on purpose: works for any collection slug,
// not just "editors-picks".
function humanizeSlug(slug: string): string {
  return slug
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export default async function SearchPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const query = Array.isArray(sp.q) ? sp.q[0] : (sp.q ?? "");
  const collectionSlug = (
    Array.isArray(sp.collection) ? sp.collection[0] : (sp.collection ?? "")
  ).trim();
  const state = parseFilterState(sp);

  // A collection link (e.g. the homepage's Editor's Picks CTA) takes
  // precedence over any stray `q` — otherwise the collection's title would
  // get sent through as an accidental free-text search instead of filtering
  // by collection slug (backend's ProductFilter.collection).
  //
  // The sidebar filters compose with either through the same ProductFilter
  // — using it here keeps facets, sort and pagination consistent with every
  // other listing page instead of juggling the separate ranked
  // /products/search/ endpoint.
  const extra: Record<string, string> = collectionSlug
    ? { collection: collectionSlug }
    : query.trim()
      ? { q: query.trim() }
      : {};

  const { items, facets, page, totalPages, total } = await fetchProductListing(
    "/products/",
    state,
    extra
  );

  const collectionTitle = collectionSlug ? humanizeSlug(collectionSlug) : "";

  const title = collectionTitle
    ? collectionTitle
    : query
      ? `Results for "${query}"`
      : "Search Fashion Trendz";

  const description = collectionTitle
    ? `${total} ${total === 1 ? "product" : "products"}`
    : query
      ? `${total} ${total === 1 ? "product" : "products"} found`
      : "Search across products, brands and categories.";

  const emptyMessage = collectionTitle
    ? `No products found in ${collectionTitle} yet.`
    : query
      ? `No results for "${query}". Try a different keyword or clear filters.`
      : "Type in the search bar above to find products, brands and categories.";

  return (
    <ProductListingLayout
      title={title}
      description={description}
      breadcrumbs={[{ label: "Home", href: "/" }, { label: "Search" }]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath="/search"
      searchParams={sp}
      emptyMessage={emptyMessage}
    />
  );
}
