"""Prose for the 41 tables that exist in the shipped backend.

Column grids come from ``introspect.py``. What is authored here is the part
introspection cannot know: why a table exists, what it relates to, which API
endpoints read and write it, and which frontend pages depend on it.
"""

from __future__ import annotations

# Each entry: table, module, section, purpose, relationships, apis, pages
IMPLEMENTED: list[dict[str, str]] = [
    # -- Authentication & users --------------------------------------------
    dict(
        table="users_user",
        module="AUTHENTICATION & USER MANAGEMENT",
        section="Users & Auth",
        purpose=(
            "Customer and staff accounts. Email is the login identifier — there is no "
            "separate username column — so the unique index on email is the credential "
            "lookup path for every sign-in. Passwords are stored as PBKDF2 hashes in the "
            "inherited password column; the application never stores plaintext."
        ),
        rel=(
            "Parent of Address, Wishlist, Cart, Order, Review, HelpfulVote, "
            "CouponUsage, RecentlyViewed, Notification and NotificationPreference. "
            "Bridged to auth_group and auth_permission for Django RBAC."
        ),
        apis=(
            "POST /auth/register · POST /auth/login · POST /auth/logout · "
            "POST /auth/token/refresh · POST /auth/token/verify · "
            "POST /auth/forgot-password · POST /auth/reset-password · "
            "POST /auth/change-password · GET|PATCH /profile"
        ),
        pages="Sign In, Register, Forgot Password, Reset Password, My Account, Profile",
    ),
    dict(
        table="users_address",
        module="AUTHENTICATION & USER MANAGEMENT",
        section="Users & Auth",
        purpose=(
            "Delivery and billing addresses belonging to a customer. Exactly one address "
            "per customer may carry is_default = TRUE; that invariant is enforced by a "
            "partial unique index rather than by application code, so two concurrent "
            "'make this default' requests cannot both win."
        ),
        rel=(
            "Child of users_user (CASCADE). Read at checkout and snapshotted into "
            "orders_order.shipping_address as JSONB — the order keeps its own frozen copy, "
            "so editing an address never rewrites delivery history."
        ),
        apis="GET|POST /addresses · GET|PATCH|DELETE /addresses/{id}",
        pages="My Account → Addresses, Checkout → Delivery Address",
    ),
    dict(
        table="users_user_groups",
        module="AUTHENTICATION & USER MANAGEMENT",
        section="Users & Auth",
        purpose=(
            "Bridge assigning users to Django auth groups. Carries the role model today; "
            "the proposed admin_role / admin_role_permission tables supersede it for "
            "fine-grained back-office RBAC."
        ),
        rel="Bridge: users_user ↔ auth_group. Composite unique on (user_id, group_id).",
        apis="Django admin only. Not exposed on the public API.",
        pages="Django Admin → Users",
    ),
    dict(
        table="users_user_user_permissions",
        module="AUTHENTICATION & USER MANAGEMENT",
        section="Users & Auth",
        purpose="Bridge granting individual Django permissions directly to a user.",
        rel="Bridge: users_user ↔ auth_permission. Composite unique on (user_id, permission_id).",
        apis="Django admin only.",
        pages="Django Admin → Users",
    ),

    # -- Catalog ------------------------------------------------------------
    dict(
        table="catalog_category",
        module="CATALOG TAXONOMY",
        section="Catalog",
        purpose=(
            "Top level of the merchandising tree (Women, Men, Kids, Accessories…). "
            "Carries its own SEO block and four separate image slots because the same "
            "category is rendered as a nav tile, a mega-menu panel, a landing banner and "
            "a homepage card, each at a different aspect ratio."
        ),
        rel=(
            "Parent of catalog_subcategory and products_product (PROTECT — a category "
            "with live products cannot be deleted). Bridged to Brand, Collection and Coupon."
        ),
        apis=(
            "GET /categories · /categories/tree · /categories/mega-menu · "
            "/categories/homepage · /categories/featured · /categories/trending · "
            "/categories/luxury · /categories/{slug} · /categories/{slug}/subcategories · "
            "/categories/{slug}/brands · /categories/{slug}/collections"
        ),
        pages="Header Mega Menu, Homepage Category Strip, Category Landing, Breadcrumbs",
    ),
    dict(
        table="catalog_subcategory",
        module="CATALOG TAXONOMY",
        section="Catalog",
        purpose=(
            "Second level of the tree (Dresses, Shirts, Sarees…). This is the unit the "
            "recommendation engine treats as a neighbourhood: 'Dresses' is a useful "
            "related-products scope, 'Women' is the whole store."
        ),
        rel=(
            "Child of catalog_category (CASCADE). Parent of products_product (PROTECT). "
            "Name is unique per parent category, not globally — 'Shirts' may exist under "
            "both Men and Women."
        ),
        apis="GET /subcategories · /subcategories/{slug} · /categories/{slug}/subcategories",
        pages="Mega Menu columns, Category Landing filter rail, Product Listing",
    ),
    dict(
        table="catalog_brand",
        module="CATALOG TAXONOMY",
        section="Catalog",
        purpose=(
            "Brand master. popularity_score is a denormalised ranking input maintained by "
            "the application so the brand rails sort without joining orders."
        ),
        rel=(
            "Parent of products_product (PROTECT). Bridged many-to-many to Category via "
            "catalog_brand_categories, and to Coupon via coupons_coupon_brands."
        ),
        apis=(
            "GET /brands · /brands/featured · /brands/luxury · /brands/popular · "
            "/brands/top · /brands/{slug} · /categories/{slug}/brands"
        ),
        pages="Brand Directory, Brand Landing, Homepage Featured Brands, Filter rail",
    ),
    dict(
        table="catalog_brand_categories",
        module="CATALOG TAXONOMY",
        section="Catalog",
        purpose="Bridge: which categories a brand sells into. Drives the per-category brand rail.",
        rel="Bridge: catalog_brand ↔ catalog_category. Composite unique on (brand_id, category_id).",
        apis="GET /categories/{slug}/brands",
        pages="Category Landing → Shop by Brand",
    ),
    dict(
        table="catalog_collection",
        module="CATALOG TAXONOMY",
        section="Catalog",
        purpose=(
            "Curated merchandising groupings — New Arrivals, Trending, Luxury, Editor's "
            "Picks, Best Sellers, Seasonal. The type column classifies the rail so the "
            "homepage can request one without hard-coding slugs."
        ),
        rel=(
            "Referenced by products_product.collection_id (SET NULL). Bridged to Category "
            "via catalog_collection_categories."
        ),
        apis=(
            "GET /collections · /collections/featured · /collections/homepage · "
            "/collections/editors-picks · /collections/seasonal · /collections/{slug}"
        ),
        pages="Homepage rails, Collection Landing, Seasonal Campaign pages",
    ),
    dict(
        table="catalog_collection_categories",
        module="CATALOG TAXONOMY",
        section="Catalog",
        purpose="Bridge scoping a collection to one or more categories.",
        rel="Bridge: catalog_collection ↔ catalog_category.",
        apis="GET /categories/{slug}/collections",
        pages="Category Landing → Collections strip",
    ),

    # -- Products -----------------------------------------------------------
    dict(
        table="products_product",
        module="PRODUCT CATALOG",
        section="Products",
        purpose=(
            "The master product record and the widest table in the schema at 57 columns. "
            "Holds identity, taxonomy, pricing, thirteen fashion attributes, logistics "
            "copy, six denormalised engagement counters and eight merchandising flags. "
            "The counters (rating_average, view_count, purchase_count, wishlist_count…) "
            "are maintained by the application with F() expressions so that listing pages "
            "sort and filter without aggregating child tables on every request."
        ),
        rel=(
            "Child of Category, SubCategory and Brand (all PROTECT) and optionally "
            "Collection (SET NULL). Parent of ProductImage, ProductVariant, "
            "ProductAttribute, ProductSpecification, WishlistItem, CartItem, Review, "
            "RecentlyViewed and ProductAffinity. Referenced by OrderItem with SET NULL, "
            "because an order line must outlive the product it sold."
        ),
        apis=(
            "GET /products · /products/{slug} · /products/{slug}/quick-view · "
            "/products/{slug}/availability · /products/{slug}/related · "
            "/products/{slug}/similar · /products/search · /products/suggestions · "
            "/products/filters · /products/homepage · /products/featured · "
            "/products/trending · /products/new-arrivals · /products/best-sellers · "
            "/products/luxury · /products/flash-sale · /products/recommended · "
            "/products/editors-picks · /products/low-stock"
        ),
        pages=(
            "Homepage, Product Listing, Product Detail, Search Results, Quick View, "
            "Wishlist, Cart, Admin Catalogue"
        ),
    ),
    dict(
        table="products_producttag",
        module="PRODUCT CATALOG",
        section="Products",
        purpose="Free-form merchandising labels (Festive, Office Wear, Monsoon Ready).",
        rel="Bridged many-to-many to Product via products_product_tags.",
        apis="GET /product-tags · /product-tags/{slug} · /product-tags/{slug}/products",
        pages="Product Detail → tag chips, Tag Landing",
    ),
    dict(
        table="products_product_tags",
        module="PRODUCT CATALOG",
        section="Products",
        purpose="Bridge assigning merchandising tags to products.",
        rel="Bridge: products_product ↔ products_producttag.",
        apis="GET /product-tags/{slug}/products",
        pages="Tag Landing",
    ),
    dict(
        table="products_productimage",
        module="PRODUCT CATALOG",
        section="Products",
        purpose=(
            "Product gallery. At most one row per product may be primary, enforced by a "
            "partial unique index — the card image is a single-valued fact and must not "
            "depend on which row the query happens to return first."
        ),
        rel="Child of products_product (CASCADE).",
        apis="Embedded in /products/{slug} and every card payload.",
        pages="Product Detail gallery, Listing cards, Quick View, Cart line thumbnails",
    ),
    dict(
        table="products_productvariant",
        module="PRODUCT CATALOG",
        section="Products",
        purpose=(
            "The sellable unit: one row per colour and size. Holds the only authoritative "
            "stock figure in the schema. reserved_stock is held between checkout and "
            "payment capture and is constrained never to exceed stock, so the database "
            "itself refuses to oversell."
        ),
        rel=(
            "Child of products_product (CASCADE). Referenced by CartItem (CASCADE) and "
            "OrderItem (SET NULL). Unique on (product, colour, size)."
        ),
        apis="GET /products/{slug}/availability · embedded in /products/{slug}",
        pages="Product Detail size/colour picker, Cart, Checkout, Admin Inventory",
    ),
    dict(
        table="products_productattribute",
        module="PRODUCT CATALOG",
        section="Products",
        purpose="Arbitrary key/value facts for filtering. One value per key per product.",
        rel="Child of products_product (CASCADE). Unique on (product, key).",
        apis="Embedded in /products/{slug}; feeds /products/filters",
        pages="Product Detail → Attributes, Listing filter rail",
    ),
    dict(
        table="products_productspecification",
        module="PRODUCT CATALOG",
        section="Products",
        purpose="Ordered display-only specification rows (Fabric, Fit, Wash Care).",
        rel="Child of products_product (CASCADE). Unique on (product, label).",
        apis="Embedded in /products/{slug}",
        pages="Product Detail → Specifications table",
    ),

    # -- Wishlist -----------------------------------------------------------
    dict(
        table="wishlist_wishlist",
        module="WISHLIST & CART",
        section="Wishlist & Cart",
        purpose="One wishlist per signed-in customer. A singleton, enforced by a one-to-one key.",
        rel="One-to-one with users_user (CASCADE). Parent of wishlist_wishlistitem.",
        apis="GET /wishlist · /wishlist/count · /wishlist/slugs · POST /wishlist/clear",
        pages="Wishlist page, header heart badge",
    ),
    dict(
        table="wishlist_wishlistitem",
        module="WISHLIST & CART",
        section="Wishlist & Cart",
        purpose=(
            "One saved product. Deliberately holds no variant: a shopper hearts 'this "
            "dress', not 'this dress in navy, size M'. The size decision happens when the "
            "item moves to the cart."
        ),
        rel="Child of Wishlist and Product (both CASCADE). Unique on (wishlist, product).",
        apis="POST /wishlist/add · /wishlist/remove · /wishlist/toggle · /wishlist/move-to-cart",
        pages="Wishlist page, Product Detail heart, Listing card heart",
    ),

    # -- Cart ---------------------------------------------------------------
    dict(
        table="cart_cart",
        module="WISHLIST & CART",
        section="Wishlist & Cart",
        purpose=(
            "A shopping bag owned by either a signed-in customer or an anonymous session, "
            "never both and never neither — a CHECK constraint enforces the exclusive-or. "
            "Two partial unique indexes guarantee one active cart per user and one per "
            "guest session."
        ),
        rel=(
            "Optional child of users_user (CASCADE). Parent of cart_cartitem. "
            "Consumed and deactivated by checkout."
        ),
        apis=(
            "GET /cart · /cart/summary · /cart/count · POST /cart/add · /cart/update · "
            "/cart/remove · /cart/increase · /cart/decrease · /cart/clear · /cart/merge · "
            "/cart/apply-coupon · /cart/remove-coupon · /cart/checkout"
        ),
        pages="Cart page, Mini-cart drawer, header bag badge, Checkout",
    ),
    dict(
        table="cart_cartitem",
        module="WISHLIST & CART",
        section="Wishlist & Cart",
        purpose=(
            "One bag line. Money columns are recomputed on every mutation rather than at "
            "read time, so the cart total is a stored fact the checkout can trust. "
            "saved_for_later moves a line out of the payable set without deleting it. "
            "Quantity is bounded 1..10 by CHECK constraints."
        ),
        rel=(
            "Child of Cart, Product and ProductVariant (all CASCADE). "
            "Unique on (cart, variant)."
        ),
        apis="POST /cart/save-for-later · /cart/move-to-bag · /cart/move-to-wishlist",
        pages="Cart page, Saved For Later section, Mini-cart",
    ),

    # -- Orders -------------------------------------------------------------
    dict(
        table="orders_order",
        module="ORDERS & FULFILMENT",
        section="Orders",
        purpose=(
            "The order header and the financial record of a sale. Addresses are stored as "
            "JSONB snapshots, not foreign keys: the delivery address on a two-year-old "
            "order must remain what it was on the day, whatever the customer has since "
            "edited. Every money component is stored separately so finance can reconcile "
            "subtotal, discount, coupon, shipping, platform fee and tax against the total."
        ),
        rel=(
            "Child of users_user (PROTECT — a customer with orders cannot be hard-deleted). "
            "Parent of OrderItem, OrderStatusHistory, Shipment and Payment."
        ),
        apis=(
            "GET /orders · /orders/{order_number} · /orders/{order_number}/tracking · "
            "/orders/{order_number}/shipments · /orders/{order_number}/invoice · "
            "POST /checkout/place-order · /orders/{order_number}/cancel · "
            "/orders/{order_number}/reorder · /orders/{order_number}/request-return · "
            "/orders/{order_number}/update-status"
        ),
        pages="My Orders, Order Detail, Order Tracking, Order Confirmation, Admin Orders",
    ),
    dict(
        table="orders_orderitem",
        module="ORDERS & FULFILMENT",
        section="Orders",
        purpose=(
            "One purchased line, fully snapshotted. product_name, brand_name, sku, size, "
            "colour, image_url and all money columns are frozen copies — the product FK is "
            "SET NULL precisely so a delisted product cannot erase what was sold."
        ),
        rel=(
            "Child of orders_order (CASCADE). Optional references to Product and Variant "
            "(SET NULL). One-to-one target of reviews_review.order_item_id."
        ),
        apis="Embedded in /orders/{order_number}; drives /reviews/pending",
        pages="Order Detail line items, Invoice PDF, Write a Review",
    ),
    dict(
        table="orders_orderstatushistory",
        module="ORDERS & FULFILMENT",
        section="Orders",
        purpose=(
            "Append-only audit of every state transition. Rows are written once and never "
            "updated — a rewritable audit log answers nothing. This table, not the order's "
            "status column, is what the notification engine watches, which is what makes "
            "'your order shipped' fire exactly once."
        ),
        rel="Child of orders_order (CASCADE); optional actor reference to users_user (SET NULL).",
        apis="GET /orders/{order_number}/tracking",
        pages="Order Tracking timeline, Admin Order Detail",
    ),
    dict(
        table="orders_shipment",
        module="ORDERS & FULFILMENT",
        section="Orders",
        purpose=(
            "One dispatched parcel with courier and tracking reference. An order may have "
            "several — split shipments are normal in fashion retail."
        ),
        rel="Child of orders_order (CASCADE).",
        apis="GET /orders/{order_number}/shipments · /orders/{order_number}/tracking",
        pages="Order Tracking, Admin Fulfilment",
    ),

    # -- Coupons ------------------------------------------------------------
    dict(
        table="coupons_coupon",
        module="PROMOTIONS & COUPONS",
        section="Coupons",
        purpose=(
            "Discount code definition: flat, percentage or free shipping, with a minimum "
            "cart value, an optional cap, global and per-customer usage limits and a "
            "validity window. A CHECK constraint guarantees valid_until is after "
            "valid_from, so an unusable window cannot be saved."
        ),
        rel=(
            "Parent of coupons_couponusage. Optionally scoped to categories, brands or "
            "products through three bridge tables; an unscoped coupon applies store-wide."
        ),
        apis=(
            "GET /coupons · /coupons/{code} · POST /coupons/validate · /coupons/apply · "
            "/coupons/remove · /cart/apply-coupon"
        ),
        pages="Cart → Apply Coupon, Checkout, Offers page, Admin Coupons",
    ),
    dict(
        table="coupons_coupon_categories",
        module="PROMOTIONS & COUPONS",
        section="Coupons",
        purpose="Bridge restricting a coupon to specific categories.",
        rel="Bridge: coupons_coupon ↔ catalog_category.",
        apis="Evaluated inside POST /coupons/validate",
        pages="Cart coupon validation",
    ),
    dict(
        table="coupons_coupon_brands",
        module="PROMOTIONS & COUPONS",
        section="Coupons",
        purpose="Bridge restricting a coupon to specific brands.",
        rel="Bridge: coupons_coupon ↔ catalog_brand.",
        apis="Evaluated inside POST /coupons/validate",
        pages="Cart coupon validation",
    ),
    dict(
        table="coupons_coupon_products",
        module="PROMOTIONS & COUPONS",
        section="Coupons",
        purpose="Bridge restricting a coupon to specific products.",
        rel="Bridge: coupons_coupon ↔ products_product.",
        apis="Evaluated inside POST /coupons/validate",
        pages="Cart coupon validation",
    ),
    dict(
        table="coupons_couponusage",
        module="PROMOTIONS & COUPONS",
        section="Coupons",
        purpose=(
            "Redemption ledger — the enforcement point for per-customer limits. A partial "
            "unique index on (coupon, order) stops a retried checkout from double-counting "
            "a redemption. is_released reverses a redemption when an order is cancelled."
        ),
        rel="Child of Coupon and User (CASCADE) and optionally Order (CASCADE).",
        apis="GET /coupons/usages",
        pages="My Account → Coupons, Admin Coupon Report",
    ),

    # -- Payments -----------------------------------------------------------
    dict(
        table="payments_payment",
        module="PAYMENTS & REFUNDS",
        section="Payments",
        purpose=(
            "One payment intent against an order. Two partial unique indexes on "
            "(gateway, gateway_payment_id) and (gateway, gateway_order_id) make gateway "
            "identifiers idempotent, and a CHECK keeps refunded_amount within the captured "
            "amount so a payment can never be over-refunded."
        ),
        rel=(
            "Child of orders_order (PROTECT — a paid order cannot be deleted). Parent of "
            "PaymentAttempt, Refund and PaymentWebhookLog."
        ),
        apis=(
            "GET /payments · /payments/gateways · POST /payments/create · "
            "/payments/verify · /payments/webhook/{gateway}"
        ),
        pages="Checkout → Payment, Payment Status, Order Detail, Admin Payments",
    ),
    dict(
        table="payments_paymentattempt",
        module="PAYMENTS & REFUNDS",
        section="Payments",
        purpose=(
            "One try within a payment intent. A customer who fails on a card and then "
            "succeeds on UPI produces two attempts under one payment; without this table "
            "the failure would be invisible and the drop-off unmeasurable."
        ),
        rel="Child of payments_payment (CASCADE). Unique on (payment, attempt_number).",
        apis="Embedded in payment detail responses.",
        pages="Admin Payment Detail",
    ),
    dict(
        table="payments_refund",
        module="PAYMENTS & REFUNDS",
        section="Payments",
        purpose=(
            "Money returned, whole or partial. reason is stored because finance treats the "
            "categories differently: a cancellation is a sale that never happened, a return "
            "is a sale reversed, and goodwill is a marketing cost."
        ),
        rel="Child of payments_payment (PROTECT).",
        apis="GET /refunds · POST /payments/refund",
        pages="Order Detail → Refund status, Admin Refund Queue",
    ),
    dict(
        table="payments_paymentwebhooklog",
        module="PAYMENTS & REFUNDS",
        section="Payments",
        purpose=(
            "Every inbound gateway callback, verified or not. The unique constraint on "
            "(gateway, event_id) is the idempotency mechanism: a duplicate delivery raises "
            "a unique violation, which the application treats as 'already seen' rather "
            "than re-applying the event."
        ),
        rel="Optional child of payments_payment (SET NULL) — an unmatched event is still logged.",
        apis="POST /payments/webhook/{gateway}",
        pages="Admin → Webhook Log",
    ),

    # -- Reviews ------------------------------------------------------------
    dict(
        table="reviews_review",
        module="REVIEWS & RATINGS",
        section="Reviews",
        purpose=(
            "A verified-purchase review. The unique constraint on order_item_id is the "
            "rule the module exists to protect: one review per purchased line. It is "
            "enforced in the database because a double-tapped submit is two concurrent "
            "requests and a check-then-insert loses that race. Only status = 'approved' "
            "rows feed the product rating."
        ),
        rel=(
            "Child of Product and User (CASCADE), one-to-one with OrderItem (SET NULL), "
            "optional moderator reference to User (SET NULL). Parent of ReviewImage and "
            "HelpfulVote."
        ),
        apis=(
            "GET /products/{slug}/reviews · /reviews/summary · /reviews/gallery · "
            "/reviews/eligibility · GET|POST /reviews · PATCH|DELETE /reviews/{uuid} · "
            "GET /reviews/pending · POST /reviews/{uuid}/helpful · "
            "GET /admin/reviews · POST /admin/reviews/moderate"
        ),
        pages="Product Detail → Reviews, Write a Review, My Reviews, Admin Moderation",
    ),
    dict(
        table="reviews_reviewimage",
        module="REVIEWS & RATINGS",
        section="Reviews",
        purpose="Customer photographs attached to a review, with a generated thumbnail.",
        rel="Child of reviews_review (CASCADE). Capped at five per review by the service layer.",
        apis="GET /products/{slug}/reviews/gallery",
        pages="Product Detail → Customer Photos, Review cards",
    ),
    dict(
        table="reviews_helpfulvote",
        module="REVIEWS & RATINGS",
        section="Reviews",
        purpose=(
            "One upvote by one customer on one review. Stored as rows rather than only a "
            "counter because the UI asks 'have I voted on this?', which an integer cannot "
            "answer. Review.helpful_count exists alongside purely so the list can be "
            "ordered without a join."
        ),
        rel="Child of Review and User (CASCADE). Unique on (review, user).",
        apis="POST /reviews/{uuid}/helpful",
        pages="Product Detail → Was this helpful?",
    ),

    # -- Recommendations ----------------------------------------------------
    dict(
        table="recommendations_recentlyviewed",
        module="RECOMMENDATIONS & PERSONALISATION",
        section="Recommendations",
        purpose=(
            "Server-side browsing trail, owned by a user or a guest session under the same "
            "exclusive-or CHECK the cart uses. Capped at 30 rows per shopper by the "
            "application. Server-side rather than localStorage so the trail follows a "
            "shopper across devices and so 'customers also viewed' has anything to read."
        ),
        rel="Optional child of User (CASCADE); child of Product (CASCADE).",
        apis=(
            "GET|POST /recently-viewed · DELETE /recently-viewed/clear · "
            "/recently-viewed/item/{slug} · GET /products/recently-viewed"
        ),
        pages="Recently Viewed rail (Homepage, Product Detail, Listing)",
    ),
    dict(
        table="recommendations_productaffinity",
        module="RECOMMENDATIONS & PERSONALISATION",
        section="Recommendations",
        purpose=(
            "Materialised co-purchase graph behind 'frequently bought together'. Directed: "
            "A→B and B→A are separate rows, because a scarf sold with every coat is a "
            "strong suggestion on the coat and a weak one on the scarf. Rebuilt nightly by "
            "a Celery task; a self-referential edge is refused by CHECK."
        ),
        rel="Two references to products_product (CASCADE). Unique on (product, related_product).",
        apis=(
            "GET /recommendations/products/{slug}/frequently-bought-together · "
            "POST /admin/recommendations/rebuild-affinities · "
            "GET /admin/recommendations/diagnose/{slug}"
        ),
        pages="Product Detail → Frequently Bought Together, Admin Diagnostics",
    ),

    # -- Notifications ------------------------------------------------------
    dict(
        table="notifications_notification",
        module="NOTIFICATIONS",
        section="Notifications",
        purpose=(
            "One message to one person on one channel. Simultaneously the in-app inbox row "
            "and the delivery ledger for email, SMS and push — one table rather than two so "
            "'did we tell them?' has a single answer. The rendered context is kept as JSONB "
            "for support: what exactly did we send."
        ),
        rel="Child of users_user (CASCADE).",
        apis=(
            "GET /notifications · /notifications/unread-count · "
            "POST /notifications/{uuid}/read · /notifications/read-all · "
            "DELETE /notifications/{uuid} · GET /admin/notifications · "
            "/admin/notifications/stats · POST /admin/notifications/drain · retry"
        ),
        pages="Notification bell menu, Notifications page, Admin Delivery Ledger",
    ),
    dict(
        table="notifications_notificationpreference",
        module="NOTIFICATIONS",
        section="Notifications",
        purpose=(
            "Per-customer opt-outs, one row per account. Modelled as opt-out booleans "
            "rather than an opt-in subscription set so a newly added notification type "
            "reaches everyone by default. Marketing is the only category a customer may "
            "switch off wholesale; transactional mail is not a subscription."
        ),
        rel="One-to-one with users_user (CASCADE).",
        apis="GET|PATCH /notifications/preferences",
        pages="My Account → Notification Settings",
    ),
]
