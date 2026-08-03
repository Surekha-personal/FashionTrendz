import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { getCategoryBySlug } from "@/data/catalog/categories";
import { getProductsByCategory, getProductsOnSale } from "@/data/catalog";
import { filterAndSort, type SearchParamsRecord } from "@/lib/filters";

interface PageProps {
  params: Promise<{ category: string }>;
  searchParams: Promise<SearchParamsRecord>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { category: categorySlug } = await params;
  const category = getCategoryBySlug(categorySlug);
  if (!category) return {};
  return {
    title: `${category.name} | Fashion Trendz`,
    description: `Shop the latest ${category.name} collection at Fashion Trendz.`,
  };
}

export default async function CategoryPage({ params, searchParams }: PageProps) {
  const { category: categorySlug } = await params;
  const category = getCategoryBySlug(categorySlug);
  if (!category) notFound();

  const sp = await searchParams;
  const baseProducts =
    categorySlug === "sale" ? getProductsOnSale() : getProductsByCategory(categorySlug);
  const { facets, items, total, page, totalPages } = filterAndSort(
    baseProducts,
    sp
  );

  return (
    <ProductListingLayout
      title={category.name}
      description={
        categorySlug === "sale"
          ? "Discounted picks across every category, updated daily."
          : `Explore ${category.subcategories.length}+ styles across ${category.name.toLowerCase()}.`
      }
      breadcrumbs={[{ label: "Home", href: "/" }, { label: category.name }]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath={`/${category.slug}`}
      searchParams={sp}
    />
  );
}
