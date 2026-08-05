# Fashion Trendz — Frontend/Backend Integration Audit

No code has been modified. Every finding below was verified by reading the actual frontend source alongside the actual Django source — not by inspection of one side alone.

## Summary

| | Count |
|---|---|
| ❌ Broken | 3 |
| ⚠ Needs attention | 5 |
| ✅ Working | 20+ endpoints verified clean |

The three ❌ items will each cause a real, reproducible failure for a normal shopper (guest cart breaks cross-origin, logout doesn't revoke the refresh token, coupon codes always report "not active yet"). The ⚠ items are correctness or robustness gaps that won't necessarily be noticed immediately but should be fixed before launch.

---

## ❌ Broken

### 1. Guest cart / recently-viewed header rejected by CORS preflight

- **Frontend file:** `lib/api.ts` (`cartHeader` option, sends `X-Cart-Session`), used by `context/CartContext.tsx` and `components/product/RecentlyViewedTracker.tsx`
- **Backend file:** `config/settings.py` (`CORS_ALLOW_HEADERS`, line 565)
- **Exact problem:** `CORS_ALLOW_HEADERS` is set to django-cors-headers' unmodified default list:
  ```
  ["accept", "accept-encoding", "authorization", "content-type", "dnt", "origin", "user-agent", "x-csrftoken", "x-requested-with"]
  ```
  `x-cart-session` is not in it. The frontend and backend run on different origins (`localhost:3000` vs `localhost:8000` in dev — different origins by CORS's own definition — and will be different domains in production). Any cross-origin request that sets a non-default header triggers a preflighted `OPTIONS` request; the browser checks the response's `Access-Control-Allow-Headers` against the headers the real request wants to send, and blocks the request if `X-Cart-Session` isn't listed. Every guest-cart call (`/cart/`, `/cart/add/`, etc. with `cartHeader: true`) and the recently-viewed trail will fail in the browser before reaching Django at all — this cannot be seen in a Postman/curl test, only in an actual browser, which is presumably why it hasn't surfaced yet.
- **Exact fix:** add `"x-cart-session"` to `CORS_ALLOW_HEADERS` in `config/settings.py`:
  ```python
  CORS_ALLOW_HEADERS: list[str] = [
      "accept", "accept-encoding", "authorization", "content-type",
      "dnt", "origin", "user-agent", "x-csrftoken", "x-requested-with",
      "x-cart-session",
  ]
  ```

### 2. Logout clears tokens before making the authenticated logout call, so the refresh token is never revoked

- **Frontend file:** `context/AuthContext.tsx` (`logout` function)
- **Backend file:** `apps/users/views.py` (`LogoutAPIView`, `permission_classes = [IsAuthenticated]`)
- **Exact problem:**
  ```ts
  const logout = async () => {
    const refresh = tokenStore.getRefresh();
    tokenStore.clear();          // <- wipes the access token here
    setUser(null);
    if (refresh) {
      try {
        await api.post("/auth/logout/", { refresh });   // <- reads the access token AFTER it's gone
      } catch { /* ignore */ }
    }
  };
  ```
  `api.post` reads `tokenStore.getAccess()` at call time to build the `Authorization` header. Because `tokenStore.clear()` runs first, no `Authorization` header is attached, and `LogoutAPIView` (`IsAuthenticated`) rejects the request with 401 before `LogoutSerializer.save()` ever calls `.blacklist()`. The `catch { }` swallows the failure silently. Net effect: the client-side session ends, but the refresh token is never blacklisted server-side — it stays valid for its full 7-day lifetime. A refresh token captured before logout (XSS, shared device, stolen localStorage dump) remains usable after the user "logs out."
- **Exact fix:** call the logout endpoint before clearing local state:
  ```ts
  const logout = async () => {
    const refresh = tokenStore.getRefresh();
    if (refresh) {
      try {
        await api.post("/auth/logout/", { refresh });
      } catch { /* ignore */ }
    }
    tokenStore.clear();
    setUser(null);
  };
  ```

### 3. Checkout coupon field calls a backend placeholder that never applies a real discount

- **Frontend file:** `context/CartContext.tsx` (`applyCoupon`, posts to `/cart/apply-coupon/`), consumed by `app/checkout/review/page.tsx`
- **Backend file:** `apps/cart/services.py` (`apply_coupon`, lines 421–446) vs. `apps/coupons/services.py` (`apply_coupon_to_cart`, lines 224–250) / `apps/coupons/views.py` (`CouponViewSet.apply`, `/coupons/apply/`)
- **Exact problem:** the endpoint the frontend calls, `POST /cart/apply-coupon/`, is implemented by `apps.cart.services.apply_coupon`, whose docstring literally says: *"Capture a coupon code. **Placeholder — no discount is applied yet.**"* It stores whatever code was typed, sets `coupon_discount` to `Decimal("0.00")`, and always returns `{"message": "Coupon codes are not active yet."}` — regardless of whether the code is real, expired, or garbage. The actual working coupon system (validates the code against the `Coupon` table, checks expiry/usage/minimum order, computes a real discount) lives at a completely different, unused-by-the-frontend endpoint: `POST /coupons/apply/` (`CouponViewSet.apply`, `IsAuthenticated`). Every coupon a customer enters at checkout will report "Coupon codes are not active yet." even for a coupon that is valid and would work through the correct endpoint.
- **Exact fix:** point `CartContext.applyCoupon` (and `removeCoupon`) at the coupons module instead of the cart placeholder:
  ```ts
  const applyCoupon = async (code: string): Promise<string> => {
    const result = await api.post<{ message: string }>("/coupons/apply/", { code });
    await refresh();
    return result.message;
  };
  const removeCoupon = async () => {
    await api.post("/coupons/remove/", {});
    await refresh();
  };
  ```
  (`/coupons/validate/` is also available if a "preview without applying" step is ever wanted.)

---

## ⚠ Needs attention

### 4. Refresh-token rotation isn't persisted

- **Frontend file:** `lib/api.ts` (`refreshAccessToken`)
- **Backend file:** `config/settings.py` (`SIMPLE_JWT`: `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`)
- **Problem:** `refreshAccessToken()` only reads `json.data.access` from the `/auth/token/refresh/` response and calls `tokenStore.setAccess(access)`. With rotation enabled, SimpleJWT's `TokenRefreshView` also returns a new `refresh` value and blacklists the old one. The frontend never stores that new refresh token, so it keeps reusing the original (now-blacklisted) one on the next refresh — which will then fail, forcing an unexpected logout mid-session, typically 15 minutes to a few hours into a visit.
- **Fix:**
  ```ts
  const json = (await res.json()) as Envelope<{ access: string; refresh?: string }>;
  const access = json.data?.access;
  if (!access) return null;
  tokenStore.setAccess(access);
  if (json.data?.refresh) tokenStore.set(access, json.data.refresh);
  return access;
  ```

### 5. `apiFetchPaged` is missing the 204 short-circuit that `apiFetch` has

- **Frontend file:** `lib/api.ts`
- **Problem:** `apiFetch` returns early on `res.status === 204` (no body to parse). `apiFetchPaged` has no equivalent check, so a 204 response falls into `res.json().catch(() => null)`, which resolves `null`, then the `!json` check throws an `ApiError` for what is actually a successful empty response. None of the current `apiFetchPaged` call sites (`/wishlist/`, `/orders/`) return 204 today, so this hasn't fired yet, but it's a latent bug the moment any paginated endpoint legitimately returns no content.
- **Fix:** add the same guard used in `apiFetch` right after the `fetch` call in `apiFetchPaged`.

### 6. Order status is dropped by the view-model adapter

- **Frontend file:** `lib/apiAdapters.ts` (`apiOrderDetailToOrder`, `apiOrderSummaryToOrder`) / `types/order.ts` (`Order`), consumed by `app/orders/[orderId]/page.tsx`, `app/checkout/success/page.tsx`
- **Backend file:** `apps/orders/serializers.py` (`OrderDetailSerializer` exposes `status`, `status_display`, `is_cancellable`)
- **Problem:** the backend returns the real fulfilment state (`placed`, `packed`, `shipped`, `delivered`, `cancelled`, etc.) on every order response, but `apiOrderDetailToOrder` never maps it onto the `Order` type, and the order-detail page hardcodes a static `<Badge>Confirmed</Badge>` regardless of the order's actual state. A shipped, delivered, or cancelled order all show identically as "Confirmed." (`app/orders/page.tsx` is fine — it reads `status_display` straight off the raw `ApiOrderSummary` without going through the adapter.)
- **Fix:** add `status: string` and `statusDisplay: string` to the `Order` type, populate them in both adapter functions, and render `order.statusDisplay` instead of the hardcoded badge on the detail and success pages.

### 7. `CartContext` mints and permanently keeps a guest session key even for signed-in users

- **Frontend file:** `context/CartContext.tsx` (`ensureGuestSession`, called unconditionally at the top of `refresh()`)
- **Backend file:** `apps/cart/views.py` (`CartViewSet.resolve_cart`), `apps/cart/services.py` (`merge_carts`)
- **Problem:** `AuthContext.mergeGuestCartIfAny()` clears the stored guest session key once, right after login. But `CartContext.refresh()` — which runs on mount and after every cart mutation — calls `ensureGuestSession()` unconditionally, with no `isAuthenticated` check. The very next refresh after that one-time clear mints a brand-new random UUID and persists it in `localStorage`, then attaches it as `X-Cart-Session` on every future cart call, forever, even though the user is signed in. Because `resolve_cart()` treats any supplied header as a merge candidate, this makes every authenticated cart request run an extra, pointless `merge_carts(user, random_uuid)` — an extra cart lookup and session lookup per request. Not data-corrupting (`merge_carts` no-ops when the session key matches no cart), just permanent unnecessary load.
- **Fix:** guard `ensureGuestSession()`/the `cartHeader` option on `isAuthenticated`, e.g. only attach `X-Cart-Session` when there is no signed-in user.

### 8. `/addresses/` is paginated but the checkout page reads it as a flat array

- **Frontend file:** `app/checkout/page.tsx` (`api.get<ApiAddress[]>("/addresses/")`)
- **Backend file:** `apps/users/views.py` (`AddressViewSet`, no `pagination_class` override → inherits the project default `StandardPagination`, 20 per page)
- **Problem:** this isn't broken today because the envelope renderer always puts the current page's rows in `data`, so `api.get` (which reads `json.data`) still gets a usable array. But nothing reads the `pagination` metadata, and nothing sends `?page=`, so a customer with more than 20 saved addresses will silently never see addresses 21+ on the shipping step, with no indication that more exist.
- **Fix:** either switch to `apiFetchPaged` and add pagination UI, or set `pagination_class = None` on `AddressViewSet` if an address book is never expected to exceed one page in practice.

---

## ✅ Working

Verified request URL, method, payload shape against the serializer, response shape against the serializer, and permission class, for each of the following. No discrepancies found.

- **Auth:** `POST /auth/register/` (`RegisterSerializer`), `POST /auth/login/` (`LoginSerializer` — email field name confirmed via `USERNAME_FIELD = "email"` on the `User` model), `GET /profile/` (`IsAuthenticated`, `ProfileAPIView`)
- **Catalog:** `GET /categories/{slug}/`, `GET /subcategories/{slug}/`, `GET /products/homepage/`, `GET /products/{slug}/`, `GET /products/{slug}/related/`, `GET /products/{slug}/similar/`, `GET /products/{slug}/quick-view/`, `GET /products/{slug}/reviews/` (nested under `apps.reviews.urls`, confirmed path is `products/<slug:slug>/reviews/`, not under the products app itself), `GET /products/` + `GET /products/filters/` (listing + facets, `ProductFilter`), `GET /products/search/`, `GET /products/suggestions/` — all public, `auth: false`/`publicGet` used correctly throughout
- **Cart (guest and authenticated):** `GET /cart/`, `POST /cart/add/`, `/cart/remove/`, `/cart/update/`, `/cart/increase/`, `/cart/decrease/`, `/cart/save-for-later/`, `/cart/move-to-bag/`, `/cart/clear/` — every payload field name (`product`, `variant`, `quantity`, `include_saved`) matches its serializer exactly; `CartAccessPermission` (`AllowAny`) confirmed to authorize guests correctly by resolving identity from the request rather than a client-supplied id
- **Wishlist:** `GET /wishlist/` (correctly uses `apiFetchPaged`, matches `StandardPagination`), `POST /wishlist/add/`, `/remove/`, `/toggle/` — field name `product` (slug) matches `WishlistActionSerializer` exactly; `IsAuthenticated` correctly enforced and handled (`requireAuth()` gate before every call)
- **Checkout / orders:** `GET /addresses/`, `POST /addresses/` (field names match `AddressSerializer` exactly), `POST /checkout/place-order/` (`shipping_address`, `payment_method`, `delivery_method` match `PlaceOrderSerializer`), `GET /orders/`, `GET /orders/{order_number}/` (lookup regex `FT-ORD-[0-9]{8}-[A-Z0-9]{6}` matches the `order_number` values the frontend receives and reuses)
- **Envelope / pagination:** `Envelope<T>` shape matches `EnvelopeJSONRenderer` exactly; `apiFetch`'s unwrap-to-`data` and `apiFetchPaged`'s `{data, pagination}` split both match the renderer's pagination-hoisting behavior
- **Image URLs:** `next.config.ts` allows `localhost:8000` / `127.0.0.1:8000` (Django dev media server) plus the two Unsplash/pravatar placeholder hosts used elsewhere in the mock data — consistent with `MEDIA_URL` being served locally in `DEBUG`
- **Env vars:** `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` matches `config/urls.py`'s `api/v1/` mount exactly; `CORS_ALLOWED_ORIGINS` default in `.env.example` (`http://localhost:3000,http://127.0.0.1:3000`) matches the frontend's dev origin

---

## Endpoint Mapping Table

Every backend endpoint the frontend calls, traced end to end.

| Frontend Page | Component | API Function | HTTP Request | Django URL | View/ViewSet | Serializer | Model |
|---|---|---|---|---|---|---|---|
| `/login` | `LoginForm` | `useAuth().login` → `api.post` | `POST /auth/login/` | `users/urls.py` → `auth/login/` | `LoginAPIView` (`TokenObtainPairView`) | `LoginSerializer` | `User` |
| `/register` | `RegisterPage` | `useAuth().register` → `api.post` | `POST /auth/register/` | `auth/register/` | `RegisterAPIView` | `RegisterSerializer` | `User` |
| any (Navbar) | `Navbar` | `useAuth().logout` → `api.post` | `POST /auth/logout/` | `auth/logout/` | `LogoutAPIView` | `LogoutSerializer` | — (blacklist) |
| any | `lib/api.ts` | `refreshAccessToken` | `POST /auth/token/refresh/` | `auth/token/refresh/` | `TokenRefreshView` (SimpleJWT) | — | — |
| any (on mount) | `AuthProvider` | `api.get` | `GET /profile/` | `profile/` | `ProfileAPIView` | `UserSerializer` | `User` |
| `/` | `Home` | `publicGet` | `GET /products/homepage/` | `products/urls.py` → router | `ProductViewSet.homepage` | `ProductCardSerializer` | `Product` |
| `/product/[slug]` | `ProductPage` | `publicGet` | `GET /products/{slug}/` | `products/{slug}/` | `ProductViewSet.retrieve` | `ProductDetailSerializer` | `Product`, `ProductVariant` |
| `/product/[slug]` | `ProductPage` | `publicGet` | `GET /products/{slug}/related/` | `products/{slug}/related/` | `ProductViewSet.related` | `ProductCardSerializer` | `Product` |
| `/product/[slug]` | `ProductPage` | `publicGet` | `GET /products/{slug}/similar/` | `products/{slug}/similar/` | `ProductViewSet.similar` | `ProductCardSerializer` | `Product` |
| `/product/[slug]` | `ProductPage` | `publicGetPaged` | `GET /products/{slug}/reviews/` | `apps.reviews.urls` → `products/<slug>/reviews/` | `ProductReviewViewSet.list` | `ReviewSerializer` | `Review` |
| `ProductCard` (everywhere) | `ProductCard` | `api.get` | `GET /products/{slug}/quick-view/` | `products/{slug}/quick-view/` | `ProductViewSet.quick_view` | `ProductQuickViewSerializer` | `Product`, `ProductVariant` |
| `/[category]` | `CategoryPage` | `publicGet` | `GET /categories/{slug}/` | `catalog/urls.py` → router | `CategoryViewSet.retrieve` | `CategorySerializer` | `Category` |
| `/[category]/[subcategory]` | `SubcategoryPage` | `publicGet` | `GET /subcategories/{slug}/` | `catalog/urls.py` → router | `SubCategoryViewSet.retrieve` | `SubCategorySerializer` | `SubCategory` |
| `/[category]`, `/[category]/[subcategory]`, `/new-in`, `/search` | `ProductListingLayout` (via `fetchProductListing`) | `publicGetPaged` | `GET /products/?…` | `products/` | `ProductViewSet.list` | `ProductCardSerializer` | `Product` |
| same as above | `ProductListingLayout` | `publicGet` | `GET /products/filters/?…` | `products/filters/` | `ProductViewSet.filters` | `ProductFacetsSerializer` | `Product` (aggregated) |
| `/search` (autocomplete) | `SearchBar` → `app/api/search-suggestions` | `publicGet` | `GET /products/suggestions/?q=` | `products/suggestions/` | `ProductViewSet.suggestions` | `SearchSuggestionsSerializer` | `Product`, `Brand`, `Category` |
| `/search` (autocomplete) | `SearchBar` → `app/api/search-suggestions` | `publicGetPaged` | `GET /products/search/?q=` | `products/search/` | `ProductViewSet.search` | `ProductCardSerializer` | `Product` |
| Navbar / cart drawer, `/checkout/*` | `CartContext` | `api.get` | `GET /cart/` | `cart/urls.py` → router | `CartViewSet.list` | `CartSerializer` | `Cart`, `CartItem` |
| `ProductOptions` | `CartContext.addToCart` | `api.post` | `POST /cart/add/` | `cart/add/` | `CartViewSet.add` | `AddToCartSerializer` | `Cart`, `CartItem` |
| Cart drawer/page | `CartContext.removeFromCart` | `api.post` | `POST /cart/remove/` | `cart/remove/` | `CartViewSet.remove` | `CartLineSerializer` | `CartItem` |
| Cart drawer/page | `CartContext.updateQuantity` | `api.post` | `POST /cart/update/` | `cart/update/` | `CartViewSet.update_quantity` | `UpdateQuantitySerializer` | `CartItem` |
| Cart drawer/page | `CartContext.increment`/`decrement` | `api.post` | `POST /cart/increase/`, `/cart/decrease/` | same | `CartViewSet.increase`/`decrease` | `CartLineSerializer` | `CartItem` |
| Cart page | `CartContext.saveForLater`/`moveToCartFromSaved` | `api.post` | `POST /cart/save-for-later/`, `/cart/move-to-bag/` | same | `CartViewSet.save_for_later`/`move_to_bag` | `CartLineSerializer` | `CartItem` |
| Cart page | `CartContext.emptyCart` | `api.post` | `POST /cart/clear/` | `cart/clear/` | `CartViewSet.clear` | — | `CartItem` |
| `/checkout/review` | `ReviewStep` | `CartContext.applyCoupon`/`removeCoupon` | `POST /cart/apply-coupon/`, `/cart/remove-coupon/` | `cart/apply-coupon/` etc. | `CartViewSet.apply_coupon`/`remove_coupon` | `CouponSerializer` | `Cart` (**placeholder — see ❌ #3**) |
| Navbar, wishlist page | `WishlistContext.refresh` | `apiFetchPaged` | `GET /wishlist/` | `wishlist/urls.py` → router | `WishlistViewSet.list` | `WishlistItemSerializer` | `Wishlist`, `WishlistItem` |
| `ProductCard`, `ProductOptions` | `WishlistContext.addToWishlist`/`toggleWishlist` | `api.post` | `POST /wishlist/add/`, `/wishlist/toggle/` | `wishlist/add/`, `/toggle/` | `WishlistViewSet.add`/`toggle` | `WishlistActionSerializer` | `WishlistItem` |
| wishlist page | `WishlistContext.removeFromWishlist` | `api.post` | `POST /wishlist/remove/` | `wishlist/remove/` | `WishlistViewSet.remove` | `WishlistActionSerializer` | `WishlistItem` |
| `/checkout` | `ShippingStep` | `api.get`/`api.post` | `GET /addresses/`, `POST /addresses/` | `users/urls.py` → router (`addresses`) | `AddressViewSet.list`/`create` | `AddressSerializer` | `Address` |
| `/checkout/review` | `ReviewStep` | `api.post` | `POST /checkout/place-order/` | `orders/urls.py` → router (`checkout`) | `CheckoutViewSet.place_order` | `PlaceOrderSerializer` → `OrderDetailSerializer` | `Order`, `OrderItem` |
| `/orders` | `OrdersPage` | `apiFetchPaged` | `GET /orders/` | `orders/urls.py` → router (`orders`) | `OrderViewSet.list` | `OrderSummarySerializer` | `Order` |
| `/orders/[orderId]`, `/checkout/success` | `OrderDetailPage`, `OrderSuccessPage` | `api.get` | `GET /orders/{order_number}/` | `orders/{order_number}/` | `OrderViewSet.retrieve` | `OrderDetailSerializer` | `Order`, `OrderItem` |

---

## Recommended fix order

1. CORS header allowlist (❌ #1) — one-line settings change, unblocks the entire guest-cart feature.
2. Coupon endpoint (❌ #3) — one function body change in `CartContext.tsx`, unblocks a checkout feature that currently cannot work at all.
3. Logout ordering (❌ #2) — reorder four lines in `AuthContext.tsx`, closes a real security gap.
4. Refresh-token rotation storage (⚠ #4) — a few lines in `lib/api.ts`, prevents random mid-session logouts.
5. The remaining ⚠ items (#5–#8) are lower urgency — a latent edge case, a cosmetic status gap, a minor inefficiency, and a pagination edge case respectively.

Say which of these you want fixed and I'll make the changes.
