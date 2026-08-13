import { notFound } from "next/navigation";
import type { Metadata } from "next";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Rating } from "@/components/common/Rating";
import { JsonLd } from "@/components/common/JsonLd";
import { ProductGallery } from "@/components/product/ProductGallery";
import { ProductOptions } from "@/components/product/ProductOptions";
import { RecentlyViewedTracker } from "@/components/product/RecentlyViewedTracker";
import { RecentlyViewed } from "@/components/product/RecentlyViewed";
import { ProductCarouselSection } from "@/components/home/ProductCarouselSection";
import { ApiError, publicGet, publicGetPaged } from "@/lib/api";
import { apiProductCardsToProducts, apiProductDetailToProduct } from "@/lib/apiAdapters";
import { formatPrice } from "@/utils/format";
import { Truck, RotateCcw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ApiProductCard, ApiProductDetail } from "@/types/api";

// Stock, price and reviews change constantly — render from the backend on
// every request instead of freezing a product page into the build.
export const dynamic = "force-dynamic";

interface ApiReview {
  id: string;
  user_name: string;
  rating: number;
  title: string;
  body: string;
  is_verified_purchase: boolean;
  created_at: string;
}

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

interface PageProps {
  params: Promise<{ slug: string }>;
}

async function getProduct(slug: string): Promise<ApiProductDetail | null> {
  try {
    return await publicGet<ApiProductDetail>(`/products/${slug}/`, 60);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) return {};
  const image = product.primary_image?.image;
  return {
    title: `${product.name} by ${product.brand.name} | Fashion Trendz`,
    description: product.short_description,
    openGraph: {
      title: `${product.name} by ${product.brand.name}`,
      description: product.short_description,
      images: image ? [{ url: image }] : undefined,
    },
    twitter: {
      card: "summary_large_image",
      title: `${product.name} by ${product.brand.name}`,
      description: product.short_description,
      images: image ? [image] : undefined,
    },
  };
}

export default async function ProductPage({ params }: PageProps) {
  const { slug } = await params;
  const apiProduct = await getProduct(slug);
  if (!apiProduct) notFound();

  const [relatedRaw, similarRaw, reviewsPage] = await Promise.all([
    publicGet<ApiProductCard[]>(`/products/${slug}/related/`, 60).catch(() => []),
    publicGet<ApiProductCard[]>(`/products/${slug}/similar/`, 60).catch(() => []),
    publicGetPaged<ApiReview[]>(`/products/${slug}/reviews/`, 60).catch(() => ({
      data: [] as ApiReview[],
      pagination: undefined,
    })),
  ]);

  const product = apiProductDetailToProduct(apiProduct);
  const related = apiProductCardsToProducts(relatedRaw);
  const recommended = apiProductCardsToProducts(similarRaw);
  const reviews = reviewsPage.data;
  const images = apiProduct.images.length
    ? apiProduct.images.map((img) => img.image)
    : [product.image];

  const distribution = [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: reviews.filter((r) => r.rating === star).length,
  }));
  const maxCount = Math.max(1, ...distribution.map((d) => d.count));
  const rating = Number(apiProduct.rating_average);
  const discountPct = Math.round(Number(apiProduct.discount_percentage));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <RecentlyViewedTracker slug={product.slug} />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL },
            {
              "@type": "ListItem",
              position: 2,
              name: apiProduct.category.name,
              item: `${SITE_URL}/${apiProduct.category.slug}`,
            },
            {
              "@type": "ListItem",
              position: 3,
              name: apiProduct.subcategory.name,
              item: `${SITE_URL}/${apiProduct.category.slug}/${apiProduct.subcategory.slug}`,
            },
            { "@type": "ListItem", position: 4, name: product.name },
          ],
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Product",
          name: product.name,
          image: images,
          description: product.description,
          sku: apiProduct.sku,
          brand: { "@type": "Brand", name: product.brand },
          aggregateRating:
            apiProduct.review_count > 0
              ? {
                  "@type": "AggregateRating",
                  ratingValue: rating,
                  reviewCount: apiProduct.review_count,
                }
              : undefined,
          offers: {
            "@type": "Offer",
            url: `${SITE_URL}/product/${product.slug}`,
            priceCurrency: apiProduct.currency,
            price: product.price,
            availability: apiProduct.is_in_stock
              ? "https://schema.org/InStock"
              : "https://schema.org/OutOfStock",
          },
        }}
      />
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">Home</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href={`/${apiProduct.category.slug}`}>{apiProduct.category.name}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href={`/${apiProduct.category.slug}/${apiProduct.subcategory.slug}`}>
                {apiProduct.subcategory.name}
              </Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{product.name}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-2">
        <ProductGallery images={images} alt={product.name} />

        <div>
        <div className="flex flex-col gap-5 lg:sticky lg:top-24">
          <div className="flex flex-col gap-1.5">
            <Link
              href={`/search?brand=${apiProduct.brand.slug}`}
              className="text-sm font-medium text-muted-foreground hover:text-accent"
            >
              {product.brand}
            </Link>
            <h1 className="font-heading text-2xl font-semibold sm:text-3xl">
              {product.name}
            </h1>
            <div className="flex items-center gap-2">
              <Rating value={rating} count={apiProduct.review_count} />
              {product.isNew && <Badge>New</Badge>}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-2xl font-semibold">{formatPrice(product.price)}</span>
            {discountPct > 0 && (
              <>
                <span className="text-base text-muted-foreground line-through">
                  {formatPrice(product.compareAtPrice ?? product.price)}
                </span>
                <Badge variant="secondary">{discountPct}% OFF</Badge>
              </>
            )}
          </div>

          <ProductOptions
            productId={product.id}
            slug={product.slug}
            name={product.name}
            brand={product.brand}
            image={product.image}
            price={product.compareAtPrice ?? product.price}
            discountedPrice={product.price}
            sizes={product.sizes ?? []}
            colors={product.colors ?? []}
            stock={product.stock ?? 0}
            variants={product.variants}
          />

          <div className="flex flex-col gap-3 rounded-xl border border-border p-4 text-sm">
            <div className="flex items-center gap-2 text-foreground/80">
              <Truck className="size-4 text-accent" />
              Delivery in {apiProduct.estimated_delivery_days} days
            </div>
            <div className="flex items-center gap-2 text-foreground/80">
              <RotateCcw className="size-4 text-accent" />
              {apiProduct.return_policy || "Easy returns within 7 days"}
            </div>
            <div className="flex items-center gap-2 text-foreground/80">
              <ShieldCheck className="size-4 text-accent" />
              100% authentic, quality checked
            </div>
          </div>

          <Accordion type="multiple" defaultValue={["description"]}>
            <AccordionItem value="description">
              <AccordionTrigger>Description</AccordionTrigger>
              <AccordionContent>{product.description}</AccordionContent>
            </AccordionItem>
            <AccordionItem value="specs">
              <AccordionTrigger>Specifications</AccordionTrigger>
              <AccordionContent>
                <dl className="grid grid-cols-2 gap-y-2 text-sm">
                  <dt className="text-muted-foreground">Material</dt>
                  <dd>{apiProduct.material_display || "—"}</dd>
                  <dt className="text-muted-foreground">Fit</dt>
                  <dd>{apiProduct.fit_display || "—"}</dd>
                  <dt className="text-muted-foreground">Occasion</dt>
                  <dd>{apiProduct.occasion_display || "—"}</dd>
                </dl>
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="care">
              <AccordionTrigger>Wash Care</AccordionTrigger>
              <AccordionContent>
                {apiProduct.care_instructions || "See garment label for care instructions."}
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
        </div>
      </div>

      <section className="mt-16 grid grid-cols-1 gap-10 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-3">
          <h2 className="font-heading text-xl font-semibold">Customer Reviews</h2>
          <div className="flex items-center gap-3">
            <span className="text-3xl font-semibold">{rating.toFixed(1)}</span>
            <div className="flex flex-col">
              <Rating value={rating} />
              <span className="text-xs text-muted-foreground">
                {apiProduct.review_count} ratings
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            {distribution.map(({ star, count }) => (
              <div key={star} className="flex items-center gap-2 text-xs">
                <span className="w-8 text-muted-foreground">{star}★</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col divide-y divide-border">
          {reviews.length === 0 && (
            <p className="py-4 text-sm text-muted-foreground">
              No reviews yet — be the first to review this product.
            </p>
          )}
          {reviews.map((review) => (
            <div key={review.id} className="flex flex-col gap-1.5 py-4 first:pt-0">
              <div className="flex items-center gap-2">
                <Rating value={review.rating} />
                {review.is_verified_purchase && (
                  <Badge variant="outline" className="text-[10px]">
                    Verified Purchase
                  </Badge>
                )}
              </div>
              <span className="text-sm font-medium">{review.title}</span>
              <p className="text-sm text-muted-foreground">{review.body}</p>
              <span className="text-xs text-muted-foreground">
                {review.user_name} ·{" "}
                {new Date(review.created_at).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
            </div>
          ))}
        </div>
      </section>

      {related.length > 0 && (
        <div className="mt-8 -mx-4 sm:-mx-6 lg:-mx-8">
          <ProductCarouselSection
            eyebrow="You May Also Like"
            title="Related Products"
            products={related}
          />
        </div>
      )}

      {recommended.length > 0 && (
        <div className="-mx-4 sm:-mx-6 lg:-mx-8">
          <ProductCarouselSection
            eyebrow="Just For You"
            title="Recommended Products"
            products={recommended}
            tinted
          />
        </div>
      )}

      <div className="-mx-4 sm:-mx-6 lg:-mx-8">
        <RecentlyViewed excludeSlug={product.slug} />
      </div>
    </div>
  );
}
