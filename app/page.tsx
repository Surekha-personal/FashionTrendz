import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import { JsonLd } from "@/components/common/JsonLd";
import { HeroCarousel } from "@/components/home/HeroCarousel";
import { ShopByCategory } from "@/components/home/ShopByCategory";
import { ProductCarouselSection } from "@/components/home/ProductCarouselSection";
import { FeaturedBrands } from "@/components/home/FeaturedBrands";
import { NewArrivals } from "@/components/home/NewArrivals";
import {
  getTrending,
  getBestSellers,
  getTrendingThisWeek,
} from "@/data/catalog";
import { toCardProducts } from "@/data/catalog/adapters";

function SectionFallback() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <Skeleton className="h-64 w-full rounded-2xl" />
    </div>
  );
}

// Below-the-fold sections are code-split so the initial homepage bundle
// stays focused on what's visible first.
const LuxuryCollection = dynamic(() =>
  import("@/components/home/LuxuryCollection").then((m) => m.LuxuryCollection)
);
const FlashSale = dynamic(
  () => import("@/components/home/FlashSale").then((m) => m.FlashSale),
  { loading: SectionFallback }
);
const EditorsPicks = dynamic(() =>
  import("@/components/home/EditorsPicks").then((m) => m.EditorsPicks)
);
const FashionInspiration = dynamic(
  () =>
    import("@/components/home/FashionInspiration").then(
      (m) => m.FashionInspiration
    ),
  { loading: SectionFallback }
);
const CustomerReviews = dynamic(() =>
  import("@/components/home/CustomerReviews").then((m) => m.CustomerReviews)
);
const FashionBlog = dynamic(() =>
  import("@/components/home/FashionBlog").then((m) => m.FashionBlog)
);
const InstagramGallery = dynamic(() =>
  import("@/components/home/InstagramGallery").then((m) => m.InstagramGallery)
);
const NewsletterSection = dynamic(() =>
  import("@/components/home/NewsletterSection").then(
    (m) => m.NewsletterSection
  )
);

const trendingProducts = toCardProducts(getTrending(10));
const bestSellerProducts = toCardProducts(getBestSellers(10));
const trendingWeekProducts = toCardProducts(getTrendingThisWeek(10));
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default function Home() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: "Fashion Trendz",
          url: SITE_URL,
          potentialAction: {
            "@type": "SearchAction",
            target: `${SITE_URL}/search?q={search_term_string}`,
            "query-input": "required name=search_term_string",
          },
        }}
      />
      <HeroCarousel />
      <ShopByCategory />
      <ProductCarouselSection
        eyebrow="Hot Right Now"
        title="Trending Now"
        subtitle="What everyone's adding to their bag this week."
        viewAllHref="/new-in"
        products={trendingProducts}
      />
      <FeaturedBrands />
      <NewArrivals />
      <ProductCarouselSection
        eyebrow="Customer Favorites"
        title="Best Sellers"
        subtitle="The pieces our shoppers keep coming back for."
        viewAllHref="/sale"
        products={bestSellerProducts}
        tinted
      />
      <LuxuryCollection />
      <FlashSale />
      <EditorsPicks />
      <ProductCarouselSection
        eyebrow="Don't Miss Out"
        title="Trending This Week"
        subtitle="Fresh picks rising fast across every category."
        products={trendingWeekProducts}
      />
      <FashionInspiration />
      <CustomerReviews />
      <FashionBlog />
      <InstagramGallery />
      <NewsletterSection />
    </>
  );
}
