import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ProductListingLayout } from "@/components/product/ProductListingLayout";
import { getCategoryBySlug, getSubcategoryBySlug } from "@/data/catalog/categories";
import { getProductsBySubcategory, getProductsOnSale } from "@/data/catalog";
import { filterAndSort, type SearchParamsRecord } from "@/lib/filters";
import type { Product } from "@/types/catalog";

interface PageProps {
  params: Promise<{ category: string; subcategory: string }>;
  searchParams: Promise<SearchParamsRecord>;
}

const SALE_PRESETS: Record<string, (products: Product[]) => Product[]> = {
  clearance: (products) => products.filter((p) => p.discount >= 40),
  "under-999": (products) => products.filter((p) => p.discountedPrice <= 999),
  "under-1999": (products) => products.filter((p) => p.discountedPrice <= 1999),
  "flat-50-off": (products) => products.filter((p) => p.discount >= 50),
  "last-few-left": (products) =>
    products.filter((p) => p.stock > 0 && p.stock <= 10),
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { category: categorySlug, subcategory: subSlug } = await params;
  const category = getCategoryBySlug(categorySlug);
  const sub = getSubcategoryBySlug(categorySlug, subSlug);
  if (!category || !sub) return {};
  return {
    title: `${sub.name} | ${category.name} | Fashion Trendz`,
    description: `Shop ${sub.name} in ${category.name} at Fashion Trendz.`,
  };
}

export default async function SubcategoryPage({ params, searchParams }: PageProps) {
  const { category: categorySlug, subcategory: subSlug } = await params;
  const category = getCategoryBySlug(categorySlug);
  const sub = getSubcategoryBySlug(categorySlug, subSlug);
  if (!category || !sub) notFound();

  const sp = await searchParams;
  const baseProducts =
    categorySlug === "sale"
      ? (SALE_PRESETS[subSlug]?.(getProductsOnSale()) ?? getProductsOnSale())
      : getProductsBySubcategory(categorySlug, subSlug);

  const { facets, items, total, page, totalPages } = filterAndSort(
    baseProducts,
    sp
  );

  return (
    <ProductListingLayout
      title={sub.name}
      description={`${category.name} · ${sub.name}`}
      breadcrumbs={[
        { label: "Home", href: "/" },
        { label: category.name, href: `/${category.slug}` },
        { label: sub.name },
      ]}
      products={items}
      facets={facets}
      total={total}
      page={page}
      totalPages={totalPages}
      basePath={`/${category.slug}/${sub.slug}`}
      searchParams={sp}
    />
  );
}
