"""Back matter: ERD, stored procedures, indexes, partitioning, normalisation."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity relationship diagram
# ---------------------------------------------------------------------------

ERD_CUSTOMER = """
users_user  (root of the customer domain)
|
+-- users_address                          1:N   one is_default per user (partial UQ)
+-- users_user_groups ----------> auth_group
+-- users_user_user_permissions --> auth_permission
+-- admin_user_role ------------> admin_role --> admin_role_permission --> admin_permission
|
+-- wishlist_wishlist                      1:1
|    \-- wishlist_wishlistitem             1:N  --> products_product
|
+-- cart_cart                              1:N   (one ACTIVE per user — partial UQ)
|    \-- cart_cartitem                     1:N  --> products_product
|                                                --> products_productvariant
|
+-- orders_order                           1:N   ON DELETE PROTECT
|    +-- orders_orderitem                  1:N  --> products_product      (SET NULL)
|    |      |                                   --> products_productvariant (SET NULL)
|    |      +-- reviews_review              1:1   UNIQUE(order_item)
|    |      \-- return_item                 1:N
|    +-- orders_orderstatushistory          1:N   append-only
|    +-- orders_shipment                    1:N  --> delivery_partner
|    |      \-- shipment_tracking_event     1:N   append-only
|    +-- payments_payment                   1:N   ON DELETE PROTECT
|    |      +-- payments_paymentattempt     1:N
|    |      +-- payments_refund             1:N   ON DELETE PROTECT
|    |      \-- payments_paymentwebhooklog  1:N   UNIQUE(gateway, event_id)
|    +-- coupons_couponusage                1:N  --> coupons_coupon
|    +-- return_request                     1:N  --> payments_refund
|    |      +-- return_item                 1:N
|    |      \-- exchange_request            1:N  --> products_productvariant
|    +-- loyalty_transaction                1:N
|    \-- gift_card_transaction              1:N
|
+-- reviews_review                          1:N
|    +-- reviews_reviewimage                1:N
|    \-- reviews_helpfulvote                1:N
+-- reviews_helpfulvote                     1:N   UNIQUE(review, user)
+-- product_question --> product_answer     1:N
|
+-- recommendations_recentlyviewed          1:N   user XOR session (CHECK)
+-- search_history                          1:N
+-- clickstream_event                       1:N   PARTITIONED BY RANGE(occurred_at)
+-- recommendation_history                  1:N
+-- fashion_preference                      1:1
|
+-- notifications_notification              1:N
+-- notifications_notificationpreference    1:1
+-- activity_log                            1:N   PARTITIONED BY RANGE(created_at)
|
+-- loyalty_account                         1:1
|    \-- loyalty_transaction                1:N
+-- gift_card       (purchased_by / redeemed_by)
+-- referral        (referrer / referred_user — self-referencing)
|
\-- support_ticket                          1:N
     \-- support_message                    1:N
"""

ERD_CATALOG = """
catalog_category  (root of the merchandising domain)
|
+-- catalog_subcategory                     1:N   UNIQUE(category, name)
|    \-- products_product                   1:N   ON DELETE PROTECT
|
+-- catalog_brand_categories --> catalog_brand        M:N
+-- catalog_collection_categories --> catalog_collection  M:N
+-- coupons_coupon_categories --> coupons_coupon      M:N
+-- homepage_banner                         1:N
\-- products_product                        1:N   ON DELETE PROTECT

products_product  (widest table: 57 columns)
|
+-- products_productimage                   1:N   partial UQ: one is_primary
+-- products_productvariant                 1:N   UNIQUE(product, colour, size)
|    +-- variant_image                      1:N
|    +-- inventory_stock                    1:N  --> warehouse
|    +-- inventory_transaction              1:N   append-only ledger
|    +-- stock_alert                        1:N
|    +-- cart_cartitem                      1:N
|    \-- orders_orderitem                   1:N   SET NULL
+-- products_productattribute               1:N   UNIQUE(product, key)
+-- products_productspecification           1:N   UNIQUE(product, label)
+-- products_product_tags --> products_producttag     M:N
+-- product_video                           1:N
+-- product_price_history                   1:N   append-only
+-- flash_sale_item --> flash_sale          M:N
+-- lookbook_item --> lookbook              M:N
+-- coupons_coupon_products --> coupons_coupon        M:N
+-- wishlist_wishlistitem                   1:N
+-- reviews_review                          1:N
+-- recommendations_recentlyviewed          1:N
+-- recommendations_productaffinity         1:N   self-join, directed, CHECK not self
+-- analytics_product_daily                 1:N
\-- product_question                        1:N

Lookup dimension (all referenced FROM products_product / _variant / users_address)
lkp_color · lkp_size · lkp_material · lkp_occasion · lkp_gender
lkp_age_group · lkp_season · lkp_pattern · lkp_fit · lkp_country
"""

ERD_NOTES = [
    "PROTECT edges (users_user → orders_order, orders_order → payments_payment, "
    "catalog_* → products_product) are deliberate: they make destructive deletes fail "
    "loudly instead of silently erasing financial history.",
    "SET NULL edges (orders_orderitem → products_product, "
    "payments_paymentwebhooklog → payments_payment) exist where the child must outlive "
    "the parent. An order line is a historical fact and keeps its own snapshot.",
    "CASCADE edges are used only where the child has no meaning without its parent — "
    "gallery images, cart lines, review photographs.",
    "Two tables (cart_cart, recommendations_recentlyviewed) carry an exclusive-or CHECK "
    "over (user_id, session_key). Every guest-capable feature follows this shape.",
]

# ---------------------------------------------------------------------------
# Stored procedures
# ---------------------------------------------------------------------------
# Business logic lives in the Django service layer today. These procedures are
# specified for the operations where a database round trip per step is the
# actual cost, or where the operation must be atomic under concurrency
# regardless of which application touches it.

PROCEDURES = [
    ("sp_place_order",
     "Convert an active cart into an order: snapshot lines, reserve stock, apply coupon, "
     "compute money, deactivate the cart.",
     "p_user_id BIGINT, p_cart_id BIGINT, p_shipping_address_id BIGINT, "
     "p_payment_method VARCHAR, p_coupon_code VARCHAR",
     "cart_cart, cart_cartitem, orders_order, orders_orderitem, orders_orderstatushistory, "
     "products_productvariant, inventory_stock, inventory_transaction, coupons_couponusage",
     "SERIALIZABLE. Locks each variant FOR UPDATE, verifies quantity_available, increments "
     "quantity_reserved, writes snapshot lines, records the coupon redemption and emits the "
     "initial status-history row. Rolls back entirely on any insufficient stock."),

    ("sp_reserve_stock",
     "Reserve units for a variant at checkout without oversell.",
     "p_variant_id BIGINT, p_warehouse_id BIGINT, p_quantity INTEGER, "
     "p_reference_id BIGINT, OUT p_success BOOLEAN",
     "inventory_stock, inventory_transaction",
     "Single conditional UPDATE … WHERE quantity_on_hand - quantity_reserved >= p_quantity. "
     "Zero rows updated means insufficient stock. Read-then-write would lose the race."),

    ("sp_commit_stock",
     "Convert a reservation into a permanent decrement on payment capture.",
     "p_order_id BIGINT",
     "orders_orderitem, inventory_stock, inventory_transaction, products_product",
     "Decrements quantity_on_hand and quantity_reserved together, writes a 'sale' ledger row "
     "per line and increments products_product.purchase_count."),

    ("sp_release_stock",
     "Return reserved units on cancellation, expiry or payment failure.",
     "p_order_id BIGINT, p_reason VARCHAR",
     "orders_orderitem, inventory_stock, inventory_transaction",
     "Decrements quantity_reserved only. Idempotent: a second call on an already-released "
     "order is a no-op, because an abandoned checkout can be swept twice."),

    ("sp_apply_coupon",
     "Validate a coupon against a cart and return the discount.",
     "p_cart_id BIGINT, p_user_id BIGINT, p_code VARCHAR, OUT p_discount NUMERIC, "
     "OUT p_reason VARCHAR",
     "coupons_coupon, coupons_couponusage, cart_cart, cart_cartitem, "
     "coupons_coupon_categories/_brands/_products",
     "Checks window, active flag, minimum cart value, global and per-user limits, "
     "first-order-only and category/brand/product scope. Returns the reason on failure so "
     "the UI can explain the refusal."),

    ("sp_process_refund",
     "Record a refund and adjust the payment atomically.",
     "p_payment_id BIGINT, p_amount NUMERIC, p_reason VARCHAR, p_processed_by BIGINT",
     "payments_payment, payments_refund, orders_order, return_request",
     "Locks the payment FOR UPDATE, verifies refunded_amount + p_amount <= amount, inserts "
     "the refund and moves the payment to refunded or partially_refunded."),

    ("sp_recompute_product_rating",
     "Recalculate a product's cached rating from APPROVED reviews only.",
     "p_product_id BIGINT",
     "reviews_review, products_product",
     "Approved-only is the whole point: averaging pending rows lets spam move the number "
     "shoppers see before a human has looked at it."),

    ("sp_rebuild_product_affinity",
     "Rebuild the co-purchase graph from order history.",
     "p_min_co_purchases INTEGER DEFAULT 2",
     "orders_order, orders_orderitem, recommendations_productaffinity",
     "Self-joins order lines within an order, counts directed pairs, computes confidence as "
     "co-purchases ÷ the left product's order count, and replaces the table in one "
     "transaction. Pairs below the threshold are dropped as coincidence."),

    ("sp_aggregate_daily_sales",
     "Populate the daily sales snapshot.",
     "p_snapshot_date DATE",
     "orders_order, payments_refund, analytics_daily_sales",
     "Idempotent upsert on (snapshot_date, currency), so a re-run after a late-settling "
     "refund corrects rather than duplicates."),

    ("sp_aggregate_product_daily",
     "Populate per-product daily performance including the view-to-purchase funnel.",
     "p_snapshot_date DATE",
     "clickstream_event, orders_orderitem, analytics_product_daily",
     "Reads one partition of clickstream_event, not the whole table."),

    ("sp_expire_coupons",
     "Deactivate coupons past their validity window.",
     "none",
     "coupons_coupon",
     "Single UPDATE. Expiry is already derivable at read time; this makes the admin list, "
     "the analytics counts and the storefront agree on one answer."),

    ("sp_expire_loyalty_points",
     "Expire points past their expiry date and adjust the balance.",
     "p_as_of DATE",
     "loyalty_transaction, loyalty_account",
     "Writes negative 'expire' ledger rows oldest-first and recomputes the balance from the "
     "ledger rather than trusting the cached figure."),

    ("sp_merge_guest_session",
     "Fold a guest cart, wishlist and browsing trail into an account on sign-in.",
     "p_user_id BIGINT, p_session_key VARCHAR",
     "cart_cart, cart_cartitem, recommendations_recentlyviewed, search_history",
     "Quantities are summed and clamped to the per-line limit. Trail rows the account "
     "already holds are dropped, since the unique constraint would reject the move."),

    ("sp_generate_order_number",
     "Allocate a collision-free human-readable order number.",
     "OUT p_order_number VARCHAR",
     "orders_order, a dedicated sequence",
     "Sequence-backed rather than timestamp-plus-random: two orders placed in the same "
     "millisecond currently collide on the unique index."),

    ("sp_low_stock_scan",
     "Raise stock alerts for variants at or below their reorder level.",
     "none",
     "inventory_stock, stock_alert, notifications_notification",
     "Inserts only where an unresolved alert does not already exist, so a persistently low "
     "SKU produces one alert rather than one per run."),

    ("sp_process_return",
     "Advance a return through QC and restock what is sellable.",
     "p_return_request_id BIGINT, p_qc_passed BOOLEAN, p_processed_by BIGINT",
     "return_request, return_item, inventory_stock, inventory_transaction, payments_refund",
     "On QC pass, restocks only lines flagged is_restockable and triggers the refund. On "
     "fail, records the reason and leaves stock untouched."),

    ("sp_calculate_customer_ltv",
     "Recompute lifetime value and tier for one customer.",
     "p_user_id BIGINT",
     "orders_order, payments_refund, loyalty_account",
     "Net of refunds. Gross LTV overstates the value of a serial returner, which is exactly "
     "the customer a tier should not promote."),

    ("sp_purge_expired_sessions",
     "Retention sweep across guest-scoped and behavioural tables.",
     "p_retention_days INTEGER DEFAULT 90",
     "cart_cart, recommendations_recentlyviewed, search_history, clickstream_event",
     "Drops whole partitions where the table is partitioned rather than issuing DELETEs — "
     "a partition drop is a metadata operation and produces no bloat."),

    ("sp_audit_log_write",
     "Generic trigger function capturing before/after images.",
     "TG_OP, TG_TABLE_NAME, OLD, NEW (trigger context)",
     "audit_log",
     "Attached as an AFTER trigger on sensitive tables. Writes only the columns that "
     "actually changed, so an unrelated touch does not produce a diff nobody can read."),

    ("sp_dashboard_summary",
     "Return every admin dashboard figure in one round trip.",
     "p_days INTEGER DEFAULT 30",
     "analytics_daily_sales, analytics_customer_daily, analytics_product_daily "
     "(all read-only)",
     "Reads the aggregate tables, never the transactional ones. Replaces roughly fifteen "
     "separate aggregate queries."),
]

# ---------------------------------------------------------------------------
# Index recommendations
# ---------------------------------------------------------------------------

INDEX_NOTES = [
    ("Existing coverage", "",
     "The shipped schema already carries 47 named composite indexes. They are documented "
     "per table earlier in this document and should not be duplicated."),
    ("products_product", "GIN (to_tsvector('english', name || ' ' || short_description))",
     "Product search currently uses chained ILIKE, which cannot use a B-tree. A GIN "
     "full-text index is the single largest available query win."),
    ("products_product", "GIN (name gin_trgm_ops) — pg_trgm",
     "Powers typo-tolerant autocomplete on /products/suggestions."),
    ("products_product", "BRIN (created_at)",
     "Append-mostly and correlated with physical order; a BRIN index is a fraction of the "
     "size of the B-tree for the same range scans."),
    ("orders_order", "(user_id, status, created_at DESC)",
     "Serves 'my orders filtered by status' without a sort."),
    ("orders_order", "Partial: (created_at DESC) WHERE status = 'pending'",
     "The abandoned-order sweep reads a tiny slice of a large table."),
    ("orders_orderitem", "(product_id, order_id)",
     "Analytics joins from product to order lines; currently only (order_id) is indexed."),
    ("cart_cart", "Partial: (updated_at) WHERE is_active",
     "Abandoned-cart job. Inactive carts dominate the table over time."),
    ("inventory_stock", "(warehouse_id, variant_id) INCLUDE (quantity_available)",
     "Covering index: allocation resolves without a heap fetch."),
    ("inventory_stock", "Partial: (variant_id) WHERE quantity_available <= reorder_level",
     "Low-stock scan touches only the rows that qualify."),
    ("clickstream_event", "(user_id, occurred_at DESC) per partition",
     "Local indexes on partitions; a global index would defeat partition pruning."),
    ("clickstream_event", "GIN (metadata jsonb_path_ops)",
     "Ad-hoc event property queries."),
    ("search_history", "GIN (normalised_query gin_trgm_ops)",
     "Fuzzy grouping of query variants for the trending job."),
    ("audit_log", "(entity_type, entity_id, created_at DESC)",
     "The only access pattern: the history of one record."),
    ("notifications_notification", "Partial: (user_id, created_at DESC) WHERE NOT is_read",
     "The unread badge is the hottest read in the module and touches a small subset."),
    ("reviews_review", "Partial: (created_at) WHERE status = 'pending'",
     "Moderation queue, oldest first."),
    ("recommendations_productaffinity", "(product_id, score DESC) INCLUDE (related_product_id)",
     "Covering index for the frequently-bought-together rail."),
    ("Extensions required", "pg_trgm, btree_gin, pg_stat_statements, pgcrypto",
     "pgcrypto supplies gen_random_uuid(); pg_stat_statements is how the slow-query list is "
     "produced at all."),
]

# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------

PARTITIONS = [
    ("clickstream_event", "RANGE (occurred_at)", "Daily",
     "90 days hot, then to cold storage",
     "Highest-volume table by an order of magnitude. Daily partitions keep each index small "
     "enough to stay in cache, and retention becomes DROP PARTITION — a metadata operation "
     "that produces no bloat and needs no VACUUM."),
    ("audit_log", "RANGE (created_at)", "Monthly", "24 months (compliance)",
     "Write-heavy, read-rarely, and legally required to be retained. Monthly partitions make "
     "the retention boundary a single DROP."),
    ("activity_log", "RANGE (created_at)", "Monthly", "12 months",
     "Same profile as audit_log at lower volume."),
    ("notifications_notification", "RANGE (created_at)", "Monthly", "6 months",
     "The retention job currently issues a bulk DELETE, which leaves dead tuples behind on "
     "a table the queue worker reads every two minutes."),
    ("inventory_transaction", "RANGE (created_at)", "Monthly", "Indefinite (financial)",
     "Append-only ledger. Old partitions are read only during audits and can be moved to "
     "slower storage."),
    ("search_history", "RANGE (created_at)", "Monthly", "12 months",
     "High volume, aggregated nightly and rarely read raw afterwards."),
    ("recommendation_history", "RANGE (served_at)", "Monthly", "6 months",
     "Written on every rail impression; useful only while a model version is live."),
    ("orders_order", "RANGE (created_at) — deferred", "Yearly", "Indefinite",
     "Do NOT partition at launch. Partitioning a table this heavily foreign-keyed forces "
     "every child to carry the partition key. Revisit past roughly five million orders."),
    ("analytics_product_daily", "RANGE (snapshot_date)", "Monthly", "36 months",
     "Grows at products × days. Partitioning keeps dashboard range scans bounded."),
]

# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

PERFORMANCE = [
    ("Full-text search",
     "Product search chains ILIKE across name, description, brand and category. This cannot "
     "use an index and degrades linearly with catalogue size.",
     "Add a generated tsvector column with a GIN index and rank with ts_rank_cd. Keep "
     "pg_trgm for typo tolerance on autocomplete."),
    ("Denormalised counters",
     "Six counters on products_product (view_count, purchase_count, wishlist_count, "
     "rating_average, rating_count, review_count) are updated with F() expressions. Correct, "
     "but view_count writes contend on hot rows.",
     "Batch view counts through Redis and flush periodically. The number is a merchandising "
     "signal, not an invoice — a few seconds of staleness costs nothing."),
    ("Analytics on live tables",
     "Every dashboard figure aggregates orders_order and orders_orderitem directly. Fine at "
     "current volume; it will not hold past ~100k orders.",
     "Introduce the three analytics_* snapshot tables and point the dashboard at them. The "
     "warm_analytics job already exists and becomes the writer."),
    ("N+1 prevention",
     "The application already uses select_related and prefetch_related consistently "
     "(with_card_data, with_detail, with_recipient), and vote state is annotated with one "
     "Exists subquery per page.",
     "Preserve this on new endpoints. Add a CI assertion on query counts for the listing and "
     "detail endpoints so a regression fails the build rather than production."),
    ("Connection pooling",
     "CONN_MAX_AGE is 60s with health checks. Each Gunicorn worker holds its own connection; "
     "workers × replicas can exhaust max_connections.",
     "Put PgBouncer in transaction mode in front of the database. Note that transaction "
     "pooling forbids session-level features — the application uses none."),
    ("Covering indexes",
     "Hot lookups fetch the heap for one or two extra columns.",
     "Use INCLUDE on the frequently-bought-together and inventory allocation indexes to make "
     "them index-only scans."),
    ("JSONB columns",
     "orders_order.shipping_address, payments_payment.raw_response and "
     "notifications_notification.context are JSONB.",
     "Snapshots are correct as JSONB and should not be normalised. Add GIN indexes only "
     "where a JSONB column is actually filtered — today none are."),
    ("Bulk operations",
     "The affinity rebuild already uses bulk_create with a batch size and streams source rows "
     "with an iterator.",
     "Apply the same pattern to the analytics aggregation jobs. Use COPY for any import "
     "above roughly ten thousand rows."),
    ("Read replicas",
     "Analytics and reports compete with checkout for the same database.",
     "Route /admin/analytics/* and /admin/reports/* to a read replica. They tolerate replica "
     "lag; checkout does not."),
    ("Partial indexes",
     "Several hot queries touch a small subset of a large table — unread notifications, "
     "pending reviews, active carts, low stock.",
     "Partial indexes on those predicates are a fraction of the size and stay cached."),
    ("VACUUM tuning",
     "High-churn tables (cart_cartitem, notifications_notification, inventory_stock) "
     "accumulate dead tuples faster than the default autovacuum threshold reacts.",
     "Lower autovacuum_vacuum_scale_factor to 0.02 on those tables specifically."),
]

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

NORMALISATION = [
    ("1NF — Atomic values, no repeating groups", "SATISFIED",
     "Every column holds a single value. Repeating groups are child tables: product images, "
     "variants, attributes, specifications, order lines and review photographs each have "
     "their own table rather than numbered columns.\n\n"
     "Three JSONB columns are deliberate exceptions and are not 1NF violations: "
     "orders_order.shipping_address and billing_address are immutable point-in-time "
     "snapshots, never queried by sub-field; payments_payment.raw_response and "
     "payments_paymentwebhooklog.payload are opaque third-party documents retained for "
     "dispute evidence; notifications_notification.context is a rendered audit copy. "
     "Normalising any of them would create a second version of a fact that must never "
     "change."),

    ("2NF — No partial dependency on a composite key", "SATISFIED",
     "Every table uses a single-column surrogate BIGSERIAL primary key, so no non-key "
     "attribute can depend on part of a key. Composite uniqueness — (product, colour, size), "
     "(cart, variant), (coupon, order), (gateway, event_id), (review, user) — is expressed "
     "as UNIQUE constraints alongside the surrogate key rather than as the key itself.\n\n"
     "Bridge tables (products_product_tags, coupons_coupon_brands, admin_role_permission) "
     "carry only their two foreign keys and, where meaningful, a grant timestamp — no "
     "attribute that depends on one side alone."),

    ("3NF — No transitive dependency", "SATISFIED WITH DOCUMENTED DENORMALISATION",
     "The normalised core is in 3NF. Six categories of denormalisation are deliberate, and "
     "each is maintained by a named service function with a recount routine:\n\n"
     "1. Engagement counters on products_product (rating_average, rating_count, "
     "review_count, wishlist_count, view_count, purchase_count) are derivable from child "
     "tables. Storing them turns every listing sort into an index scan instead of a "
     "six-way aggregate join. Rebuilt by sp_recompute_product_rating.\n\n"
     "2. Money columns on cart_cartitem and orders_orderitem are computable from price and "
     "quantity. Stored so the total a customer agreed to is a fact, not a recomputation "
     "that could disagree after a price change.\n\n"
     "3. Order line snapshots (product_name, brand_name, sku, size, colour, image_url) "
     "duplicate the product tables. This is not redundancy — it is temporal correctness. "
     "The product FK is SET NULL precisely so a delisted product cannot rewrite history.\n\n"
     "4. reviews_review.helpful_count duplicates a COUNT over reviews_helpfulvote. Stored "
     "so the review list can order by helpfulness without a join; rebuilt by recount_helpful.\n\n"
     "5. products_productvariant.stock becomes a roll-up of inventory_stock once "
     "warehousing lands. The per-warehouse rows are authoritative.\n\n"
     "6. The analytics_* tables are wholly derived and rebuildable from source at any time. "
     "They are a cache with a schema, never a system of record.\n\n"
     "Enum-backed CharFields (gender, material, occasion, season, fit, pattern, size) are a "
     "3NF weakness in the shipped schema: the label is functionally dependent on the code "
     "but no relation holds it. The ten proposed lkp_* tables resolve this."),

    ("BCNF — Every determinant is a candidate key", "SATISFIED",
     "No table has overlapping candidate keys with a non-trivial functional dependency "
     "between them. The composite unique constraints are all over foreign keys and "
     "discriminators, none of which determine another attribute in the same table."),

    ("4NF — No multi-valued dependency", "SATISFIED",
     "Independent many-to-many relationships are separate bridge tables. A coupon's category "
     "scope, brand scope and product scope live in three tables rather than one, so the "
     "combinations are not multiplied."),
]
