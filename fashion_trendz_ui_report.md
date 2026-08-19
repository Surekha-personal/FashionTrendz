# Fashion Trendz — Complete UI Report

Read-only audit of every route and every UI component in the frontend, done by reading the actual source (not by rendering the site). Purpose: give you a single reference for refining the UI — what exists, how it's built, and what's actually broken or inconsistent today.

## 1. Design system

The site is built on Tailwind v4 with shadcn/ui primitives, Framer Motion for animation, Lucide for icons, and embla-carousel for every carousel. Typography uses three font families loaded via `next/font/google`: Inter for body text, Playfair Display for all headings (`h1`–`h4` and anything with `font-heading`), and Geist Mono (declared but not visibly used anywhere in the UI — it's wired into the CSS variables but no component references a monospace style).

Color tokens live in `app/globals.css` as CSS custom properties, consumed through Tailwind's `@theme inline` mapping (`bg-background`, `text-foreground`, `bg-accent`, etc.):

| Token | Light value | Role |
|---|---|---|
| `background` / `foreground` | `#fafafa` / `#111111` | Page background and default text |
| `primary` / `primary-foreground` | `#111111` / `#fafafa` | Near-black — the announcement bar, flash sale section, footer newsletter CTA, back-to-top button |
| `accent` / `accent-foreground` | `#e91e63` / `#ffffff` | The one brand color — pink/magenta. Used for prices-on-sale styling, active filter states, wishlist hearts, ratings stars, CTAs, focus rings |
| `secondary` / `muted` | `#f2f2f2` / `#f0f0f0` | Card backgrounds, image placeholders, subtle section tints |
| `border` / `input` | `#e5e5e5` | All hairline borders and form field borders |
| `destructive` | `oklch(0.577 0.245 27.325)` (red) | Form errors, out-of-stock/error text |

A full parallel `.dark` palette exists (inverted near-black background, same pink accent) and is CSS-complete, but there is no `ThemeProvider` anywhere in the app and no UI control to switch modes — `next-themes` is only referenced inside the shadcn `Toaster` component. In practice dark mode is unreachable; the CSS just sits unused unless a user's OS/browser forces a `.dark` class some other way (it doesn't, since nothing toggles that class).

Corner radius is a single scale driven by one `--radius: 1rem` variable (`radius-sm` through `radius-4xl` are all multiples of it), which is why every card, image tile, button, and input across the site shares the same rounded, soft aesthetic. Section rhythm is consistent: almost every homepage section and listing page wraps content in `mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8` (or `py-8` for utility pages like cart/orders), so horizontal margins and vertical spacing are already systematized — a genuine strength to preserve when refining.

Motion is centralized in `lib/motion.ts` (`fadeInUp`, `fadeIn`, `scaleIn`, `staggerContainer`, all Framer Motion variants) and reused everywhere — homepage sections fade/slide up on scroll into view, grids stagger their children in. This is applied consistently, which is good, but it also means every homepage section performs its own `whileInView` scroll-trigger; on a long homepage (11 stacked sections) this is a lot of independent IntersectionObservers and could be worth auditing for jank on lower-end devices.

## 2. Global chrome (present on every page)

**Announcement bar** — a single-row, infinitely scrolling marquee (CSS `@keyframes marquee`) on a near-black background, cycling three hardcoded promotional strings ("Free shipping on orders above ₹1,999", etc.). Purely decorative, not backend-driven, no dismiss button.

**Navbar** — sticky, blurred background on scroll (adds a shadow once scrolled), containing: a hamburger trigger (mobile only), the wordmark "Fashion Trendz" in Playfair, a desktop-only mega menu, a desktop-only search bar (capped at `max-w-xs`, which is fairly narrow for a primary search box on a fashion site), then wishlist/account/cart icons. The wishlist and cart icons both show an animated spring-in count badge. The account icon is a dropdown showing "Hi, {name}" or a Login link, plus Orders and Logout — there's no link to a proper account/profile/addresses page from here (none exists in the app at all — see gaps below).

**Mega menu** — desktop only, built on Radix's `NavigationMenu`, driven entirely by a **static local file** (`data/navigation.ts` → `data/catalog/categories.ts`), not the live backend `/categories/` endpoint. It auto-splits each category's subcategories into 2–3 columns plus two "Featured" tiles ("New In X" / "Trending in X") that are just text-and-emoji-less placeholder tiles (`role="img"` span with a gray box and the word "Featured" — no actual image, despite `imageAlt` being defined on the data). This is a real visual gap: those featured tiles in the mega menu render as flat gray placeholder boxes, not imagery, on every single category dropdown.

**Mobile nav** — a left-side `Sheet` with the same static nav data collapsed into an accordion. Functionally fine, consistent with desktop.

**Search bar** — the most complex piece of chrome. Debounced (150 ms) suggestions from `/api/search-suggestions`, categorized into Categories/Brands/Products with text highlighting, full keyboard navigation (arrow keys, enter, escape), an idle state showing Recent Searches (localStorage), Recently Viewed (live backend, thumbnails), Trending Searches (static list), and Popular Brands (live backend). This is genuinely well-built. One inconsistency: recent searches are stored under a *different* key (`ft_recent_searches`) and mechanism than everything else in the app, which otherwise centralizes storage keys in `lib/storage.ts` — worth reconciling for consistency, not a functional bug.

**Cart drawer** — a right-side `Sheet` triggered from the bag icon, showing line items, savings, subtotal, and "View Bag" / "Checkout" buttons. Consistent styling with the full cart page.

**Footer** — four columns (brand blurb + newsletter form, Shop, Help, Company) plus a bottom bar with copyright and social links. This is the single biggest source of broken navigation in the app: **Help → Track Order** points to `/orders` (fine), but **Returns & Exchanges, Shipping Info, Contact Us** (`/help/returns`, `/help/shipping`, `/help/contact`), all of **Company** (`/about`, `/careers`, `/legal/terms`, `/legal/privacy`), and the social links (`instagram.com`, `twitter.com`, `facebook.com` — not your actual profile URLs) have no corresponding pages or real destinations anywhere in the app — they will 404 or leave the site. The footer also links directly to `/admin` labeled "Admin Preview," in plain text, on every single page for every visitor (see the Admin section below for why that's worth reconsidering before this goes live).

**Back to top** — a floating circular button, bottom-right, fades in after 480px of scroll. Small, unobtrusive, works well.

## 3. Homepage (`/`)

Eleven sections stacked vertically, all server-fetched in parallel and passed down as props (this part of the architecture is solid — no client-side waterfall). In order:

1. **Hero Carousel** — full-bleed, autoplay embla carousel (5.5s) backed by the live Banner API, animated text overlay, dot indicators, arrows. Recently migrated from static to backend-driven (see prior work in this conversation) — this is the one section explicitly already re-verified end-to-end.
2. **Shop By Category** — asymmetric grid (first tile spans 2 columns on mobile), image tiles with a gradient overlay, category name, and an arrow badge. Backend-driven, has an empty-state guard.
3. **Trending Now** — a `ProductCarouselSection` (generic, reused 4× across the homepage) — embla carousel of `ProductCard`s with arrows hidden below `sm`.
4. **Featured Brands** — a plain text-in-a-box grid (brand name in Playfair, no logos rendered even though `ApiBrand.logo` exists in the type — logos are fetched but never displayed here, this section is purely typographic).
5. **New Arrivals** — a static grid (not a carousel) of `ProductCard`s, 2/3/4 columns responsive, links to `/new-in`.
6. **Best Sellers** — another `ProductCarouselSection`, tinted background (`bg-muted/40`) to visually separate it from neighboring white sections.
7. **Luxury Collection** — full-width alternating-side editorial banners (odd banners flip to right-aligned text + reversed gradient), large imagery, outline CTA button.
8. **Flash Sale** — the one section with an inverted (near-black) background, a `CountdownTimer`, and a product carousel. **The countdown is fake**: `SALE_END = now + 18.5 hours`, computed fresh on every page load/request — it never actually reaches zero from a real backend-defined sale window, so it's permanently "always about 18 hours left," which will look broken/dishonest to a returning visitor who reloads and sees the same countdown again.
9. **Editor's Picks** — 2-column grid, first tile spans full width at 16:9, rest at 4:5, editorial imagery with eyebrow/title/description overlay. Backend-driven (recently fixed to use the real collection filter).
10. **Trending This Week** — another `ProductCarouselSection`, no "View All" link this time (inconsistent with the other carousels, which all link somewhere).
11. **Fashion Inspiration** — a Pinterest-style CSS column masonry (`columns-2/3/4`), hover caption overlay. Backed by static local data (`data/inspiration.ts`) — intentionally out of scope from earlier backend-migration work, still fine as editorial content, but worth knowing it's not dynamic.
12. **Customer Reviews** — carousel of testimonial cards with avatar, rating, quote. Static data (`data/testimonials.ts`).
13. **Fashion Blog** — 3-column card grid, "Read More" links to `/blog/[slug]`-style hrefs and "View All" to `/blog`. **None of these routes exist** — every blog card and the section's View All link are dead ends.
14. **Instagram Gallery** — 2×4/4×N image grid with like-count hover overlay, links out to `post.href`. Static data (`data/instagram.ts`).
15. **Newsletter Section** — dark rounded banner, email capture form. **Not functional** — `NewsletterForm`'s submit handler just waits 400ms and shows a success toast; no request is ever sent anywhere, so subscriptions are not actually captured. This exact form is reused (styled differently) in the footer too, so the same non-functional behavior exists in two places.

## 4. Product listing pages (category, subcategory, sale presets, search, new-in)

All five listing entry points (`/[category]`, `/[category]/[subcategory]`, `/search`, `/new-in`, plus the `/sale/[preset]` variants) funnel into one shared component, `ProductListingLayout`, so their UI is close to identical by design: breadcrumb, title + description, a two-column layout with a sticky desktop filter sidebar and a product grid, pagination with ellipsis-collapsed page numbers.

`ProductFilters` is thorough — accordion sections for Price (manual min/max + submit), Gender, Discount tiers, Rating, Brand (scrollable checkbox list), Color (pill buttons, no actual color swatches even though `ProductOptions` on the PDP has a `COLOR_HEX` map that could be reused here for consistency), Size (pill buttons), Material, Occasion, and Availability. Active filters surface as removable chips above the accordion. This is a solid, complete filter UI.

**Confirmed layout bug**: the mobile "Filters" trigger is a native `<details>/<summary>` disclosure with its dropdown panel styled `absolute z-30 mt-2 w-72 ...`. None of its ancestor elements (`<div className="flex items-center gap-2">`, its parent, or anything up to `<body>`) declare `position: relative`. An `absolute` element positions itself against the nearest *positioned* ancestor — since there isn't one here, this filter panel will not anchor under the "Filters" button on mobile; it will jump to align against the page's root positioning context instead, most likely rendering in the wrong place on screen (top-left-ish) rather than as a dropdown beneath the button. This is worth fixing with a one-line `relative` class on the `<details>` element or its wrapper.

Sort control (`SortSelect`) is a bare, unstyled-by-shadcn native `<select>` — functionally fine, but visually it's the one dropdown on the entire site not using the shadcn `Select` component that's used for filters/gender/etc. elsewhere (well, filters actually use accordions + checkboxes, not a `Select` either — but the point stands that native `<select>` here, and again in the checkout State/Bank/Wallet dropdowns, look like plain OS-styled dropdowns next to an otherwise fully custom-styled UI). This is a minor visual inconsistency worth a pass if you want a fully polished look.

Empty state (no results) uses the shared `EmptyState` pattern — icon, message, "Clear Filters" button. Consistent and fine.

## 5. Product detail page (`/product/[slug]`)

Two-column layout: an embla `ProductGallery` (main carousel + thumbnail strip below) on the left, sticky purchase panel on the right (brand link, name, rating, price/discount, `ProductOptions`, delivery/returns/authenticity trust badges, an accordion for Description/Specifications/Wash Care). Below the fold: a star-distribution review summary next to a scrollable review list, then "Related Products" and "Recommended Products" carousels (only rendered if non-empty), then a "Recently Viewed" carousel excluding the current product.

`ProductOptions` renders color swatches from a large hardcoded `COLOR_HEX` map (20 named colors) — any backend color name not in that map silently falls back to a flat gray swatch (`#cccccc`), which would look like a bug (all-gray dot) for any color outside that specific list. Add to Bag is correctly disabled until real variant data has loaded and correctly blocks submission with a toast if size/color combination doesn't resolve to a real SKU — good defensive UX, no fake "added to cart" states.

Two structural findings worth knowing: the quick-view modal on `ProductCard` duplicates a good chunk of this same purchase-panel logic rather than reusing `ProductOptions`+gallery consistently (it does reuse `ProductOptions`, but the image side of quick-view is a single static image, not the gallery), and the PDP itself has no "you're viewing this product" recently-viewed dedupe issue since it explicitly filters the current slug out client-side.

## 6. Cart (`/cart`) and cart drawer

Two-column cart page: line items (with quantity stepper, remove, "save for later," "move to wishlist") on the left, a separate "Saved For Later" card below if any exist, order summary card on the right with subtotal/savings/CTA to checkout. Empty state uses the shared pattern. The header's `CartDrawer` mirrors this same information in miniature. Both are visually consistent and functionally complete — no fake/mock cart data.

## 7. Wishlist (`/wishlist`)

Straightforward responsive grid of `WishlistCard`s (image, discount badge, name/brand/price, "Move to Bag," remove). Empty state consistent with the rest of the app. Nothing notable to flag here — this page is clean.

## 8. Checkout flow (`/checkout`, `/checkout/delivery`, `/checkout/payment`, `/checkout/review`, `/checkout/success`)

A 4-step wizard (Shipping → Delivery → Payment → Review) with a shared `CheckoutStepper` (numbered circles, connecting progress line, completed steps get a checkmark) rendered once in `app/checkout/layout.tsx`, so it's consistent across steps and correctly hidden on the success page. The layout also gates the entire flow behind authentication (redirects to `/login?next=...`) and an empty-cart guard — sensible, since the backend's order endpoints require auth.

Shipping step supports saved addresses (radio-card style selection) or a new-address form with full Zod validation (Indian mobile/pincode patterns). Delivery step is a card-radio list of delivery options with computed shipping fees. Payment step is the most elaborate: five payment method tabs (UPI/Card/Net Banking/Wallet/COD) each with their own sub-form and format validation — but **all of it is cosmetic**. Only the selected method code is ever sent to the backend; no gateway is wired up, so a UPI ID or a 16-digit card number is validated client-side purely for realism and then discarded. This isn't a bug exactly (it's explicitly commented in the code as a known placeholder pending a real Razorpay integration), but from a pure UI-content standpoint, it's presenting fully-interactive payment forms that don't do what they visually imply.

Review step ties it together: item list, editable summaries of address/delivery/payment (each with an "Edit" link back to that step), a working coupon apply/remove flow tied to the live cart summary, and a full price breakdown pulled from the real backend cart summary (subtotal/discount/coupon/tax/shipping/platform fee/grand total) — this part is fully live-data-driven, not mocked.

Success page has a nice spring-in checkmark animation, order summary card, and a working "Download Invoice" button that generates a real client-side PDF via `lib/generateInvoicePdf.ts`.

## 9. Orders (`/orders`, `/orders/[orderId]`)

List page: auth-gated, live-fetched order cards with stacked preview thumbnails, status badge, date, item count, total. Detail page: full item list, shipping address, complete price breakdown, payment method, estimated delivery, and the same invoice-download button. Both are clean, consistent with the rest of the app's card/typography language, and fully backend-driven — no mock data here.

## 10. Auth (`/login`, `/register`)

Both are minimal centered cards. This is the one place in the app with a real form-handling inconsistency: every other form on the site (newsletter, checkout shipping address) uses `react-hook-form` + Zod with inline field-level error messages, but Login and Register use plain `useState` with only native HTML `required`/`type="email"` validation on the client (server-side field errors from Django *are* surfaced for Register, but there's no client-side password-confirmation match check, no password strength/length hint, no show/hide-password toggle, and no "Forgot password?" link or flow anywhere in the app). Functionally these pages work, but they're visually and technically the least polished forms in the product relative to everything else.

## 11. Admin preview (`/admin`)

Worth flagging clearly since it's linked from the public footer of every page: this dashboard is **entirely fake data** — hardcoded stats ("1,284 Total Orders," "3,410 Customers," a fabricated ₹18.4L revenue figure), a sales chart, and a "Recent Products" list all sourced from the old static `data/catalog` mock dataset (not the live backend), plus a "Recent Orders" table that reads from `localStorage` (`lib/orders.ts`) and falls back to three hardcoded fake customer names/orders if nothing's there. It has `robots: { index: false }` (keeps it out of search engines) but **no authentication gate at all** — anyone who clicks "Admin Preview" in the footer, or just navigates to `/admin` directly, sees a dashboard that looks like real business data but isn't. Before this goes live, this either needs a real auth gate, an explicit "demo data" disclaimer on the page itself, or removal of the public footer link (or all three).

## Summary: concrete issues worth fixing, ranked by impact

**Broken navigation** — Footer's Help/Company links (`/help/*`, `/about`, `/careers`, `/legal/*`), the blog section's links (`/blog`, `/blog/[slug]`), and the footer's social links (placeholder domains, not real profiles) all point to routes that don't exist. This is the single highest-visibility gap since footer links are present on every page.

**Mobile filter dropdown mispositioning** — `ProductFilters`' mobile trigger panel has no positioned ancestor, so it likely renders detached from the "Filters" button instead of as an anchored dropdown. One-line CSS fix (add `relative` to the trigger's wrapper).

**Mega menu content is stale relative to the backend** — the top navigation and mobile menu are still built from a static local category list, separate from the live `/categories/` data that now powers the homepage rail and listing pages. If backend categories/subcategories ever diverge from the hardcoded set in `data/catalog/categories.ts`, the nav and the actual catalog will disagree.

**Mega menu featured tiles have no imagery** — every category dropdown shows two gray placeholder boxes labeled "Featured" instead of actual promotional images, despite the data model having an `imageAlt` field that implies an image was intended.

**Non-functional newsletter capture** (both instances — footer and homepage section) — visually complete, but doesn't submit anywhere; subscriptions are silently lost.

**Fake flash-sale countdown** — resets to ~18.5 hours on every request rather than counting down to a real, fixed backend-defined end time, which will look glitchy to anyone who reloads the page.

**Publicly linked, unauthenticated, fully-mocked admin dashboard** — a trust/security concern more than a visual one, but very much a "UI surface" the user asked about.

**Minor styling inconsistencies** — native unstyled `<select>` elements (sort, state, bank, wallet) next to an otherwise fully custom shadcn-styled UI; product color swatches fall back to flat gray for any color name outside a fixed 20-color hardcoded map; Login/Register forms lack the Zod validation, password visibility toggle, and forgot-password flow present in spirit elsewhere in the app; dark mode CSS is fully defined but entirely unreachable (no toggle, no `ThemeProvider`) — either wire it up or consider removing the dead `.dark` block to reduce confusion for whoever edits `globals.css` next.

None of the above required any file changes to identify — this is a pure read of the current source. Happy to scope and implement fixes for any subset of these once you tell me which ones you want tackled first.
