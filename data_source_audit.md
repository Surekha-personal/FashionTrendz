# Data-Source Audit — Frontend Product/Catalogue Data & Images

Read-only. Nothing has been modified. This traces every place the frontend can put a product, category, brand, or "hero/banner" image on screen, and says whether that pixel came from the Django API or from frontend-local mock data.

## Root cause, in one paragraph

The homepage is not fully wired to the backend. Five rails (Trending Now, New Arrivals, Best Sellers, Flash Sale, Trending This Week) already call `GET /products/homepage/` and render real backend products with real backend image URLs. But eight other homepage sections — the hero carousel, Shop By Category, Featured Brands, Luxury Collection, Editor's Picks, Fashion Inspiration, Customer Reviews, and the Instagram gallery — were never reconnected after the backend was wired up. They still import static arrays from `data/*.ts`, most of which resolve to hard-coded Unsplash/pravatar URLs. That's why the homepage looks like it's mixing "old demo" and "real backend" images: it genuinely is, section by section, not row by row.

There is also a second, separate mechanism that can inject fake data into the *cart/wishlist/orders*: a client-side "Demo Mode" toggle in the account dropdown that overwrites real state with a mock order history built from the same static product catalog. That's covered in its own section below since it's not a rendering bug, it's a feature someone can accidentally leave switched on.

---

## A. Complete Audit

### A1. Homepage rails — product data (the "Trending/New/Best Sellers/Sale" rows)

| File | Component | Data used | Source | Correct endpoint | Notes |
|---|---|---|---|---|---|
| `app/page.tsx` | `Home` | `rails.trending`, `.new_arrivals`, `.best_sellers`, `.flash_sale`, `.trending_this_week` via `apiProductCardsToProducts` | ✅ **API** | `GET /products/homepage/` | Already correct. Falls back to an all-empty `EMPTY_HOMEPAGE` object (not fake products) on fetch failure — an empty rail, not demo data. Safe. |
| `components/home/NewArrivals.tsx` | `NewArrivals` | `products` prop from `app/page.tsx` | ✅ **API** (passthrough) | — | Pure presentational component, takes real data as a prop. No source problem. |
| `components/home/FlashSale.tsx` | `FlashSale` | `products` prop from `app/page.tsx` | ✅ **API** (passthrough) | — | Same — presentational only. |
| `components/home/ProductCarouselSection.tsx` | used for Trending Now / Best Sellers / Trending This Week | `products` prop | ✅ **API** (passthrough) | — | Same. |

### A2. Homepage rails — NOT product data, but hard-coded imagery sitting on the same page

| File | Component | Data used | Source | Correct endpoint | Removing frontend data breaks anything? |
|---|---|---|---|---|---|
| `components/home/HeroCarousel.tsx` + `data/hero.ts` | `HeroCarousel` | `heroSlides`: hard-coded array of hero images (Unsplash URLs — see `data/hero.ts`, uses `unsplash()` from `utils/images.ts`), titles, CTAs, links | ❌ **Hard-coded** | **Unknown — see Gap E1.** Should be the backend's Banner endpoint once confirmed. | No — nothing else reads `heroSlides`. Safe to swap once the endpoint is known. |
| `components/home/ShopByCategory.tsx` + `data/categories.ts` → `data/catalog/categories.ts` | `ShopByCategory` | `categories`: id, name, `href`, `image`, `imageAlt` — ultimately sourced from `data/catalog/categories.ts` (mock category tiles, Unsplash-backed images via `imagePool`/`unsplash()`) | ❌ **Hard-coded** | `GET /categories/` (already used elsewhere — `app/[category]/page.tsx` calls `GET /categories/{slug}/`) or `GET /categories/homepage/` if it returns the specific curated tile set. Backend `CategorySerializer` exposes `image`/`banner_image`. | No other component imports `data/categories.ts` besides this one. Safe to remove once replaced. |
| `components/home/FeaturedBrands.tsx` + `data/brands.ts` → `data/catalog/brands.ts` | `FeaturedBrands` | `brands`: id, name, `href` (12 mock brands, no image field is even rendered here, but the underlying mock brand records carry fake logos) | ❌ **Hard-coded** | `GET /brands/featured/` (confirmed to exist: `BrandViewSet.featured` action) | No other component imports `data/brands.ts`. `SearchBar` uses it too (see A3) — that import must stay or be swapped at the same time. |
| `components/home/LuxuryCollection.tsx` + `data/editorial.ts` (`luxuryBanners`) | `LuxuryCollection` | Hard-coded luxury promo banner images/copy | ❌ **Hard-coded** | `GET /brands/luxury/` and/or `GET /collections/featured/` (both confirmed to exist on the backend) for the underlying items; banner artwork itself may need the Banner endpoint from Gap E1 if it's meant to be editorial, not per-brand. | No other importer. Safe. |
| `components/home/EditorsPicks.tsx` + `data/editorial.ts` (`editorsPicks`) | `EditorsPicks` | Hard-coded editorial picks (images + copy) | ❌ **Hard-coded** | `GET /collections/editors-picks/` (confirmed to exist: `CollectionViewSet.editors_picks`) | No other importer. Safe. |
| `components/home/FashionInspiration.tsx` + `data/inspiration.ts` | `FashionInspiration` | Hard-coded Pinterest-style image grid (Unsplash) | ❌ **Hard-coded, no backend equivalent** | None found. This is editorial/marketing content, not catalogue data — there is no `Product`, `Category`, `Brand`, or `Collection` behind it. | See recommendation below — likely stays static by design, just needs to be called out explicitly rather than assumed. |
| `components/home/CustomerReviews.tsx` + `data/testimonials.ts` | `CustomerReviews` | Hard-coded testimonial quotes + `pravatar()` reviewer avatars | ❌ **Hard-coded, no backend equivalent** | The backend does have a real `Review` model (`apps.reviews`), but there is no "site-wide featured testimonials" endpoint — only per-product reviews (`GET /products/{slug}/reviews/`). | Same as above — marketing content, not catalogue data. Flagging, not necessarily fixing. |
| `components/home/FashionBlog.tsx` + `data/blog.ts` | `FashionBlog` | Hard-coded blog post cards (Unsplash images) | ❌ **Hard-coded, no backend equivalent** | None — no blog/CMS module exists in this backend. | Editorial content, out of scope for "catalogue data." |
| `components/home/InstagramGallery.tsx` + `data/instagram.ts` | `InstagramGallery` | Hard-coded Instagram-style grid (Unsplash) | ❌ **Hard-coded, no backend equivalent** | None — no social-feed module exists. | Editorial content, out of scope. |
| `components/home/NewsletterSection.tsx` | `NewsletterSection` | No product/image data at all (just a form) | — | — | Not in scope. |

**Bottom line for the homepage:** four sections (Hero, Shop By Category, Featured Brands, Luxury Collection, Editor's Picks — five, really) have a direct, confirmed backend replacement and should move to real data. Four sections (Fashion Inspiration, Customer Reviews, Fashion Blog, Instagram Gallery) have **no backend equivalent at all** — they're pure marketing/editorial filler and were probably always meant to stay static. I'm flagging them per your instructions, not recommending they be wired to anything, since there's nothing to wire them to.

### A3. Category / listing / search / product-detail pages

| File | Component/function | Data used | Source | Endpoint currently called | Notes |
|---|---|---|---|---|---|
| `app/[category]/page.tsx`, `app/[category]/[subcategory]/page.tsx`, `app/new-in/page.tsx`, `app/search/page.tsx` | via `lib/apiCatalog.ts` `fetchProductListing` | Product grid + filter facets | ✅ **API** | `GET /products/`, `GET /products/filters/` | Correct, already audited in the integration pass. |
| `app/product/[slug]/page.tsx` | `ProductPage` | Product detail, related, similar, reviews | ✅ **API** | `GET /products/{slug}/`, `/related/`, `/similar/`, `/reviews/` | Correct. |
| `app/api/search-suggestions/route.ts` | proxy route used by `SearchBar` while typing | Live suggestions + ranked results | ✅ **API** | `GET /products/suggestions/`, `GET /products/search/` | Correct — this is the part of search that's already real. |
| `components/layout/SearchBar.tsx` | idle-state ("Popular Brands") suggestions, before the user types anything | `popularBrands` from `data/brands.ts` | ❌ **Hard-coded** | `GET /brands/popular/` (confirmed to exist) | Only affects the empty-state chip row shown before typing — once a query is entered, results are already real (see row above). |
| `components/layout/SearchBar.tsx` | idle-state "Recently Viewed" thumbnails | `getRecentlyViewed()` from `lib/recentlyViewed.ts` (localStorage) | ⚠ **Local-only, not backend** | See A5 — the backend has a real recently-viewed endpoint the frontend never calls. | Images shown here are whatever was cached locally, which today are real backend URLs (see A5) — so visually this isn't broken, but it's not the source of truth and won't sync across devices. |
| `lib/search.ts` | `POPULAR_SEARCHES` (static term list), `searchProducts`, `searchBrandsByQuery`, `searchCategoriesByQuery` | Static search-term list + three functions that search a locally-held `Product[]`/mock brand/category array | Mixed | — | `POPULAR_SEARCHES` (just words like "Dresses", "Sneakers") is still used by `SearchBar` for the trending-terms chips — cosmetic, no image/product data, low priority. The three functions (`searchProducts`, `searchBrandsByQuery`, `searchCategoriesByQuery`) are **dead code** — nothing in the app calls them anymore (confirmed by grep; only their own exports match). Safe to delete, changes nothing. |
| `components/product/ProductFilters.tsx` | Brand filter checkbox/chip labels | `getBrandBySlug()` from `data/catalog/brands.ts` — used only to turn a real backend brand *slug* (from `/products/filters/` facets) into a display *name* | ⚠ **Mixed** | The backend facets response (`ApiFacets.brands`) already includes `{name, slug, product_count}` — the name doesn't need to be looked up locally at all. | The slugs themselves are real (from the API); only the human-readable label is at risk of being wrong or falling back to the raw slug if a backend brand isn't in the static list. Low severity, easy fix (use the name the facets response already provides instead of a local lookup). |

### A4. Wishlist / cart

| File | Component | Data used | Source | Notes |
|---|---|---|---|---|
| `context/CartContext.tsx`, `components/cart/CartDrawer.tsx`, `components/cart/CartLineItem.tsx` | cart state and images | `apiCartItemToLine()` → `item.product.primary_image?.image ?? PLACEHOLDER_IMAGE` | ✅ **API**, with a local SVG placeholder only when the backend genuinely has no image | Correct — `PLACEHOLDER_IMAGE` (`/placeholder-product.svg`) is a legitimate empty-state fallback, not mock product data. Already audited in the integration pass. |
| `context/WishlistContext.tsx`, `components/wishlist/WishlistCard.tsx` | wishlist state and images | `apiWishlistItemToLine()` → same pattern | ✅ **API** | Same as above. Correct. |

### A5. Recently Viewed — the one real structural gap

| File | Component | Data used | Source | Correct endpoint | Notes |
|---|---|---|---|---|---|
| `lib/recentlyViewed.ts`, `components/product/RecentlyViewedTracker.tsx`, `components/product/RecentlyViewed.tsx` | product-detail page's "Recently Viewed" rail, and `SearchBar`'s idle thumbnails | Entirely `localStorage`-based (`STORAGE_KEYS.recentlyViewed`), written by `recordRecentlyViewed()` on every product-page view, read by `getRecentlyViewed()` | ⚠ **Local-only — never touches the backend** | `GET /recently-viewed/`, `POST /recently-viewed/` (confirmed to exist: `RecentlyViewedViewSet`, supports guest `X-Cart-Session` and authenticated users with server-side merge — the backend already built this) | **This is a real gap, not just a rendering bug.** The backend has a whole recently-viewed system (with cross-device sync for signed-in users) that the frontend built its own parallel, local-only, never-synced version of instead of calling. The images it stores are today's real backend image URLs (since it captures whatever `product.image` resolved to at view time), so nothing looks "fake" right now — but the moment `lib/demoMode.ts` (below) is triggered, this exact storage key gets overwritten with fake demo-catalog images, which is the most likely explanation for stray old-looking images showing up unpredictably. |

### A6. Demo Mode — a second, separate mechanism that can inject fake data

| File | What it does |
|---|---|
| `lib/demoMode.ts` | `enableDemoMode()` fetches `/api/demo-seed`, then **overwrites** `localStorage` keys `cart`, `wishlist`, `orders`, `recentlyViewed`, and `demoUser` with fake data, then reloads the page. `disableDemoMode()` removes them and reloads. |
| `app/api/demo-seed/route.ts` | Builds that fake payload by pulling six to eight products out of `data/catalog` (the mock 600+-product generator, images from `data/catalog/imagePool.ts` → Unsplash) and shaping them into fake cart lines, wishlist lines, recently-viewed entries, and two fake past orders. |
| `components/layout/Navbar.tsx` | Exposes "Enable Demo Mode" / "Disable Demo Mode" as a clickable item in the account dropdown, for anyone signed in or out. |
| `components/common/DemoModeBadge.tsx` | Shows a small floating "Demo Mode" pill when the flag is on — the only visible warning that this happened. |

**Why this matters for your symptom:** `enableDemoMode()` writes directly into `STORAGE_KEYS.recentlyViewed`, the exact key `lib/recentlyViewed.ts` reads from. If Demo Mode was ever toggled on (by you, a tester, or anyone using that browser profile) and then off again, the `recentlyViewed` key isn't necessarily restored to real data — it just sits there with fake Unsplash-backed entries until the next time a real product page view overwrites it one slug at a time. `cart`/`wishlist`/`orders` are safer — `CartContext`/`WishlistContext` don't read those localStorage keys at all (they're 100% API-driven), so demo mode can't actually corrupt what the cart/wishlist pages show; it can only corrupt the Recently Viewed rail and the account-menu "demo user" name. Still, this entire mechanism directly contradicts "backend is the single source of truth" and should be addressed.

### A7. The one mock dataset with zero live consumers

| File | Used by |
|---|---|
| `data/catalog/index.ts`, `data/catalog/generateProducts.ts`, `data/catalog/imagePool.ts`, `data/catalog/attributes.ts`, `data/catalog/beautyWords.ts`, `data/catalog/reviews.ts` | Only `app/admin/page.tsx` (a `robots: noindex` internal dashboard preview, explicitly labeled "A frontend-only preview of what the Fashion Trendz team would see") and `app/api/demo-seed/route.ts` (Demo Mode, above). **No customer-facing page imports this anymore** — the homepage, listings, search, and product-detail pages were already migrated off it in the earlier integration work. |

This is good news: the 600+-product mock generator that used to be the entire site's data source is already fully retired from every real shopper-facing page. It's only reachable through the admin preview and Demo Mode.

---

## B. Frontend files that must change (if you approve)

Ordered by impact:

1. `components/home/ShopByCategory.tsx` + `data/categories.ts` — switch to `GET /categories/` (or the homepage-curated variant if the endpoint returns one)
2. `components/home/FeaturedBrands.tsx` + `data/brands.ts` — switch to `GET /brands/featured/`
3. `components/home/EditorsPicks.tsx` + `data/editorial.ts` (`editorsPicks` half) — switch to `GET /collections/editors-picks/`
4. `components/home/LuxuryCollection.tsx` + `data/editorial.ts` (`luxuryBanners` half) — switch to `GET /brands/luxury/` and/or `GET /collections/featured/`
5. `components/home/HeroCarousel.tsx` + `data/hero.ts` — switch to the Banner endpoint (blocked on Gap E1, see below)
6. `components/layout/SearchBar.tsx` — idle "Popular Brands" chips: switch to `GET /brands/popular/`; drop the `data/brands.ts` import (once nothing else needs it)
7. `components/product/ProductFilters.tsx` — use `facets.brands[].name` directly from the API response instead of `getBrandBySlug()` from mock data (small correctness fix, not a full data-source swap)
8. `lib/recentlyViewed.ts` + `RecentlyViewedTracker.tsx` + `RecentlyViewed.tsx` — repoint at `GET/POST /recently-viewed/` instead of `localStorage` (bigger change — this is the one genuine feature gap, not just a wiring swap)
9. `lib/demoMode.ts`, `app/api/demo-seed/route.ts`, `components/common/DemoModeBadge.tsx`, and the "Demo Mode" menu item in `components/layout/Navbar.tsx` — decide whether to remove Demo Mode entirely or at minimum stop it from writing into `recentlyViewed` (your call — this is a deliberate feature, not a bug, so I'm not assuming you want it deleted)
10. `lib/search.ts` — delete the three dead functions (`searchProducts`, `searchBrandsByQuery`, `searchCategoriesByQuery`); keep `POPULAR_SEARCHES`

**Not recommended to touch:** `FashionInspiration.tsx`, `CustomerReviews.tsx`, `FashionBlog.tsx`, `InstagramGallery.tsx`, `NewsletterSection.tsx` — no backend data exists for any of these; they're editorial/marketing sections that appear to be intentionally static.

**Not recommended to touch:** `data/catalog/*` (the mock generator) and `app/admin/page.tsx` — nothing customer-facing depends on them; removing them is a separate cleanup decision, not a data-integrity fix.

## C. Exact API endpoint currently being called, per section

| Section | Currently calls |
|---|---|
| Trending Now / New Arrivals / Best Sellers / Flash Sale / Trending This Week | `GET /products/homepage/` ✅ |
| Hero/Banner | *nothing* — fully static |
| Shop By Category | *nothing* — fully static |
| Featured Brands | *nothing* — fully static |
| Luxury Collection | *nothing* — fully static |
| Editor's Picks | *nothing* — fully static |
| Category pages | `GET /categories/{slug}/`, `GET /products/`, `GET /products/filters/` ✅ |
| Search (typed) | `GET /products/suggestions/`, `GET /products/search/` ✅ |
| Search (idle) | *nothing* — static popular-brand chips |
| Product detail | `GET /products/{slug}/`, `/related/`, `/similar/`, `/reviews/` ✅ |
| Related/Recommended (product page) | `GET /products/{slug}/related/`, `/similar/` ✅ — note: the dedicated `/recommendations/products/{slug}/...` rails (frequently-bought-together, also-viewed, etc.) confirmed to exist on the backend are not called anywhere in the frontend yet; not something you asked to fix, flagging for awareness only |
| Recently Viewed | *nothing* — `localStorage` only, real endpoint exists and is unused |
| Cart | `GET/POST /cart/...` ✅ |
| Wishlist | `GET/POST /wishlist/...` ✅ |

## D. Exact hard-coded/demo data to remove or bypass

- `data/hero.ts` (`heroSlides`) — used only by `HeroCarousel`
- `data/categories.ts` — used only by `ShopByCategory`
- `data/brands.ts` — used by `FeaturedBrands` and `SearchBar`'s idle state
- `data/editorial.ts` (`luxuryBanners`, `editorsPicks`) — used only by `LuxuryCollection`/`EditorsPicks`
- `lib/recentlyViewed.ts` localStorage-backed store — used by `RecentlyViewedTracker`, `RecentlyViewed`, and `SearchBar`
- `lib/demoMode.ts` + `app/api/demo-seed/route.ts` — the mechanism that can inject fake data into `recentlyViewed` at runtime
- `lib/search.ts`'s three dead functions (`searchProducts`, `searchBrandsByQuery`, `searchCategoriesByQuery`) — unreferenced, safe to delete outright

**Deliberately NOT flagged for removal:** `data/inspiration.ts`, `data/testimonials.ts`, `data/blog.ts`, `data/instagram.ts`, and `data/catalog/*` (the mock generator, admin-only). No backend data exists for the first four, and nothing customer-facing uses the last one.

## E. Backend API gaps discovered

1. **Hero/Banner endpoint unconfirmed.** You said the backend now has a `Banner` model with seeded banners, but the backend source I have on hand (from the zip provided earlier in this project) has no standalone `Banner` app — only a `banner_image`/`banner` *field* on the existing `Category`, `SubCategory`, `Brand`, and `Collection` models, each exposed through their own serializer, not a dedicated homepage-hero endpoint with its own ordering/CTA/link fields. Since you've told me not to touch the backend and I shouldn't guess at a URL, I need the exact endpoint (e.g., `GET /api/v1/banners/`) and its response shape confirmed before `HeroCarousel` can be wired to it correctly.
2. **No "recently popular / new-for-you" wiring**, mentioned above under C — not a gap in the backend (the endpoints exist), just an unused capability. Not fixing unless you want it.

---

Nothing has been changed. Waiting for your go-ahead on which items from Section B to fix.
