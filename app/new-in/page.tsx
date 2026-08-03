import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { products } from "@/data/catalog";
import { filterAndSort, type SearchParamsRecord } from "@/lib/filters";

export const metadata: Metadata = {
  title: "New In | Fashion Trendz",
  description: "The newest arrivals across every category at Fashion Trendz.",
};

interface PageProps {
  searchParams: Promise<SearchParamsRecord>;
}

export default async function NewInPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const baseProducts = products.filter((p) => p.isNew);
  const { facets, items, total, page, totalPages } = filterAndSort(
    baseProducts,
    sp
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
