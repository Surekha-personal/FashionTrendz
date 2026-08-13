"""Tables required by the module brief that the shipped backend does not yet have.

Every table here is marked PROPOSED in the document. The distinction matters
more than anything else in this specification: the database team must know
which objects they are describing and which they are building.

Column tuple order is (name, type, nullable, default, key, references, notes),
matching the grid headers used throughout the document.
"""

from __future__ import annotations

# Audit columns carried by every proposed table, matching the BaseModel
# convention already used by the 41 implemented tables.
AUDIT = [
    ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "UTC"),
    ("updated_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "UTC; touched on write"),
]
UUIDC = ("uuid", "UUID", "NOT NULL", "gen_random_uuid()", "UQ", "", "Public-safe identifier")


def T(table, module, section, purpose, cols, rel, apis, pages, keys=None):
    """Return one proposed-table entry."""
    return dict(table=table, module=module, section=section, purpose=purpose,
                cols=cols, rel=rel, apis=apis, pages=pages, keys=keys or [])


LOOKUP = "LOOKUP & REFERENCE TABLES"
INV = "INVENTORY & WAREHOUSING"
PRICING = "PRICING, OFFERS & PROMOTIONS"
SHIP = "SHIPPING, RETURNS & EXCHANGES"
CONTENT = "CONTENT, MERCHANDISING & CMS"
ENGAGE = "CUSTOMER ENGAGEMENT & LOYALTY"
BEHAV = "SEARCH, BEHAVIOUR & AI PERSONALISATION"
ADMIN = "ADMINISTRATION, RBAC & AUDIT"
SUPPORT = "SUPPORT & COMMUNICATION"
ANALYT = "ANALYTICS AGGREGATION"

_LKP_TAIL = [
    ("display_order", "SMALLINT", "NOT NULL", "0", "", "", "Sort position in filter rails"),
    ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", "Soft disable"),
] + AUDIT


def lookup(name, extra=None, note=""):
    """Return a standard code/label lookup table definition."""
    return [
        ("id", "SMALLSERIAL", "NOT NULL", "identity", "PK", "", ""),
        ("code", "VARCHAR(32)", "NOT NULL", "", "UQ", "", note or "Stable machine key"),
        ("label", "VARCHAR(80)", "NOT NULL", "", "", "", "Display name"),
    ] + (extra or []) + _LKP_TAIL


PROPOSED: list[dict] = [

    # =====================================================================
    # LOOKUP TABLES
    # =====================================================================
    T("lkp_color", LOOKUP, "Lookups",
      "Colour master. Today colour is a free-text VARCHAR(40) on products_productvariant "
      "with a separate hex column, which permits 'Navy', 'navy' and 'Navy Blue' to coexist "
      "and fragments the colour filter. Normalising it is the single highest-value "
      "lookup change in this document.",
      lookup("colour", [
          ("hex_code", "CHAR(7)", "NOT NULL", "", "", "", "#RRGGBB swatch"),
          ("colour_family", "VARCHAR(32)", "NOT NULL", "", "", "", "Blues, Neutrals — filter grouping"),
      ]),
      "Referenced by products_productvariant.color_id and the proposed variant_image table. "
      "Migration path: backfill from DISTINCT lower(trim(color)), then add the FK.",
      "GET /products/filters · embedded in /products/{slug}",
      "Listing colour filter, Product Detail swatches"),

    T("lkp_size", LOOKUP, "Lookups",
      "Size master with a sort key. Sizes are currently an enum on the variant, which "
      "cannot express that UK8 sits between XS and S, so size filters sort alphabetically "
      "and read as nonsense.",
      lookup("size", [
          ("size_system", "VARCHAR(16)", "NOT NULL", "'ALPHA'", "", "", "ALPHA | UK | EU | US | NUMERIC"),
          ("sort_key", "SMALLINT", "NOT NULL", "0", "", "", "Canonical ordering across systems"),
          ("category_id", "BIGINT", "NULL", "", "FK", "catalog_category", "Scope: footwear vs apparel"),
      ]),
      "Referenced by products_productvariant.size_id. Optional category scope so shoe sizes "
      "do not appear on a dress filter.",
      "GET /products/filters",
      "Listing size filter, Product Detail size picker, Size Guide"),

    T("lkp_material", LOOKUP, "Lookups",
      "Fabric master, replacing the material enum on products_product.",
      lookup("material", [
          ("care_note", "VARCHAR(255)", "NOT NULL", "''", "", "", "Default wash-care copy"),
          ("is_sustainable", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Drives the sustainability badge"),
      ]),
      "Referenced by products_product.material_id.",
      "GET /products/filters", "Listing fabric filter, Product Detail"),

    T("lkp_occasion", LOOKUP, "Lookups",
      "Occasion master (Casual, Formal, Wedding, Festive), replacing the product enum.",
      lookup("occasion"),
      "Referenced by products_product.occasion_id and by lookbook.",
      "GET /products/filters", "Occasion filter, Shop by Occasion"),

    T("lkp_gender", LOOKUP, "Lookups",
      "Gender/audience master, shared by products and customer profiles.",
      lookup("gender"),
      "Referenced by products_product.gender_id and users_user.gender_id.",
      "GET /products/filters", "Gender nav, Profile form"),

    T("lkp_age_group", LOOKUP, "Lookups",
      "Age banding (Adult, Teen, Kids 8–12, Infant). Absent from the current schema "
      "entirely — kidswear is only inferable from the category name.",
      lookup("age_group", [
          ("min_age_years", "SMALLINT", "NULL", "", "", "", "Inclusive lower bound"),
          ("max_age_years", "SMALLINT", "NULL", "", "", "", "Inclusive upper bound"),
      ]),
      "Referenced by products_product.age_group_id.",
      "GET /products/filters", "Kids landing, Age filter"),

    T("lkp_season", LOOKUP, "Lookups", "Season master, replacing the season enum.",
      lookup("season"), "Referenced by products_product.season_id and seasonal collections.",
      "GET /products/filters", "Seasonal campaign pages"),

    T("lkp_pattern", LOOKUP, "Lookups", "Pattern master (Solid, Floral, Striped, Checked).",
      lookup("pattern"), "Referenced by products_product.pattern_id.",
      "GET /products/filters", "Pattern filter"),

    T("lkp_fit", LOOKUP, "Lookups", "Fit master (Slim, Regular, Relaxed, Oversized, Bodycon).",
      lookup("fit"), "Referenced by products_product.fit_id.",
      "GET /products/filters", "Fit filter, Product Detail"),

    T("lkp_country", LOOKUP, "Lookups",
      "ISO country master for addresses, brand origin and product country of origin — all "
      "three are free-text VARCHAR(100) today.",
      [
          ("id", "SMALLSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("iso2", "CHAR(2)", "NOT NULL", "", "UQ", "", "ISO 3166-1 alpha-2"),
          ("iso3", "CHAR(3)", "NOT NULL", "", "UQ", "", "ISO 3166-1 alpha-3"),
          ("name", "VARCHAR(100)", "NOT NULL", "", "", "", ""),
          ("phone_code", "VARCHAR(8)", "NOT NULL", "''", "", "", "E.164 prefix"),
          ("currency_code", "CHAR(3)", "NOT NULL", "'INR'", "", "", "ISO 4217"),
          ("is_shipping_supported", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Gates checkout"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Referenced by users_address.country_id, catalog_brand.country_id and "
      "products_product.country_of_origin_id.",
      "GET /addresses (validation)", "Checkout country picker, Address form"),

    # =====================================================================
    # INVENTORY & WAREHOUSING
    # =====================================================================
    T("warehouse", INV, "Inventory",
      "Physical fulfilment locations. The current schema holds a single stock integer per "
      "variant with no notion of where that stock sits, which makes multi-location "
      "fulfilment, transfers and location-aware delivery estimates impossible.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("code", "VARCHAR(24)", "NOT NULL", "", "UQ", "", "e.g. BLR-01"),
          ("name", "VARCHAR(120)", "NOT NULL", "", "", "", ""),
          ("address_line_1", "VARCHAR(255)", "NOT NULL", "", "", "", ""),
          ("address_line_2", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("city", "VARCHAR(100)", "NOT NULL", "", "", "", ""),
          ("state", "VARCHAR(100)", "NOT NULL", "", "", "", ""),
          ("country_id", "SMALLINT", "NOT NULL", "", "FK", "lkp_country", "ON DELETE RESTRICT"),
          ("postal_code", "VARCHAR(16)", "NOT NULL", "", "", "", ""),
          ("latitude", "NUMERIC(9,6)", "NULL", "", "", "", "Nearest-warehouse routing"),
          ("longitude", "NUMERIC(9,6)", "NULL", "", "", "", ""),
          ("priority", "SMALLINT", "NOT NULL", "0", "", "", "Allocation preference; higher wins"),
          ("is_pickup_enabled", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Click-and-collect"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Parent of inventory_stock, inventory_transaction and stock_alert.",
      "GET /admin/warehouses (new) · consumed by allocation during checkout",
      "Admin → Warehouses, Checkout delivery estimate"),

    T("inventory_stock", INV, "Inventory",
      "Stock on hand per variant per warehouse. This table takes over from "
      "products_productvariant.stock, which becomes a maintained roll-up. quantity_available "
      "is a generated column so no query can compute availability incorrectly.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("variant_id", "BIGINT", "NOT NULL", "", "FK", "products_productvariant", "ON DELETE CASCADE"),
          ("warehouse_id", "BIGINT", "NOT NULL", "", "FK", "warehouse", "ON DELETE RESTRICT"),
          ("quantity_on_hand", "INTEGER", "NOT NULL", "0", "", "", "CHECK >= 0"),
          ("quantity_reserved", "INTEGER", "NOT NULL", "0", "", "", "CHECK >= 0 AND <= on_hand"),
          ("quantity_available", "INTEGER", "NOT NULL", "GENERATED", "", "",
           "GENERATED ALWAYS AS (quantity_on_hand - quantity_reserved) STORED"),
          ("reorder_level", "INTEGER", "NOT NULL", "5", "", "", "Triggers stock_alert"),
          ("reorder_quantity", "INTEGER", "NOT NULL", "0", "", "", "Suggested purchase order size"),
          ("bin_location", "VARCHAR(32)", "NOT NULL", "''", "", "", "Aisle/shelf"),
          ("last_counted_at", "TIMESTAMPTZ", "NULL", "", "", "", "Last physical stocktake"),
      ] + AUDIT,
      "Composite UNIQUE (variant_id, warehouse_id). Roll-up of quantity_available across "
      "warehouses maintains products_productvariant.stock.",
      "GET /admin/analytics/inventory · /admin/dashboard/low-stock · /products/{slug}/availability",
      "Admin Inventory, Product Detail availability, Low Stock report"),

    T("inventory_transaction", INV, "Inventory",
      "Immutable ledger of every stock movement. The current schema mutates a counter with "
      "no history, so 'where did those forty units go?' is unanswerable. Append-only: "
      "corrections are new rows, never updates.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("variant_id", "BIGINT", "NOT NULL", "", "FK", "products_productvariant", "ON DELETE RESTRICT"),
          ("warehouse_id", "BIGINT", "NOT NULL", "", "FK", "warehouse", "ON DELETE RESTRICT"),
          ("transaction_type", "VARCHAR(24)", "NOT NULL", "", "", "",
           "purchase | sale | return | reservation | release | adjustment | transfer_in | transfer_out | damage"),
          ("quantity_delta", "INTEGER", "NOT NULL", "", "", "", "Signed; CHECK <> 0"),
          ("balance_after", "INTEGER", "NOT NULL", "", "", "", "Running balance for reconciliation"),
          ("reference_type", "VARCHAR(32)", "NOT NULL", "''", "", "", "order | return | manual | po"),
          ("reference_id", "BIGINT", "NULL", "", "", "", "Polymorphic source id"),
          ("order_item_id", "BIGINT", "NULL", "", "FK", "orders_orderitem", "ON DELETE SET NULL"),
          ("performed_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("notes", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "Partition key"),
      ],
      "Child of ProductVariant, Warehouse, OrderItem and User. Never updated or deleted.",
      "GET /admin/analytics/inventory · POST /admin/inventory/adjust (new)",
      "Admin Inventory Ledger, Stock Audit report"),

    T("stock_alert", INV, "Inventory",
      "Open low-stock and out-of-stock signals, plus customer back-in-stock subscriptions. "
      "Today low stock is recomputed on every dashboard load with no record of whether "
      "anyone acted on it.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("variant_id", "BIGINT", "NOT NULL", "", "FK", "products_productvariant", "ON DELETE CASCADE"),
          ("warehouse_id", "BIGINT", "NULL", "", "FK", "warehouse", "ON DELETE CASCADE"),
          ("alert_type", "VARCHAR(24)", "NOT NULL", "", "", "", "low_stock | out_of_stock | back_in_stock_request"),
          ("threshold", "INTEGER", "NULL", "", "", "", "Level that fired the alert"),
          ("quantity_at_alert", "INTEGER", "NULL", "", "", "", ""),
          ("subscriber_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE CASCADE; back-in-stock only"),
          ("is_resolved", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("resolved_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("notified_at", "TIMESTAMPTZ", "NULL", "", "", "", "When the customer was told"),
      ] + AUDIT,
      "Child of ProductVariant, Warehouse and User. Partial unique on "
      "(variant_id, subscriber_id) WHERE is_resolved = FALSE stops duplicate subscriptions.",
      "POST /products/{slug}/notify-me (new) · GET /admin/dashboard/low-stock",
      "Product Detail → Notify Me, Admin Low Stock queue"),

    # =====================================================================
    # PRICING, OFFERS & PROMOTIONS
    # =====================================================================
    T("product_price_history", PRICING, "Pricing",
      "Append-only price change log. Nothing in the current schema records what a product "
      "used to cost, so a 'was INR 2,999' claim cannot be substantiated — which is a legal "
      "exposure under Indian consumer-protection rules on reference pricing.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("product_id", "BIGINT", "NOT NULL", "", "FK", "products_product", "ON DELETE CASCADE"),
          ("variant_id", "BIGINT", "NULL", "", "FK", "products_productvariant", "ON DELETE CASCADE"),
          ("old_mrp", "NUMERIC(12,2)", "NULL", "", "", "", ""),
          ("new_mrp", "NUMERIC(12,2)", "NOT NULL", "", "", "", ""),
          ("old_selling_price", "NUMERIC(12,2)", "NULL", "", "", "", ""),
          ("new_selling_price", "NUMERIC(12,2)", "NOT NULL", "", "", "", ""),
          ("change_reason", "VARCHAR(32)", "NOT NULL", "'manual'", "", "", "manual | flash_sale | rule | markdown"),
          ("changed_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("effective_from", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "Partition key"),
      ],
      "Child of Product and Variant. Written by a trigger or the pricing service on any "
      "price update.",
      "GET /admin/products/{slug}/price-history (new)",
      "Admin Product Detail → Price History, Price-drop notifications"),

    T("discount_rule", PRICING, "Pricing",
      "Automatic discounts that need no coupon code — 'Buy 2 Get 1', 'Flat 30% on Denim', "
      "tiered cart discounts. Currently expressible only as a per-product percentage, so "
      "every campaign is a bulk product edit that has to be undone by hand.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("name", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("rule_type", "VARCHAR(24)", "NOT NULL", "", "", "",
           "percentage | flat | bogo | tiered | bundle | free_shipping"),
          ("scope", "VARCHAR(16)", "NOT NULL", "'product'", "", "", "product | category | brand | cart"),
          ("value", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", "CHECK >= 0"),
          ("max_discount", "NUMERIC(12,2)", "NULL", "", "", "", "Cap for percentage rules"),
          ("min_quantity", "SMALLINT", "NOT NULL", "1", "", "", "BOGO / tier trigger"),
          ("min_cart_value", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", ""),
          ("get_quantity", "SMALLINT", "NOT NULL", "0", "", "", "BOGO: units given free"),
          ("priority", "SMALLINT", "NOT NULL", "0", "", "", "Resolution order when rules overlap"),
          ("is_stackable", "BOOLEAN", "NOT NULL", "FALSE", "", "", "May combine with a coupon"),
          ("valid_from", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("valid_until", "TIMESTAMPTZ", "NULL", "", "", "", "CHECK > valid_from"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Scoped through discount_rule_product / _category / _brand bridges (same shape as the "
      "coupon bridges). Evaluated by the cart pricing service before coupons.",
      "GET /offers (new) · evaluated inside GET /cart/summary",
      "Cart price breakdown, Offers page, Product Detail offer strip"),

    T("offer", PRICING, "Pricing",
      "Customer-facing promotional banner copy for a discount rule — the marketing surface, "
      "separate from the pricing mechanics so campaign copy can change without touching "
      "money logic.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("slug", "VARCHAR(255)", "NOT NULL", "", "UQ", "", ""),
          ("title", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("subtitle", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("description", "TEXT", "NOT NULL", "''", "", "", ""),
          ("banner_image", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("badge_text", "VARCHAR(32)", "NOT NULL", "''", "", "", "e.g. 30% OFF"),
          ("discount_rule_id", "BIGINT", "NULL", "", "FK", "discount_rule", "ON DELETE SET NULL"),
          ("coupon_id", "BIGINT", "NULL", "", "FK", "coupons_coupon", "ON DELETE SET NULL"),
          ("target_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
          ("starts_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("ends_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
      ] + AUDIT,
      "Optionally linked to a discount_rule or a coupon.",
      "GET /offers · /offers/{slug} (new)",
      "Offers page, Homepage offer strip, Product Detail offer box"),

    T("flash_sale", PRICING, "Pricing",
      "Time-boxed sale event with a countdown. The current /products/flash-sale endpoint "
      "just filters products discounted 40% or more — there is no event, no start and end "
      "time, and no per-item sale price or unit cap.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("slug", "VARCHAR(255)", "NOT NULL", "", "UQ", "", ""),
          ("title", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("banner_image", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("starts_at", "TIMESTAMPTZ", "NOT NULL", "", "", "", "Drives the countdown timer"),
          ("ends_at", "TIMESTAMPTZ", "NOT NULL", "", "", "", "CHECK > starts_at"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
          ("total_stock_cap", "INTEGER", "NULL", "", "", "", "Units across the whole event"),
          ("units_sold", "INTEGER", "NOT NULL", "0", "", "", "Denormalised progress bar counter"),
      ] + AUDIT,
      "Parent of flash_sale_item. EXCLUDE constraint on overlapping active windows prevents "
      "two live flash sales claiming the same product.",
      "GET /products/flash-sale · /flash-sales/{slug} (new)",
      "Homepage Flash Sale rail with countdown, Flash Sale landing"),

    T("flash_sale_item", PRICING, "Pricing",
      "One product in a flash sale at an event-specific price and unit cap.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("flash_sale_id", "BIGINT", "NOT NULL", "", "FK", "flash_sale", "ON DELETE CASCADE"),
          ("product_id", "BIGINT", "NOT NULL", "", "FK", "products_product", "ON DELETE CASCADE"),
          ("variant_id", "BIGINT", "NULL", "", "FK", "products_productvariant", "ON DELETE CASCADE"),
          ("sale_price", "NUMERIC(12,2)", "NOT NULL", "", "", "", "CHECK > 0"),
          ("unit_cap", "INTEGER", "NULL", "", "", "", "Units released for this item"),
          ("units_sold", "INTEGER", "NOT NULL", "0", "", "", "CHECK <= unit_cap"),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
      ] + AUDIT,
      "Composite UNIQUE (flash_sale_id, product_id, variant_id).",
      "GET /products/flash-sale",
      "Flash Sale rail and landing page"),

    # =====================================================================
    # SHIPPING, RETURNS & EXCHANGES
    # =====================================================================
    T("delivery_partner", SHIP, "Shipping",
      "Courier master. orders_shipment.courier_name is free text today, so the same courier "
      "appears under three spellings and per-courier performance cannot be measured.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("code", "VARCHAR(24)", "NOT NULL", "", "UQ", "", "bluedart | delhivery | ekart"),
          ("name", "VARCHAR(120)", "NOT NULL", "", "", "", ""),
          ("logo", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("tracking_url_template", "VARCHAR(500)", "NOT NULL", "''", "", "", "{tracking_number} placeholder"),
          ("api_endpoint", "VARCHAR(500)", "NOT NULL", "''", "", "", "Rate/manifest integration"),
          ("supports_cod", "BOOLEAN", "NOT NULL", "TRUE", "", "", "Gates COD at checkout"),
          ("supports_reverse_pickup", "BOOLEAN", "NOT NULL", "TRUE", "", "", "Required for returns"),
          ("avg_delivery_days", "SMALLINT", "NOT NULL", "5", "", "", "Delivery estimate input"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Referenced by orders_shipment.delivery_partner_id and return_request.pickup_partner_id.",
      "GET /orders/{order_number}/tracking · /checkout (delivery options)",
      "Order Tracking, Checkout delivery method, Admin Fulfilment"),

    T("shipment_tracking_event", SHIP, "Shipping",
      "Scan-by-scan courier events. orders_shipment currently holds only three timestamps, "
      "so the tracking page shows a coarse status where customers expect a scan history.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("shipment_id", "BIGINT", "NOT NULL", "", "FK", "orders_shipment", "ON DELETE CASCADE"),
          ("status_code", "VARCHAR(32)", "NOT NULL", "", "", "", "Courier's raw code"),
          ("status_label", "VARCHAR(120)", "NOT NULL", "", "", "", "Customer-facing text"),
          ("location", "VARCHAR(150)", "NOT NULL", "''", "", "", "Scan hub"),
          ("remarks", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("occurred_at", "TIMESTAMPTZ", "NOT NULL", "", "", "", "Courier timestamp, not receipt time"),
          ("raw_payload", "JSONB", "NOT NULL", "'{}'::jsonb", "", "", "Provider response, for disputes"),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
      ],
      "Child of orders_shipment (CASCADE). UNIQUE (shipment_id, status_code, occurred_at) "
      "makes webhook replay idempotent.",
      "GET /orders/{order_number}/tracking · POST /webhooks/courier/{partner} (new)",
      "Order Tracking timeline"),

    T("return_request", SHIP, "Returns",
      "A customer's request to send an item back. /orders/{order_number}/request-return "
      "exists today but only flips the order status — there is no return record, no "
      "per-item scope, no QC outcome and no link to the refund.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("return_number", "VARCHAR(32)", "NOT NULL", "", "UQ", "", "Customer-facing RMA"),
          ("order_id", "BIGINT", "NOT NULL", "", "FK", "orders_order", "ON DELETE RESTRICT"),
          ("user_id", "BIGINT", "NOT NULL", "", "FK", "users_user", "ON DELETE RESTRICT"),
          ("return_type", "VARCHAR(16)", "NOT NULL", "'refund'", "", "", "refund | exchange | store_credit"),
          ("reason_code", "VARCHAR(32)", "NOT NULL", "", "", "",
           "size_issue | damaged | wrong_item | quality | changed_mind | late_delivery"),
          ("reason_detail", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("status", "VARCHAR(24)", "NOT NULL", "'requested'", "", "",
           "requested | approved | rejected | pickup_scheduled | picked_up | received | qc_passed | qc_failed | completed"),
          ("pickup_partner_id", "BIGINT", "NULL", "", "FK", "delivery_partner", "ON DELETE SET NULL"),
          ("pickup_tracking_number", "VARCHAR(64)", "NOT NULL", "''", "", "", ""),
          ("pickup_scheduled_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("received_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("qc_notes", "VARCHAR(500)", "NOT NULL", "''", "", "", "Warehouse inspection outcome"),
          ("refund_id", "BIGINT", "NULL", "", "FK", "payments_refund", "ON DELETE SET NULL"),
          ("refund_amount", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", "CHECK >= 0"),
          ("processed_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("completed_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
      ] + AUDIT,
      "Child of Order and User (RESTRICT). Parent of return_item. Optionally linked to the "
      "payments_refund it produced, closing the loop between goods and money.",
      "POST /orders/{order_number}/request-return · GET /returns · /admin/returns (new)",
      "Order Detail → Return, My Returns, Admin Returns queue"),

    T("return_item", SHIP, "Returns",
      "Which lines of an order are coming back, and how many units. Partial returns are the "
      "norm — a three-item order where one dress does not fit.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("return_request_id", "BIGINT", "NOT NULL", "", "FK", "return_request", "ON DELETE CASCADE"),
          ("order_item_id", "BIGINT", "NOT NULL", "", "FK", "orders_orderitem", "ON DELETE RESTRICT"),
          ("quantity", "SMALLINT", "NOT NULL", "1", "", "", "CHECK >= 1 AND <= ordered quantity"),
          ("condition", "VARCHAR(24)", "NOT NULL", "''", "", "", "unopened | used | damaged | tags_removed"),
          ("is_restockable", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Set by QC; drives inventory_transaction"),
          ("refund_amount", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", "Line share of the refund"),
      ] + AUDIT,
      "Child of return_request (CASCADE) and orders_orderitem (RESTRICT). "
      "UNIQUE (return_request_id, order_item_id).",
      "Embedded in return endpoints",
      "Return form line selection, Admin QC screen"),

    T("exchange_request", SHIP, "Returns",
      "A size or colour swap. Modelled separately from a refund because an exchange must "
      "reserve the replacement variant before the original comes back, or the customer "
      "returns an item for a size that has since sold out.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("return_request_id", "BIGINT", "NOT NULL", "", "FK", "return_request", "ON DELETE CASCADE"),
          ("original_order_item_id", "BIGINT", "NOT NULL", "", "FK", "orders_orderitem", "ON DELETE RESTRICT"),
          ("requested_variant_id", "BIGINT", "NOT NULL", "", "FK", "products_productvariant", "ON DELETE RESTRICT"),
          ("quantity", "SMALLINT", "NOT NULL", "1", "", "", "CHECK >= 1"),
          ("price_difference", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", "Signed; positive means customer pays"),
          ("status", "VARCHAR(24)", "NOT NULL", "'requested'", "", "",
           "requested | approved | reserved | dispatched | completed | rejected"),
          ("replacement_order_id", "BIGINT", "NULL", "", "FK", "orders_order", "ON DELETE SET NULL"),
          ("reserved_until", "TIMESTAMPTZ", "NULL", "", "", "", "Replacement stock hold expiry"),
      ] + AUDIT,
      "Child of return_request. References the replacement variant and, once dispatched, "
      "the replacement order.",
      "POST /orders/{order_number}/request-exchange (new)",
      "Order Detail → Exchange, Admin Exchange queue"),

    # =====================================================================
    # CONTENT, MERCHANDISING & CMS
    # =====================================================================
    T("homepage_banner", CONTENT, "Content",
      "Scheduled promotional banners by placement. Homepage content is hard-coded in the "
      "frontend today, so every campaign needs a deploy.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("title", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("subtitle", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("placement", "VARCHAR(32)", "NOT NULL", "'hero'", "", "",
           "hero | strip | grid_left | grid_right | footer | category_top"),
          ("desktop_image", "VARCHAR(255)", "NOT NULL", "", "", "", ""),
          ("mobile_image", "VARCHAR(255)", "NULL", "", "", "", "Separate crop for small screens"),
          ("alt_text", "VARCHAR(200)", "NOT NULL", "''", "", "", "Accessibility; required for WCAG"),
          ("cta_text", "VARCHAR(40)", "NOT NULL", "''", "", "", ""),
          ("target_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("category_id", "BIGINT", "NULL", "", "FK", "catalog_category", "ON DELETE SET NULL"),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
          ("starts_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("ends_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
          ("click_count", "INTEGER", "NOT NULL", "0", "", "", "Denormalised CTR numerator"),
          ("impression_count", "INTEGER", "NOT NULL", "0", "", "", "CTR denominator"),
      ] + AUDIT,
      "Optionally scoped to a category. Read by the homepage and category landing pages.",
      "GET /banners · /banners/{placement} (new)",
      "Homepage hero and strips, Category Landing banner"),

    T("hero_carousel_slide", CONTENT, "Content",
      "Ordered slides for the homepage hero carousel, with per-slide dwell time.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("banner_id", "BIGINT", "NULL", "", "FK", "homepage_banner", "ON DELETE CASCADE"),
          ("title", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("subtitle", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("desktop_image", "VARCHAR(255)", "NOT NULL", "", "", "", ""),
          ("mobile_image", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("video_url", "VARCHAR(500)", "NOT NULL", "''", "", "", "Optional motion slide"),
          ("cta_text", "VARCHAR(40)", "NOT NULL", "''", "", "", ""),
          ("target_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("text_position", "VARCHAR(16)", "NOT NULL", "'left'", "", "", "left | center | right"),
          ("duration_ms", "INTEGER", "NOT NULL", "5000", "", "", "Auto-advance delay"),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Optionally derived from a homepage_banner.",
      "GET /homepage/carousel (new)",
      "Homepage hero carousel"),

    T("product_video", CONTENT, "Content",
      "Product videos and 360° spins. products_productimage covers stills only, and video "
      "is now standard on fashion PDPs.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("product_id", "BIGINT", "NOT NULL", "", "FK", "products_product", "ON DELETE CASCADE"),
          ("video_url", "VARCHAR(500)", "NOT NULL", "", "", "", "CDN or provider URL"),
          ("thumbnail", "VARCHAR(255)", "NULL", "", "", "", "Poster frame"),
          ("video_type", "VARCHAR(16)", "NOT NULL", "'showcase'", "", "", "showcase | 360_spin | try_on | care"),
          ("provider", "VARCHAR(24)", "NOT NULL", "'self'", "", "", "self | youtube | vimeo"),
          ("duration_seconds", "SMALLINT", "NULL", "", "", "", ""),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Child of products_product (CASCADE).",
      "Embedded in GET /products/{slug}",
      "Product Detail gallery video tab"),

    T("variant_image", CONTENT, "Content",
      "Images tied to a specific colourway. products_productvariant has one "
      "image_override column, which cannot hold a gallery — so switching colour on the PDP "
      "cannot swap the whole image set.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("variant_id", "BIGINT", "NOT NULL", "", "FK", "products_productvariant", "ON DELETE CASCADE"),
          ("image", "VARCHAR(255)", "NOT NULL", "", "", "", ""),
          ("thumbnail", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("alt_text", "VARCHAR(200)", "NOT NULL", "''", "", "", ""),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
          ("is_primary", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Partial UQ per variant"),
      ] + AUDIT,
      "Child of products_productvariant (CASCADE). Partial unique on (variant_id) "
      "WHERE is_primary, mirroring products_productimage.",
      "Embedded in GET /products/{slug}",
      "Product Detail colour swatch → gallery swap"),

    T("lookbook", CONTENT, "Content",
      "Editorial styling galleries — 'Wedding Season 2026', 'Office Capsule'. Pure "
      "merchandising content with no home in the current schema.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("slug", "VARCHAR(255)", "NOT NULL", "", "UQ", "", ""),
          ("title", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("description", "TEXT", "NOT NULL", "''", "", "", ""),
          ("cover_image", "VARCHAR(255)", "NOT NULL", "", "", "", ""),
          ("season_id", "SMALLINT", "NULL", "", "FK", "lkp_season", "ON DELETE SET NULL"),
          ("occasion_id", "SMALLINT", "NULL", "", "FK", "lkp_occasion", "ON DELETE SET NULL"),
          ("influencer_id", "BIGINT", "NULL", "", "FK", "influencer", "ON DELETE SET NULL"),
          ("meta_title", "VARCHAR(70)", "NOT NULL", "''", "", "", "SEO"),
          ("meta_description", "VARCHAR(170)", "NOT NULL", "''", "", "", "SEO"),
          ("view_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("is_published", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("published_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
      ] + AUDIT,
      "Parent of lookbook_item. Optionally attributed to an influencer.",
      "GET /lookbooks · /lookbooks/{slug} (new)",
      "Lookbook index, Lookbook detail, Homepage editorial rail"),

    T("lookbook_item", CONTENT, "Content",
      "One shoppable hotspot on a lookbook image, positioned by percentage coordinates so "
      "it survives responsive scaling.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("lookbook_id", "BIGINT", "NOT NULL", "", "FK", "lookbook", "ON DELETE CASCADE"),
          ("product_id", "BIGINT", "NOT NULL", "", "FK", "products_product", "ON DELETE CASCADE"),
          ("image", "VARCHAR(255)", "NULL", "", "", "", "Per-look shot"),
          ("hotspot_x", "NUMERIC(5,2)", "NULL", "", "", "", "0–100 % of width"),
          ("hotspot_y", "NUMERIC(5,2)", "NULL", "", "", "", "0–100 % of height"),
          ("caption", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
      ] + AUDIT,
      "Child of lookbook and Product. UNIQUE (lookbook_id, product_id, display_order).",
      "Embedded in GET /lookbooks/{slug}",
      "Lookbook detail shoppable hotspots"),

    T("blog_category", CONTENT, "Content", "Taxonomy for the fashion blog.",
      lookup("blog_category", [("description", "TEXT", "NOT NULL", "''", "", "", "")]),
      "Parent of blog_post.", "GET /blog/categories (new)", "Blog index filter"),

    T("blog_post", CONTENT, "Content",
      "Fashion journal articles — SEO surface and top-of-funnel traffic.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("slug", "VARCHAR(255)", "NOT NULL", "", "UQ", "", ""),
          ("title", "VARCHAR(200)", "NOT NULL", "", "", "", ""),
          ("excerpt", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("content", "TEXT", "NOT NULL", "", "", "", "Rich text or MDX"),
          ("cover_image", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("blog_category_id", "SMALLINT", "NULL", "", "FK", "blog_category", "ON DELETE SET NULL"),
          ("author_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("influencer_id", "BIGINT", "NULL", "", "FK", "influencer", "ON DELETE SET NULL"),
          ("reading_minutes", "SMALLINT", "NOT NULL", "3", "", "", ""),
          ("view_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("meta_title", "VARCHAR(70)", "NOT NULL", "''", "", "", "SEO"),
          ("meta_description", "VARCHAR(170)", "NOT NULL", "''", "", "", "SEO"),
          ("is_published", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("published_at", "TIMESTAMPTZ", "NULL", "", "", "", "Index for the archive"),
      ] + AUDIT,
      "Child of blog_category, User and Influencer. Bridged to products via "
      "blog_post_products for shoppable articles.",
      "GET /blog · /blog/{slug} (new)",
      "Blog index, Blog article, Homepage editorial rail"),

    T("influencer", CONTENT, "Content",
      "Creator and brand-ambassador profiles behind lookbooks, articles and affiliate "
      "attribution.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("slug", "VARCHAR(255)", "NOT NULL", "", "UQ", "", ""),
          ("name", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("handle", "VARCHAR(80)", "NOT NULL", "", "UQ", "", "Social handle"),
          ("bio", "TEXT", "NOT NULL", "''", "", "", ""),
          ("avatar", "VARCHAR(255)", "NULL", "", "", "", ""),
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL; if they have a login"),
          ("instagram_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("youtube_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("follower_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("commission_percentage", "NUMERIC(5,2)", "NOT NULL", "0.00", "", "", "Affiliate rate"),
          ("referral_code", "VARCHAR(24)", "NOT NULL", "''", "UQ", "", "Attribution code"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Parent of lookbook, blog_post and influencer_campaign.",
      "GET /influencers · /influencers/{slug} (new)",
      "Influencer landing, Lookbook credits, Blog byline"),

    T("influencer_campaign", CONTENT, "Content",
      "A paid or affiliate collaboration with measurable attribution.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("influencer_id", "BIGINT", "NOT NULL", "", "FK", "influencer", "ON DELETE CASCADE"),
          ("name", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("coupon_id", "BIGINT", "NULL", "", "FK", "coupons_coupon", "ON DELETE SET NULL"),
          ("landing_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("budget", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", ""),
          ("clicks", "INTEGER", "NOT NULL", "0", "", "", "Attribution counters"),
          ("orders_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("revenue_attributed", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("commission_earned", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", ""),
          ("starts_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("ends_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Child of influencer; optionally bound to a coupon for attribution.",
      "GET /admin/influencer-campaigns (new)",
      "Admin Marketing → Campaigns"),

    T("cms_page", CONTENT, "CMS",
      "Editable static pages — About, Privacy, Terms, Shipping Policy, Size Guide. "
      "Currently frontend files, so a legal copy change is a deploy.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("slug", "VARCHAR(255)", "NOT NULL", "", "UQ", "", ""),
          ("title", "VARCHAR(200)", "NOT NULL", "", "", "", ""),
          ("content", "TEXT", "NOT NULL", "", "", "", "Rich text"),
          ("page_type", "VARCHAR(24)", "NOT NULL", "'static'", "", "", "static | legal | help | landing"),
          ("meta_title", "VARCHAR(70)", "NOT NULL", "''", "", "", "SEO"),
          ("meta_description", "VARCHAR(170)", "NOT NULL", "''", "", "", "SEO"),
          ("version", "INTEGER", "NOT NULL", "1", "", "", "Incremented on publish"),
          ("effective_from", "TIMESTAMPTZ", "NULL", "", "", "", "Legal pages need dated versions"),
          ("is_published", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("published_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("updated_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
      ] + AUDIT,
      "Standalone. Legal pages should retain superseded versions for audit.",
      "GET /pages/{slug} (new)",
      "About, Privacy Policy, Terms, Shipping Policy, Size Guide"),

    T("faq_category", CONTENT, "CMS", "Grouping for FAQs (Orders, Returns, Payments, Sizing).",
      lookup("faq_category"), "Parent of faq.", "GET /faqs (new)", "Help Centre navigation"),

    T("faq", CONTENT, "CMS",
      "Question and answer pairs for the help centre, with a helpfulness signal.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("faq_category_id", "SMALLINT", "NULL", "", "FK", "faq_category", "ON DELETE SET NULL"),
          ("question", "VARCHAR(300)", "NOT NULL", "", "", "", ""),
          ("answer", "TEXT", "NOT NULL", "", "", "", ""),
          ("display_order", "SMALLINT", "NOT NULL", "0", "", "", ""),
          ("helpful_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("not_helpful_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("is_published", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Child of faq_category.", "GET /faqs · /faqs/{category} (new)", "Help Centre, Product Detail FAQ"),

    # =====================================================================
    # Q&A
    # =====================================================================
    T("product_question", CONTENT, "Q&A",
      "Customer questions on a product page. Distinct from reviews: a question needs no "
      "purchase and expects an answer.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("product_id", "BIGINT", "NOT NULL", "", "FK", "products_product", "ON DELETE CASCADE"),
          ("user_id", "BIGINT", "NOT NULL", "", "FK", "users_user", "ON DELETE CASCADE"),
          ("question", "VARCHAR(500)", "NOT NULL", "", "", "", ""),
          ("status", "VARCHAR(12)", "NOT NULL", "'pending'", "", "", "pending | approved | rejected"),
          ("answer_count", "SMALLINT", "NOT NULL", "0", "", "", "Denormalised"),
          ("upvote_count", "INTEGER", "NOT NULL", "0", "", "", "Sorts the most-asked to the top"),
          ("moderated_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("moderated_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
      ] + AUDIT,
      "Child of Product and User. Parent of product_answer. Moderated on the same queue "
      "pattern as reviews_review.",
      "GET|POST /products/{slug}/questions (new)",
      "Product Detail → Questions & Answers"),

    T("product_answer", CONTENT, "Q&A",
      "An answer from a verified buyer, a seller or support. answered_by_type is what lets "
      "the UI badge an official reply differently from a shopper's opinion.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("question_id", "BIGINT", "NOT NULL", "", "FK", "product_question", "ON DELETE CASCADE"),
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("answer", "VARCHAR(1000)", "NOT NULL", "", "", "", ""),
          ("answered_by_type", "VARCHAR(16)", "NOT NULL", "'customer'", "", "", "customer | seller | support"),
          ("is_verified_buyer", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Derived from order history"),
          ("is_official", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Pinned above customer answers"),
          ("helpful_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("status", "VARCHAR(12)", "NOT NULL", "'pending'", "", "", "pending | approved | rejected"),
      ] + AUDIT,
      "Child of product_question (CASCADE) and User (SET NULL).",
      "POST /products/{slug}/questions/{id}/answers (new)",
      "Product Detail → Q&A thread"),

    # =====================================================================
    # LOYALTY & REWARDS
    # =====================================================================
    T("loyalty_account", ENGAGE, "Loyalty",
      "One points balance per customer with a tier. Balance is a maintained roll-up of "
      "loyalty_transaction — the ledger is authoritative, this is the fast read.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("user_id", "BIGINT", "NOT NULL", "", "FK/UQ", "users_user", "ON DELETE CASCADE; one per customer"),
          ("points_balance", "INTEGER", "NOT NULL", "0", "", "", "CHECK >= 0"),
          ("lifetime_points_earned", "INTEGER", "NOT NULL", "0", "", "", "Drives tier"),
          ("lifetime_points_redeemed", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("tier", "VARCHAR(16)", "NOT NULL", "'bronze'", "", "", "bronze | silver | gold | platinum"),
          ("tier_expires_at", "TIMESTAMPTZ", "NULL", "", "", "", "Tiers lapse without activity"),
          ("total_spent", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", "Tier qualification input"),
      ] + AUDIT,
      "One-to-one with users_user. Parent of loyalty_transaction.",
      "GET /loyalty · /loyalty/balance (new)",
      "My Account → Rewards, Checkout points redemption"),

    T("loyalty_transaction", ENGAGE, "Loyalty",
      "Append-only points ledger. Points expire, so each earning row carries its own "
      "expiry and redemption consumes oldest-first.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("loyalty_account_id", "BIGINT", "NOT NULL", "", "FK", "loyalty_account", "ON DELETE CASCADE"),
          ("transaction_type", "VARCHAR(24)", "NOT NULL", "", "", "",
           "earn | redeem | expire | adjust | refund_reversal | referral_bonus"),
          ("points", "INTEGER", "NOT NULL", "", "", "", "Signed; CHECK <> 0"),
          ("balance_after", "INTEGER", "NOT NULL", "", "", "", "Reconciliation aid"),
          ("order_id", "BIGINT", "NULL", "", "FK", "orders_order", "ON DELETE SET NULL"),
          ("description", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("expires_at", "TIMESTAMPTZ", "NULL", "", "", "", "Earning rows only"),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "Partition key"),
      ],
      "Child of loyalty_account and optionally Order. Never updated.",
      "GET /loyalty/transactions (new)",
      "My Account → Points History"),

    T("gift_card", ENGAGE, "Gift Cards",
      "Stored-value cards. The code is stored only as a hash — a gift card code is a "
      "bearer instrument, and a leaked database dump of plaintext codes is a direct "
      "financial loss.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("code_hash", "VARCHAR(128)", "NOT NULL", "", "UQ", "", "SHA-256; never store plaintext"),
          ("code_last4", "CHAR(4)", "NOT NULL", "", "", "", "Display only"),
          ("initial_value", "NUMERIC(12,2)", "NOT NULL", "", "", "", "CHECK > 0"),
          ("current_balance", "NUMERIC(12,2)", "NOT NULL", "", "", "", "CHECK >= 0 AND <= initial_value"),
          ("currency", "CHAR(3)", "NOT NULL", "'INR'", "", "", ""),
          ("purchased_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("recipient_email", "VARCHAR(254)", "NOT NULL", "''", "", "", ""),
          ("recipient_name", "VARCHAR(150)", "NOT NULL", "''", "", "", ""),
          ("message", "VARCHAR(500)", "NOT NULL", "''", "", "", "Gift note"),
          ("redeemed_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("status", "VARCHAR(16)", "NOT NULL", "'active'", "", "", "active | redeemed | expired | cancelled"),
          ("issued_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("expires_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
      ] + AUDIT,
      "References the purchaser and the redeemer. Parent of gift_card_transaction.",
      "POST /gift-cards/purchase · /gift-cards/redeem · GET /gift-cards/balance (new)",
      "Gift Card purchase, Checkout redemption, My Account → Gift Cards"),

    T("gift_card_transaction", ENGAGE, "Gift Cards",
      "Every debit and credit against a card balance.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("gift_card_id", "BIGINT", "NOT NULL", "", "FK", "gift_card", "ON DELETE RESTRICT"),
          ("order_id", "BIGINT", "NULL", "", "FK", "orders_order", "ON DELETE SET NULL"),
          ("transaction_type", "VARCHAR(16)", "NOT NULL", "", "", "", "issue | redeem | refund | expire"),
          ("amount", "NUMERIC(12,2)", "NOT NULL", "", "", "", "Signed"),
          ("balance_after", "NUMERIC(12,2)", "NOT NULL", "", "", "", ""),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
      ],
      "Child of gift_card (RESTRICT — a card with movements is never deleted).",
      "Embedded in gift card endpoints", "My Account → Gift Card history"),

    T("referral", ENGAGE, "Referrals",
      "Refer-a-friend tracking. A partial unique index on referred_user_id stops one "
      "person being claimed by two referrers, which is the standard abuse.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("referrer_id", "BIGINT", "NOT NULL", "", "FK", "users_user", "ON DELETE CASCADE"),
          ("referred_user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("referral_code", "VARCHAR(24)", "NOT NULL", "", "", "", "Referrer's code"),
          ("referred_email", "VARCHAR(254)", "NOT NULL", "''", "", "", "Before signup"),
          ("status", "VARCHAR(16)", "NOT NULL", "'invited'", "", "", "invited | signed_up | qualified | rewarded | expired"),
          ("qualifying_order_id", "BIGINT", "NULL", "", "FK", "orders_order", "ON DELETE SET NULL"),
          ("referrer_reward_points", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("referred_reward_points", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("rewarded_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
      ] + AUDIT,
      "Two references to users_user. Reward payout writes to loyalty_transaction.",
      "GET /referrals · POST /referrals/invite (new)",
      "My Account → Refer a Friend, Signup with referral code"),

    # =====================================================================
    # SEARCH, BEHAVIOUR & AI
    # =====================================================================
    T("search_history", BEHAV, "Search",
      "Every search query with its result count. Nothing persists searches today, so the "
      "zero-result queries that reveal catalogue gaps are invisible.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE CASCADE"),
          ("session_key", "VARCHAR(64)", "NOT NULL", "''", "", "", "Guest identity"),
          ("query", "VARCHAR(255)", "NOT NULL", "", "", "", "Normalised lower-case"),
          ("normalised_query", "VARCHAR(255)", "NOT NULL", "", "", "", "Stemmed; groups variants"),
          ("result_count", "INTEGER", "NOT NULL", "0", "", "", "0 = catalogue gap"),
          ("clicked_product_id", "BIGINT", "NULL", "", "FK", "products_product", "ON DELETE SET NULL"),
          ("click_position", "SMALLINT", "NULL", "", "", "", "Relevance signal"),
          ("filters_applied", "JSONB", "NOT NULL", "'{}'::jsonb", "", "", "Facet state"),
          ("device_type", "VARCHAR(16)", "NOT NULL", "''", "", "", "mobile | desktop | tablet"),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "Partition key"),
      ],
      "Optional child of User and Product. Feeds trending_search and the merchandising "
      "zero-results report.",
      "GET /products/search (writes) · GET /products/suggestions",
      "Search bar, Search Results, My Account → Recent Searches"),

    T("trending_search", BEHAV, "Search",
      "Aggregated popular queries per window. /products/suggestions serves a static list "
      "today; this makes it reflect what people actually search.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("query", "VARCHAR(255)", "NOT NULL", "", "", "", ""),
          ("search_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("click_through_rate", "NUMERIC(5,2)", "NOT NULL", "0.00", "", "", "Quality signal"),
          ("window_start", "DATE", "NOT NULL", "", "", "", ""),
          ("window_end", "DATE", "NOT NULL", "", "", "", ""),
          ("rank", "SMALLINT", "NOT NULL", "0", "", "", "Position in the window"),
          ("is_promoted", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Merchandiser pin"),
      ] + AUDIT,
      "Derived from search_history by a scheduled job. UNIQUE (query, window_start, window_end).",
      "GET /products/suggestions · /products/search-defaults",
      "Search bar suggestions, Trending Searches chips"),

    T("clickstream_event", BEHAV, "Behaviour",
      "Raw interaction events — the highest-volume table in the schema and the reason the "
      "partitioning section exists. Expect tens of millions of rows a month; it must be "
      "range-partitioned by day from the outset.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", "Composite PK with occurred_at when partitioned"),
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("session_key", "VARCHAR(64)", "NOT NULL", "''", "", "", ""),
          ("event_type", "VARCHAR(32)", "NOT NULL", "", "", "",
           "page_view | product_view | add_to_cart | remove_from_cart | wishlist_add | "
           "checkout_start | purchase | search | filter | banner_click"),
          ("product_id", "BIGINT", "NULL", "", "FK", "products_product", "ON DELETE SET NULL"),
          ("category_id", "BIGINT", "NULL", "", "FK", "catalog_category", "ON DELETE SET NULL"),
          ("page_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("referrer_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("utm_source", "VARCHAR(80)", "NOT NULL", "''", "", "", "Attribution"),
          ("utm_medium", "VARCHAR(80)", "NOT NULL", "''", "", "", ""),
          ("utm_campaign", "VARCHAR(120)", "NOT NULL", "''", "", "", ""),
          ("device_type", "VARCHAR(16)", "NOT NULL", "''", "", "", ""),
          ("ip_address", "INET", "NULL", "", "", "", "Truncate or hash under DPDP"),
          ("metadata", "JSONB", "NOT NULL", "'{}'::jsonb", "", "", "Event-specific payload"),
          ("occurred_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "PARTITION KEY"),
      ],
      "Optional references to User, Product and Category — all SET NULL so a deletion "
      "never blocks on the largest table in the database.",
      "POST /events (new, fire-and-forget)",
      "Every page (instrumentation layer)"),

    T("fashion_preference", BEHAV, "AI Personalisation",
      "A shopper's derived and declared style profile — the feature vector the "
      "recommendation engine reads. Today taste is recomputed from orders, wishlist and "
      "browsing on every request.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("user_id", "BIGINT", "NOT NULL", "", "FK/UQ", "users_user", "ON DELETE CASCADE; one per customer"),
          ("preferred_sizes", "JSONB", "NOT NULL", "'{}'::jsonb", "", "", "Per category: {\"tops\":\"M\"}"),
          ("preferred_colours", "JSONB", "NOT NULL", "'[]'::jsonb", "", "", "Weighted colour ids"),
          ("preferred_brands", "JSONB", "NOT NULL", "'[]'::jsonb", "", "", "Weighted brand ids"),
          ("preferred_categories", "JSONB", "NOT NULL", "'[]'::jsonb", "", "", "Weighted category ids"),
          ("preferred_occasions", "JSONB", "NOT NULL", "'[]'::jsonb", "", "", ""),
          ("price_band_min", "NUMERIC(12,2)", "NULL", "", "", "", "Observed spend floor"),
          ("price_band_max", "NUMERIC(12,2)", "NULL", "", "", "", "Observed spend ceiling"),
          ("style_vector", "JSONB", "NOT NULL", "'{}'::jsonb", "", "", "Embedding; migrate to pgvector at scale"),
          ("is_explicit", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Declared by the customer vs inferred"),
          ("last_computed_at", "TIMESTAMPTZ", "NULL", "", "", "", "Recompute staleness"),
      ] + AUDIT,
      "One-to-one with users_user. Written by the nightly personalisation job; read by "
      "the for-you and new-for-you rails.",
      "GET /recommendations/for-you · /recommendations/new-for-you",
      "Homepage For You rail, Style Quiz, My Account → Preferences"),

    T("recommendation_history", BEHAV, "AI Personalisation",
      "What was recommended, where, and whether it was clicked or bought. Without this "
      "there is no way to tell whether the recommendation engine earns its place.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("session_key", "VARCHAR(64)", "NOT NULL", "''", "", "", ""),
          ("product_id", "BIGINT", "NOT NULL", "", "FK", "products_product", "ON DELETE CASCADE"),
          ("source_product_id", "BIGINT", "NULL", "", "FK", "products_product", "ON DELETE SET NULL", ),
          ("rail", "VARCHAR(40)", "NOT NULL", "", "", "",
           "related | similar | fbt | trending | recently_popular | also_viewed | new_for_you | for_you"),
          ("algorithm_version", "VARCHAR(24)", "NOT NULL", "'v1'", "", "", "A/B comparison"),
          ("score", "DOUBLE PRECISION", "NOT NULL", "0", "", "", "Model score at serve time"),
          ("position", "SMALLINT", "NOT NULL", "0", "", "", "Slot in the rail"),
          ("was_clicked", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("was_added_to_cart", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("was_purchased", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
          ("served_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "Partition key"),
      ],
      "References User and Product twice (recommended and source).",
      "Written by every /recommendations/* endpoint",
      "All recommendation rails (instrumentation)"),

    # =====================================================================
    # NOTIFICATION & EMAIL TEMPLATES
    # =====================================================================
    T("notification_template", CONTENT, "Notifications",
      "Database-backed notification copy. Nineteen event templates live in Python today "
      "(apps/notifications/templates.py), which means marketing cannot change a subject "
      "line without a deploy. Moving them here keeps the code as the fallback.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("event_key", "VARCHAR(64)", "NOT NULL", "", "UQ*", "", "Composite UQ with channel and locale"),
          ("channel", "VARCHAR(8)", "NOT NULL", "", "UQ*", "", "in_app | email | sms | push"),
          ("locale", "VARCHAR(10)", "NOT NULL", "'en'", "UQ*", "", "Localisation"),
          ("category", "VARCHAR(16)", "NOT NULL", "'system'", "", "", "account | order | payment | review | marketing | system"),
          ("subject_template", "VARCHAR(200)", "NOT NULL", "", "", "", "str.format placeholders"),
          ("body_template", "TEXT", "NOT NULL", "", "", "", ""),
          ("link_template", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("available_variables", "JSONB", "NOT NULL", "'[]'::jsonb", "", "", "Documents valid placeholders"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
          ("version", "INTEGER", "NOT NULL", "1", "", "", ""),
      ] + AUDIT,
      "Read by the notification service before falling back to the code catalogue. "
      "Composite UNIQUE (event_key, channel, locale).",
      "GET /admin/notification-templates (new)",
      "Admin → Notification Templates"),

    T("email_template", CONTENT, "Notifications",
      "HTML email layouts, separate from notification_template because an email has a "
      "wrapper, inline CSS and a plain-text alternative that a push payload does not.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("code", "VARCHAR(64)", "NOT NULL", "", "UQ", "", ""),
          ("name", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("subject", "VARCHAR(200)", "NOT NULL", "", "", "", ""),
          ("html_body", "TEXT", "NOT NULL", "", "", "", "Inlined CSS"),
          ("text_body", "TEXT", "NOT NULL", "''", "", "", "Multipart alternative"),
          ("layout_code", "VARCHAR(64)", "NOT NULL", "''", "", "", "Shared header/footer wrapper"),
          ("from_name", "VARCHAR(120)", "NOT NULL", "''", "", "", ""),
          ("reply_to", "VARCHAR(254)", "NOT NULL", "''", "", "", ""),
          ("locale", "VARCHAR(10)", "NOT NULL", "'en'", "", "", ""),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Referenced by notification_template for email-channel rows.",
      "GET /admin/email-templates (new)", "Admin → Email Templates"),

    # =====================================================================
    # ADMIN, RBAC & AUDIT
    # =====================================================================
    T("admin_role", ADMIN, "Admin",
      "Named back-office roles. Authorisation is a single is_staff boolean today, so a "
      "catalogue merchandiser and a finance controller have identical access — including "
      "to revenue and refunds.",
      [
          ("id", "SMALLSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("code", "VARCHAR(32)", "NOT NULL", "", "UQ", "", "super_admin | catalog_manager | order_manager | finance | support | marketing"),
          ("name", "VARCHAR(80)", "NOT NULL", "", "", "", ""),
          ("description", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("is_system", "BOOLEAN", "NOT NULL", "FALSE", "", "", "System roles cannot be deleted"),
          ("is_active", "BOOLEAN", "NOT NULL", "TRUE", "", "", ""),
      ] + AUDIT,
      "Bridged to admin_permission and users_user.",
      "GET /admin/roles (new)", "Admin → Roles & Permissions"),

    T("admin_permission", ADMIN, "Admin",
      "Atomic permission keys, one per module and action.",
      [
          ("id", "SMALLSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("code", "VARCHAR(64)", "NOT NULL", "", "UQ", "", "e.g. orders.refund"),
          ("module", "VARCHAR(32)", "NOT NULL", "", "", "", "catalog | orders | payments | reviews | analytics | cms"),
          ("action", "VARCHAR(24)", "NOT NULL", "", "", "", "view | create | update | delete | approve | export"),
          ("description", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
      ] + AUDIT,
      "Bridged to admin_role.", "GET /admin/permissions (new)", "Admin → Roles & Permissions"),

    T("admin_role_permission", ADMIN, "Admin",
      "Bridge granting permissions to a role.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("role_id", "SMALLINT", "NOT NULL", "", "FK", "admin_role", "ON DELETE CASCADE"),
          ("permission_id", "SMALLINT", "NOT NULL", "", "FK", "admin_permission", "ON DELETE CASCADE"),
          ("granted_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("granted_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
      ],
      "Bridge: admin_role ↔ admin_permission. UNIQUE (role_id, permission_id).",
      "Evaluated on every /admin/* request", "Admin → Role editor"),

    T("admin_user_role", ADMIN, "Admin",
      "Bridge assigning back-office roles to staff accounts, with optional expiry for "
      "temporary elevation.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("user_id", "BIGINT", "NOT NULL", "", "FK", "users_user", "ON DELETE CASCADE"),
          ("role_id", "SMALLINT", "NOT NULL", "", "FK", "admin_role", "ON DELETE CASCADE"),
          ("assigned_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
          ("assigned_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("expires_at", "TIMESTAMPTZ", "NULL", "", "", "", "Temporary elevation"),
      ],
      "Bridge: users_user ↔ admin_role. UNIQUE (user_id, role_id).",
      "Evaluated on every /admin/* request", "Admin → Staff"),

    T("audit_log", ADMIN, "Audit",
      "Row-level before/after change log for sensitive entities. There is currently no "
      "record of who changed a price, approved a refund or edited an order — a gap that "
      "fails any commercial audit.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("entity_type", "VARCHAR(64)", "NOT NULL", "", "", "", "Table name"),
          ("entity_id", "VARCHAR(64)", "NOT NULL", "", "", "", "Text, so UUID and BIGINT both fit"),
          ("action", "VARCHAR(24)", "NOT NULL", "", "", "", "create | update | delete | approve | reject | export"),
          ("old_values", "JSONB", "NULL", "", "", "", "Changed columns only"),
          ("new_values", "JSONB", "NULL", "", "", "", ""),
          ("changed_fields", "JSONB", "NOT NULL", "'[]'::jsonb", "", "", "Fast filter without diffing"),
          ("performed_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("performed_by_type", "VARCHAR(16)", "NOT NULL", "'user'", "", "", "user | system | api | job"),
          ("ip_address", "INET", "NULL", "", "", "", ""),
          ("user_agent", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("request_id", "VARCHAR(64)", "NOT NULL", "''", "", "", "Correlates with application logs"),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "PARTITION KEY"),
      ],
      "Optional reference to the acting user (SET NULL — the log outlives the account). "
      "Written by database triggers on sensitive tables, not by application code.",
      "GET /admin/audit-logs (new)", "Admin → Audit Trail"),

    T("activity_log", ADMIN, "Audit",
      "Customer-facing activity feed: logins, password changes, address edits, order "
      "placement. Distinct from audit_log, which is for staff actions on data.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE CASCADE"),
          ("activity_type", "VARCHAR(32)", "NOT NULL", "", "", "",
           "login | logout | login_failed | password_change | profile_update | address_add | order_place | review_post"),
          ("description", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("ip_address", "INET", "NULL", "", "", "", ""),
          ("user_agent", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("device_type", "VARCHAR(16)", "NOT NULL", "''", "", "", ""),
          ("location", "VARCHAR(120)", "NOT NULL", "''", "", "", "Geo-IP city; 'new device' alerts"),
          ("is_suspicious", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Flagged by risk rules"),
          ("created_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "PARTITION KEY"),
      ],
      "Child of users_user (CASCADE).",
      "GET /account/activity (new)", "My Account → Login Activity, Security alerts"),

    T("system_setting", ADMIN, "System",
      "Runtime configuration a business user may change without a deploy. Everything is "
      "environment variables today, so altering the free-shipping threshold restarts the "
      "application.",
      [
          ("key", "VARCHAR(100)", "NOT NULL", "", "PK", "", "Natural key"),
          ("value", "TEXT", "NOT NULL", "", "", "", ""),
          ("data_type", "VARCHAR(16)", "NOT NULL", "'string'", "", "", "string | integer | decimal | boolean | json"),
          ("module", "VARCHAR(32)", "NOT NULL", "''", "", "", "cart | catalog | payments | notifications"),
          ("description", "VARCHAR(255)", "NOT NULL", "''", "", "", ""),
          ("is_public", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Safe to expose to the frontend"),
          ("is_encrypted", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Secrets stay in the environment"),
          ("updated_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
      ] + AUDIT,
      "Standalone. Cached aggressively; invalidated on write.",
      "GET /admin/settings · GET /config/public (new)",
      "Admin → Settings, frontend bootstrap config"),

    # =====================================================================
    # SUPPORT
    # =====================================================================
    T("contact_message", SUPPORT, "Support",
      "Contact-form submissions. The frontend has a Contact page with nowhere to post to.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("user_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("name", "VARCHAR(150)", "NOT NULL", "", "", "", ""),
          ("email", "VARCHAR(254)", "NOT NULL", "", "", "", ""),
          ("phone", "VARCHAR(16)", "NOT NULL", "''", "", "", ""),
          ("subject", "VARCHAR(200)", "NOT NULL", "", "", "", ""),
          ("message", "TEXT", "NOT NULL", "", "", "", ""),
          ("category", "VARCHAR(32)", "NOT NULL", "'general'", "", "", "general | order | product | partnership | press"),
          ("status", "VARCHAR(16)", "NOT NULL", "'new'", "", "", "new | read | responded | closed | spam"),
          ("responded_by_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("responded_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("ip_address", "INET", "NULL", "", "", "", "Spam triage"),
      ] + AUDIT,
      "Optional reference to a signed-in user; may be escalated into a support_ticket.",
      "POST /contact (new)", "Contact Us page, Admin → Messages"),

    T("support_ticket", SUPPORT, "Support",
      "Customer support cases with SLA tracking.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("ticket_number", "VARCHAR(24)", "NOT NULL", "", "UQ", "", "Customer-facing reference"),
          ("user_id", "BIGINT", "NOT NULL", "", "FK", "users_user", "ON DELETE CASCADE"),
          ("order_id", "BIGINT", "NULL", "", "FK", "orders_order", "ON DELETE SET NULL"),
          ("return_request_id", "BIGINT", "NULL", "", "FK", "return_request", "ON DELETE SET NULL"),
          ("category", "VARCHAR(32)", "NOT NULL", "'general'", "", "", "order | payment | return | product | account | general"),
          ("subject", "VARCHAR(200)", "NOT NULL", "", "", "", ""),
          ("priority", "VARCHAR(12)", "NOT NULL", "'normal'", "", "", "low | normal | high | urgent"),
          ("status", "VARCHAR(20)", "NOT NULL", "'open'", "", "", "open | in_progress | waiting_customer | resolved | closed"),
          ("assigned_to_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("first_response_at", "TIMESTAMPTZ", "NULL", "", "", "", "SLA numerator"),
          ("resolved_at", "TIMESTAMPTZ", "NULL", "", "", "", ""),
          ("sla_due_at", "TIMESTAMPTZ", "NULL", "", "", "", "Breach reporting"),
          ("satisfaction_rating", "SMALLINT", "NULL", "", "", "", "CHECK 1..5"),
      ] + AUDIT,
      "Child of User; optionally linked to an order or return. Parent of support_message.",
      "GET|POST /support/tickets · /support/tickets/{number} (new)",
      "Help Centre → My Tickets, Admin → Support Queue"),

    T("support_message", SUPPORT, "Support",
      "One message in a ticket thread. is_internal keeps staff notes out of the customer view.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""), UUIDC,
          ("ticket_id", "BIGINT", "NOT NULL", "", "FK", "support_ticket", "ON DELETE CASCADE"),
          ("sender_id", "BIGINT", "NULL", "", "FK", "users_user", "ON DELETE SET NULL"),
          ("sender_type", "VARCHAR(12)", "NOT NULL", "'customer'", "", "", "customer | agent | system"),
          ("message", "TEXT", "NOT NULL", "", "", "", ""),
          ("attachment_url", "VARCHAR(500)", "NOT NULL", "''", "", "", ""),
          ("is_internal", "BOOLEAN", "NOT NULL", "FALSE", "", "", "Staff-only note"),
          ("is_read", "BOOLEAN", "NOT NULL", "FALSE", "", "", ""),
      ] + AUDIT,
      "Child of support_ticket (CASCADE).",
      "Embedded in ticket endpoints", "Ticket thread, Admin → Ticket Detail"),

    # =====================================================================
    # ANALYTICS AGGREGATION
    # =====================================================================
    T("analytics_daily_sales", ANALYT, "Analytics",
      "Pre-aggregated daily sales. The analytics module computes everything live from the "
      "orders table, which is correct now and will not hold past roughly a hundred thousand "
      "orders. One row per day per currency.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("snapshot_date", "DATE", "NOT NULL", "", "UQ*", "", "Composite UQ with currency"),
          ("currency", "CHAR(3)", "NOT NULL", "'INR'", "UQ*", "", ""),
          ("orders_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("units_sold", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("gross_revenue", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("discount_total", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("coupon_discount_total", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("shipping_total", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("tax_total", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("refund_total", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("net_revenue", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", "gross − refunds"),
          ("average_order_value", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", ""),
          ("cancelled_orders", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("new_customers", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("returning_customers", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("computed_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", "Recompute stamp"),
      ],
      "Derived from orders_order and payments_refund by a nightly job. Rebuildable at any "
      "time from source — never the system of record.",
      "GET /admin/dashboard/summary · /admin/dashboard/charts · /admin/reports/revenue",
      "Admin Dashboard cards and charts, Revenue Report"),

    T("analytics_product_daily", ANALYT, "Analytics",
      "Per-product daily performance, and the funnel the current schema cannot produce: "
      "views to cart-adds to purchases.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("snapshot_date", "DATE", "NOT NULL", "", "UQ*", "", "Composite UQ with product_id"),
          ("product_id", "BIGINT", "NOT NULL", "", "FK/UQ*", "products_product", "ON DELETE CASCADE"),
          ("views", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("unique_viewers", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("cart_adds", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("wishlist_adds", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("units_sold", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("revenue", "NUMERIC(14,2)", "NOT NULL", "0.00", "", "", ""),
          ("returns_count", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("conversion_rate", "NUMERIC(5,2)", "NOT NULL", "0.00", "", "", "purchases ÷ views"),
          ("cart_abandonment_rate", "NUMERIC(5,2)", "NOT NULL", "0.00", "", "", ""),
          ("computed_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
      ],
      "Child of products_product (CASCADE). Partition by snapshot_date range.",
      "GET /admin/analytics/top-products · /admin/reports/sales",
      "Admin Product Analytics, Sales Report"),

    T("analytics_customer_daily", ANALYT, "Analytics",
      "Customer cohort and retention metrics, computed once rather than on every dashboard "
      "load.",
      [
          ("id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", ""),
          ("snapshot_date", "DATE", "NOT NULL", "", "UQ", "", ""),
          ("total_customers", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("new_signups", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("active_customers", "INTEGER", "NOT NULL", "0", "", "", "Placed an order that day"),
          ("returning_customers", "INTEGER", "NOT NULL", "0", "", "", ""),
          ("churned_customers", "INTEGER", "NOT NULL", "0", "", "", "No order in 180 days"),
          ("average_lifetime_value", "NUMERIC(12,2)", "NOT NULL", "0.00", "", "", ""),
          ("repeat_purchase_rate", "NUMERIC(5,2)", "NOT NULL", "0.00", "", "", ""),
          ("cart_abandonment_rate", "NUMERIC(5,2)", "NOT NULL", "0.00", "", "", ""),
          ("computed_at", "TIMESTAMPTZ", "NOT NULL", "now()", "", "", ""),
      ],
      "Derived from users_user and orders_order nightly.",
      "GET /admin/dashboard/customers · /admin/reports/customers",
      "Admin Customer Analytics, Customer Report"),
]
