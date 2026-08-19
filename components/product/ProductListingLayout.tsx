import Link from "next/link";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { ProductCard } from "@/components/product/ProductCard";
import { ProductEmptyState } from "@/components/product/ProductEmptyState";
import { ProductFilters } from "@/components/product/ProductFilters";
import { MobileFilterSheet } from "@/components/product/MobileFilterSheet";
import { SortSelect } from "@/components/product/SortSelect";
import { JsonLd } from "@/components/common/JsonLd";
import type { SearchParamsRecord } from "@/lib/filters";
import type { FilterFacets } from "@/types/catalog";
import type { Product } from "@/types/product";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

interface Crumb {
  label: string;
  href?: string;
}

interface ProductListingLayoutProps {
  title: string;
  description?: string;
  breadcrumbs: Crumb[];
  products: Product[];
  facets: FilterFacets;
  total: number;
  page: number;
  totalPages: number;
  basePath: string;
  searchParams: SearchParamsRecord;
  showGender?: boolean;
  emptyMessage?: string;
}

function buildPageHref(
  basePath: string,
  searchParams: SearchParamsRecord,
  page: number
) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (key === "page" || value === undefined) continue;
    params.set(key, Array.isArray(value) ? value[0] : value);
  }
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

export function ProductListingLayout({
  title,
  description,
  breadcrumbs,
  products,
  facets,
  total,
  page,
  totalPages,
  basePath,
  searchParams,
  showGender = true,
  emptyMessage = "No products match these filters yet. Try adjusting or clearing a filter.",
}: ProductListingLayoutProps) {
  const cardProducts = products;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: breadcrumbs.map((crumb, index) => ({
            "@type": "ListItem",
            position: index + 1,
            name: crumb.label,
            ...(crumb.href ? { item: `${SITE_URL}${crumb.href}` } : {}),
          })),
        }}
      />
      <Breadcrumb className="mb-4">
        <BreadcrumbList>
          {breadcrumbs.map((crumb, index) => (
            <span key={crumb.label} className="flex items-center gap-1.5">
              <BreadcrumbItem>
                {crumb.href ? (
                  <BreadcrumbLink asChild>
                    <Link href={crumb.href}>{crumb.label}</Link>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {index < breadcrumbs.length - 1 && <BreadcrumbSeparator />}
            </span>
          ))}
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-6 flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold sm:text-3xl">{title}</h1>
        {description && (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[240px_1fr]">
        <div className="hidden lg:block">
          <aside className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-1">
            <ProductFilters facets={facets} showGender={showGender} />
          </aside>
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              {total} {total === 1 ? "product" : "products"}
            </p>
            <div className="flex items-center gap-2">
              <MobileFilterSheet facets={facets} showGender={showGender} />
              <SortSelect />
            </div>
          </div>

          {cardProducts.length === 0 ? (
            <ProductEmptyState description={emptyMessage} basePath={basePath} />
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-6 xl:grid-cols-4">
              {cardProducts.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <Pagination>
              <PaginationContent>
                {page > 1 && (
                  <PaginationItem>
                    <PaginationPrevious
                      href={buildPageHref(basePath, searchParams, page - 1)}
                    />
                  </PaginationItem>
                )}
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(
                    (p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1
                  )
                  .map((p, i, arr) => (
                    <span key={p} className="flex items-center">
                      {i > 0 && arr[i - 1] !== p - 1 && (
                        <span className="px-1 text-muted-foreground">…</span>
                      )}
                      <PaginationItem>
                        <PaginationLink
                          href={buildPageHref(basePath, searchParams, p)}
                          isActive={p === page}
                        >
                          {p}
                        </PaginationLink>
                      </PaginationItem>
                    </span>
                  ))}
                {page < totalPages && (
                  <PaginationItem>
                    <PaginationNext
                      href={buildPageHref(basePath, searchParams, page + 1)}
                    />
                  </PaginationItem>
                )}
              </PaginationContent>
            </Pagination>
          )}
        </div>
      </div>
    </div>
  );
}
