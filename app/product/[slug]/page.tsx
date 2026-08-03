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
import {
  getProductBySlug,
  getRelatedProducts,
  getRecommendedProducts,
} from "@/data/catalog";
import { getReviewsForProduct } from "@/data/catalog/reviews";
import { toCardProducts } from "@/data/catalog/adapters";
import { formatPrice } from "@/utils/format";
import { Truck, RotateCcw, ShieldCheck } from "lucide-react";
import Link from "next/link";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const product = getProductBySlug(slug);
  if (!product) return {};
  return {
    title: `${product.title} by ${product.brand} | Fashion Trendz`,
    description: product.description,
    openGraph: {
      title: `${product.title} by ${product.brand}`,
      description: product.description,
      images: [{ url: product.images[0] }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${product.title} by ${product.brand}`,
      description: product.description,
      images: [product.images[0]],
    },
  };
}

export default async function ProductPage({ params }: PageProps) {
  const { slug } = await params;
  const product = getProductBySlug(slug);
  if (!product) notFound();

  const reviews = getReviewsForProduct(product);
  const related = toCardProducts(getRelatedProducts(product, 8));
  const recommended = toCardProducts(getRecommendedProducts(product, 8));
  const distribution = [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: reviews.filter((r) => r.rating === star).length,
  }));
  const maxCount = Math.max(1, ...distribution.map((d) => d.count));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <RecentlyViewedTracker
        slug={product.slug}
        title={product.title}
        brand={product.brand}
        image={product.images[0]}
        price={product.price}
        discountedPrice={product.discountedPrice}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL },
            {
              "@type": "ListItem",
              position: 2,
              name: product.categoryName,
              item: `${SITE_URL}/${product.category}`,
            },
            {
              "@type": "ListItem",
              position: 3,
              name: product.subcategoryName,
              item: `${SITE_URL}/${product.category}/${product.subcategory}`,
            },
            { "@type": "ListItem", position: 4, name: product.title },
          ],
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Product",
          name: product.title,
          image: product.images,
          description: product.description,
          sku: product.id,
          brand: { "@type": "Brand", name: product.brand },
          aggregateRating:
            product.reviewCount > 0
              ? {
                  "@type": "AggregateRating",
                  ratingValue: product.rating,
                  reviewCount: product.reviewCount,
                }
              : undefined,
          offers: {
            "@type": "Offer",
            url: `${SITE_URL}/product/${product.slug}`,
            priceCurrency: "INR",
            price: product.discountedPrice,
            availability:
              product.stock > 0
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
              <Link href={`/${product.category}`}>{product.categoryName}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href={`/${product.category}/${product.subcategory}`}>
                {product.subcategoryName}
              </Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{product.title}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-2">
        <ProductGallery images={product.images} alt={product.title} />

        <div>
        <div className="flex flex-col gap-5 lg:sticky lg:top-24">
          <div className="flex flex-col gap-1.5">
            <Link
              href={`/search?brand=${product.brandSlug}`}
              className="text-sm font-medium text-muted-foreground hover:text-accent"
            >
              {product.brand}
            </Link>
            <h1 className="font-heading text-2xl font-semibold sm:text-3xl">
              {product.title}
            </h1>
            <div className="flex items-center gap-2">
              <Rating value={product.rating} count={product.reviewCount} />
              {product.isNew && <Badge>New</Badge>}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-2xl font-semibold">
              {formatPrice(product.discountedPrice)}
            </span>
            {product.discount > 0 && (
              <>
                <span className="text-base text-muted-foreground line-through">
                  {formatPrice(product.price)}
                </span>
                <Badge variant="secondary">{product.discount}% OFF</Badge>
              </>
            )}
          </div>

          <ProductOptions
            productId={product.id}
            slug={product.slug}
            name={product.title}
            brand={product.brand}
            image={product.images[0]}
            price={product.price}
            discountedPrice={product.discountedPrice}
            sizes={product.sizes}
            colors={product.colors}
            stock={product.stock}
          />

          <div className="flex flex-col gap-3 rounded-xl border border-border p-4 text-sm">
            <div className="flex items-center gap-2 text-foreground/80">
              <Truck className="size-4 text-accent" />
              Delivery in {product.deliveryDays} days
            </div>
            <div className="flex items-center gap-2 text-foreground/80">
              <RotateCcw className="size-4 text-accent" />
              {product.returnPolicy}
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
                  <dd>{product.material}</dd>
                  <dt className="text-muted-foreground">Fit</dt>
                  <dd>{product.fit}</dd>
                  <dt className="text-muted-foreground">Occasion</dt>
                  <dd>{product.occasion}</dd>
                </dl>
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="care">
              <AccordionTrigger>Wash Care</AccordionTrigger>
              <AccordionContent>{product.careInstructions}</AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
        </div>
      </div>

      <section className="mt-16 grid grid-cols-1 gap-10 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-3">
          <h2 className="font-heading text-xl font-semibold">Customer Reviews</h2>
          <div className="flex items-center gap-3">
            <span className="text-3xl font-semibold">{product.rating}</span>
            <div className="flex flex-col">
              <Rating value={product.rating} />
              <span className="text-xs text-muted-foreground">
                {product.reviewCount} ratings
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
          {reviews.map((review) => (
            <div key={review.id} className="flex flex-col gap-1.5 py-4 first:pt-0">
              <div className="flex items-center gap-2">
                <Rating value={review.rating} />
                {review.verified && (
                  <Badge variant="outline" className="text-[10px]">
                    Verified Purchase
                  </Badge>
                )}
              </div>
              <span className="text-sm font-medium">{review.title}</span>
              <p className="text-sm text-muted-foreground">{review.body}</p>
              <span className="text-xs text-muted-foreground">
                {review.author} · {review.date}
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
