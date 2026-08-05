import nextDynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import { JsonLd } from "@/components/common/JsonLd";
import { HeroCarousel } from "@/components/home/HeroCarousel";
import { ShopByCategory } from "@/components/home/ShopByCategory";
import { ProductCarouselSection } from "@/components/home/ProductCarouselSection";
import { FeaturedBrands } from "@/components/home/FeaturedBrands";
import { NewArrivals } from "@/components/home/NewArrivals";
import { publicGet } from "@/lib/api";
import { apiProductCardsToProducts } from "@/lib/apiAdapters";
import type { ApiHomepageProducts } from "@/types/api";

// Product rails are live backend data — always render at request time
// rather than being baked into the build as a static shell.
export const dynamic = "force-dynamic";

function SectionFallback() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <Skeleton className="h-64 w-full rounded-2xl" />
    </div>
  );
}

// Below-the-fold sections are code-split so the initial homepage bundle
// stays focused on what's visible first.
const LuxuryCollection = nextDynamic(() =>
  import("@/components/home/LuxuryCollection").then((m) => m.LuxuryCollection)
);
const FlashSale = nextDynamic(
  () => import("@/components/home/FlashSale").then((m) => m.FlashSale),
  { loading: SectionFallback }
);
const EditorsPicks = nextDynamic(() =>
  import("@/components/home/EditorsPicks").then((m) => m.EditorsPicks)
);
const FashionInspiration = nextDynamic(
  () =>
    import("@/components/home/FashionInspiration").then(
      (m) => m.FashionInspiration
    ),
  { loading: SectionFallback }
);
const CustomerReviews = nextDynamic(() =>
  import("@/components/home/CustomerReviews").then((m) => m.CustomerReviews)
);
const FashionBlog = nextDynamic(() =>
  import("@/components/home/FashionBlog").then((m) => m.FashionBlog)
);
const InstagramGallery = nextDynamic(() =>
  import("@/components/home/InstagramGallery").then((m) => m.InstagramGallery)
);
const NewsletterSection = nextDynamic(() =>
  import("@/components/home/NewsletterSection").then(
    (m) => m.NewsletterSection
  )
);

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const EMPTY_HOMEPAGE: ApiHomepageProducts = {
  featured: [],
  trending: [],
  new_arrivals: [],
  best_sellers: [],
  luxury: [],
  flash_sale: [],
  editors_picks: [],
  trending_this_week: [],
  recommended: [],
  recently_added: [],
};

export default async function Home() {
  const rails = await publicGet<ApiHomepageProducts>("/products/homepage/", 60).catch(
    () => EMPTY_HOMEPAGE
  );

  const trendingProducts = apiProductCardsToProducts(rails.trending);
  const bestSellerProducts = apiProductCardsToProducts(rails.best_sellers);
  const trendingWeekProducts = apiProductCardsToProducts(rails.trending_this_week);
  const newArrivalProducts = apiProductCardsToProducts(rails.new_arrivals);
  const flashSaleProducts = apiProductCardsToProducts(rails.flash_sale);

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
      <NewArrivals products={newArrivalProducts} />
      <ProductCarouselSection
        eyebrow="Customer Favorites"
        title="Best Sellers"
        subtitle="The pieces our shoppers keep coming back for."
        viewAllHref="/sale"
        products={bestSellerProducts}
        tinted
      />
      <LuxuryCollection />
      <FlashSale products={flashSaleProducts} />
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
