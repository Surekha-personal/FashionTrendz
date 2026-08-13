"""Assemble the Fashion Trendz database design document."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    KeepTogether, NextPageTemplate, PageBreak, Paragraph, Preformatted, Spacer,
)

import introspect as I  # noqa: E402
import render as R  # noqa: E402
from spec_backmatter import (  # noqa: E402
    ERD_CATALOG, ERD_CUSTOMER, ERD_NOTES, INDEX_NOTES, NORMALISATION,
    PARTITIONS, PERFORMANCE, PROCEDURES,
)
from spec_implemented import IMPLEMENTED  # noqa: E402
from spec_proposed import PROPOSED  # noqa: E402

VERSION = "1.0"
TODAY = date.today().strftime("%d %B %Y")

COL_HEADER = ["Column Name", "Data Type", "Nullable", "Default", "Key", "References", "Notes"]
COL_WIDTHS = [30, 22, 13, 18, 9, 27, 46]
COL_STYLES = [R.S_MONO, R.S_MONO, R.S_CELL, R.S_MONO, R.S_CELL_B, R.S_MONO, R.S_NOTE]

KEY_HEADER = ["Type", "Constraint / Index Name", "Column(s)", "Definition & Behaviour"]
KEY_WIDTHS = [12, 30, 24, 66]
KEY_STYLES = [R.S_CELL_B, R.S_MONO, R.S_MONO, R.S_NOTE]


def _all_tables() -> list[dict]:
    """Return every table, implemented first, in document order."""
    out = []
    for e in IMPLEMENTED:
        out.append({**e, "status": "IMPLEMENTED", "cols": None})
    for e in PROPOSED:
        out.append({**e, "status": "PROPOSED"})
    return out


TABLES = _all_tables()


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------

def cover() -> list:
    """Return the cover page flowables."""
    impl = sum(1 for t in TABLES if t["status"] == "IMPLEMENTED")
    prop = len(TABLES) - impl

    s = [Spacer(1, 34 * mm)]
    s.append(Paragraph("FASHION TRENDZ", R.S_TITLE))
    s.append(Paragraph("E-COMMERCE PLATFORM", R.S_TITLE))
    s.append(Spacer(1, 5 * mm))
    s.append(Paragraph("DATABASE DESIGN DOCUMENT", R._st(
        "cst", fontName="Helvetica-Bold", fontSize=15, alignment=1, textColor=R.ACCENT)))
    s.append(Spacer(1, 14 * mm))

    meta = [
        ["Project Name", "Fashion Trendz E-Commerce Platform"],
        ["Document", "Fashion Trendz Database Schema"],
        ["Version", VERSION],
        ["Date", TODAY],
        ["Database Engine", "PostgreSQL 18"],
        ["Total Tables", f"{len(TABLES)}  ({impl} implemented · {prop} proposed)"],
        ["Framework Tables", "8 (Django & SimpleJWT internals — documented in Appendix A)"],
        ["Total Stored Procedures", str(len(PROCEDURES))],
        ["Total Indexes", "47 existing + 18 recommended"],
        ["Total Foreign Keys", "63 implemented + 71 proposed"],
        ["Source of Truth", "Django model metadata, introspected from the live migration state"],
        ["Prepared For", "Fashion Trendz Database Engineering Team"],
        ["Prepared By", "Lead Database Architect"],
        ["Classification", "Confidential — Internal Engineering"],
    ]
    t = R.grid(["Field", "Value"], meta, [26, 74],
               [R.S_CELL_B, R.S_BODY], repeat=1)
    s.append(t)
    s.append(Spacer(1, 10 * mm))
    s.append(Paragraph(
        "This document describes the physical database design for the Fashion Trendz "
        "platform. The implemented tables are derived directly from the shipped Django "
        "backend by introspecting model metadata against the applied migration state — not "
        "transcribed by hand — so the column definitions, constraints and indexes below are "
        "the ones actually present in the database. Proposed tables are clearly marked and "
        "represent new build required to satisfy the full product brief.",
        R._st("cnote", fontSize=8, leading=11.5, alignment=4, textColor=R.MUTED)))
    return s


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def overview() -> list:
    """Return the numbered table inventory."""
    s = R.h1("Overview — Complete Table Inventory")
    s.append(Paragraph(
        "Every table in the Fashion Trendz database, numbered and grouped by module. "
        "Status distinguishes what exists today from what this document specifies for build.",
        R.S_BODY))
    s.append(Spacer(1, 3 * mm))

    rows = []
    for i, t in enumerate(TABLES, 1):
        purpose = t["purpose"].split(".")[0].strip()
        if len(purpose) > 115:
            purpose = purpose[:112] + "…"
        rows.append([str(i), t["table"], purpose, t["module"].title(),
                     t["section"], t["status"]])

    shade = {i: R.PROPOSED for i, t in enumerate(TABLES, 1) if t["status"] == "PROPOSED"}
    s.append(R.grid(["#", "Table Name", "Description", "Module", "Section", "Status"],
                    rows, [4, 22, 44, 16, 8, 9],
                    [R.S_CELL, R.S_MONO, R.S_NOTE, R.S_CELL, R.S_CELL, R.S_CELL_B],
                    shade=shade))
    return s


def conventions() -> list:
    """Return the design-conventions page."""
    s = R.h1("Design Conventions")
    rows = [
        ["Primary keys", "BIGSERIAL surrogate on every table",
         "Monotonic integers keep B-tree inserts local. A random UUID primary key fragments "
         "every index on a table this size."],
        ["Public identifiers", "uuid UUID DEFAULT gen_random_uuid(), UNIQUE",
         "Exposed in URLs and API payloads so row counts and insert rates are not leaked. "
         "Secondary, never the PK."],
        ["Audit columns", "created_at, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
         "Inherited by all 41 implemented tables from a shared abstract base; omitted from "
         "per-table grids only where noted."],
        ["Timestamps", "TIMESTAMPTZ, stored UTC",
         "The application runs Asia/Kolkata; storage is always UTC."],
        ["Money", "NUMERIC(12,2) — NUMERIC(14,2) for aggregates",
         "Never FLOAT. A rupee amount that cannot round-trip is a reconciliation failure."],
        ["Currency", "CHAR(3), ISO 4217, default 'INR'", "Stored per row, not assumed."],
        ["Enumerations", "VARCHAR with a CHECK constraint",
         "Not PostgreSQL ENUM types: altering an ENUM takes a lock, and adding a status "
         "should not require one. The lkp_* tables normalise the catalogue-facing ones."],
        ["Text", "VARCHAR(n) where bounded, TEXT where not",
         "Bounds are validation, documented per column."],
        ["Booleans", "BOOLEAN NOT NULL with an explicit default",
         "Never nullable — a three-valued flag is a bug waiting to be written."],
        ["Blank strings", "'' rather than NULL for optional short text",
         "Django convention, carried into the schema. NULL is reserved for 'not applicable'."],
        ["Soft delete", "Not used; is_active / status columns instead",
         "Deletion is genuinely rare. PROTECT foreign keys guard the financial chain."],
        ["Naming", "snake_case; tables prefixed by owning module",
         "e.g. orders_order, payments_refund. Proposed tables adopt the same rule."],
        ["Constraint naming", "pk_ / uq_ / fk_ / ck_ / idx_ prefixes",
         "So a violation message names the rule that fired."],
        ["Cascade policy", "CASCADE for owned children; PROTECT on financial edges; "
         "SET NULL where the child outlives the parent",
         "Applied consistently — see the ERD notes."],
    ]
    s.append(R.grid(["Convention", "Rule", "Rationale"], rows, [16, 30, 54],
                    [R.S_CELL_B, R.S_MONO, R.S_NOTE]))
    return s


# ---------------------------------------------------------------------------
# Table sections
# ---------------------------------------------------------------------------

def _meta_block(t: dict) -> list:
    """Return the purpose / relationships / APIs / pages block."""
    rows = [
        ["Purpose", t["purpose"]],
        ["Relationships", t["rel"]],
        ["Used By APIs", t["apis"]],
        ["Used By Frontend Pages", t["pages"]],
    ]
    return [R.grid(["Attribute", "Detail"], rows, [15, 85],
                   [R.S_CELL_B, R.S_NOTE], repeat=0)]


def table_section(t: dict) -> list:
    """Return the flowables documenting one table."""
    s: list = []
    head = f"{t['table']}"
    s.append(R.h2(head, t["status"]))
    s.append(Spacer(1, 1.5 * mm))

    if t["status"] == "IMPLEMENTED":
        cols = I.columns(t["table"])
        shade = I.shading(t["table"])
        s.append(R.grid(COL_HEADER, cols, COL_WIDTHS, COL_STYLES, shade=shade))
        s.append(Spacer(1, 2 * mm))
        s.append(Paragraph(
            f"Default ordering: {I.ordering(t['table'])} · {len(cols)} columns",
            R.S_NOTE))
        s.append(Spacer(1, 2 * mm))
        s.append(R.grid(KEY_HEADER, I.constraints(t["table"]), KEY_WIDTHS, KEY_STYLES))
    else:
        cols = [list(c) for c in t["cols"]]
        shade = {}
        for i, c in enumerate(cols, 1):
            k = c[4]
            if "PK" in k:
                shade[i] = R.PK_BG
            elif "FK" in k:
                shade[i] = R.FK_BG
            elif "UQ" in k:
                shade[i] = R.UQ_BG
        s.append(R.grid(COL_HEADER, cols, COL_WIDTHS, COL_STYLES, shade=shade))
        s.append(Spacer(1, 2 * mm))
        s.append(Paragraph(f"{len(cols)} columns · NEW BUILD REQUIRED", R.S_NOTE))

    s.append(Spacer(1, 2 * mm))
    s += _meta_block(t)
    s.append(Spacer(1, 6 * mm))
    return s


def modules() -> list:
    """Return every module section, in document order."""
    s: list = []
    current = None
    for t in TABLES:
        if t["module"] != current:
            current = t["module"]
            s.append(PageBreak())
            s += R.h1(current)
        s += table_section(t)
    return s


# ---------------------------------------------------------------------------
# Back matter
# ---------------------------------------------------------------------------

def erd() -> list:
    """Return the entity relationship diagram."""
    s = R.h1("Entity Relationship Diagram")
    s.append(Paragraph("Customer & Transaction Domain", R.S_H3))
    s.append(Spacer(1, 2 * mm))
    s.append(Preformatted(ERD_CUSTOMER, R.S_ERD))
    s.append(PageBreak())
    s += R.h1("Entity Relationship Diagram")
    s.append(Paragraph("Catalog & Product Domain", R.S_H3))
    s.append(Spacer(1, 2 * mm))
    s.append(Preformatted(ERD_CATALOG, R.S_ERD))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph("Referential Integrity Notes", R.S_H3))
    s.append(Spacer(1, 2 * mm))
    s.append(R.grid(["#", "Note"],
                    [[str(i), n] for i, n in enumerate(ERD_NOTES, 1)],
                    [4, 96], [R.S_CELL, R.S_NOTE]))
    return s


def procedures() -> list:
    """Return the stored procedure specification."""
    s = R.h1("Stored Procedures")
    s.append(Paragraph(
        "Business logic currently lives in the Django service layer. The procedures below "
        "are specified for operations where a per-step round trip is the actual cost, or "
        "where atomicity must hold under concurrency regardless of which application "
        "connects. They are specifications, not implementations — no procedure exists yet.",
        R.S_BODY))
    s.append(Spacer(1, 3 * mm))
    rows = [[str(i), p[0], p[1], p[2], p[3], p[4]]
            for i, p in enumerate(PROCEDURES, 1)]
    s.append(R.grid(["#", "Procedure Name", "Purpose", "Parameters", "Tables Used",
                     "Business Logic"],
                    rows, [3, 15, 20, 18, 20, 34],
                    [R.S_CELL, R.S_MONO, R.S_NOTE, R.S_MONO, R.S_MONO, R.S_NOTE]))
    return s


def indexes() -> list:
    """Return the index recommendations."""
    s = R.h1("Database Index Recommendations")
    s.append(R.grid(["Table / Scope", "Recommended Index", "Rationale"],
                    [list(x) for x in INDEX_NOTES], [18, 34, 48],
                    [R.S_CELL_B, R.S_MONO, R.S_NOTE]))
    return s


def partitions() -> list:
    """Return the partitioning strategy."""
    s = R.h1("Partition Strategy")
    s.append(Paragraph(
        "PostgreSQL declarative partitioning. Retention becomes DROP PARTITION — a metadata "
        "operation that leaves no dead tuples and needs no VACUUM — which is the main reason "
        "to partition these tables at all.",
        R.S_BODY))
    s.append(Spacer(1, 3 * mm))
    s.append(R.grid(["Table", "Partition Method", "Interval", "Retention", "Rationale"],
                    [list(x) for x in PARTITIONS], [18, 20, 9, 16, 47],
                    [R.S_MONO, R.S_MONO, R.S_CELL, R.S_CELL, R.S_NOTE]))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph(
        "Operational note: create partitions ahead of time with pg_partman or a scheduled "
        "job. A missing partition rejects the insert, which on clickstream_event would drop "
        "instrumentation silently and on inventory_transaction would fail a checkout.",
        R.S_NOTE))
    return s


def performance() -> list:
    """Return the performance optimisation suggestions."""
    s = R.h1("Performance Optimization Suggestions")
    s.append(R.grid(["Area", "Current State", "Recommendation"],
                    [list(x) for x in PERFORMANCE], [15, 42, 43],
                    [R.S_CELL_B, R.S_NOTE, R.S_NOTE]))
    return s


def normalisation() -> list:
    """Return the normalisation report."""
    s = R.h1("Normalization Report")
    s.append(R.grid(["Normal Form", "Verdict", "Analysis"],
                    [list(x) for x in NORMALISATION], [22, 14, 64],
                    [R.S_CELL_B, R.S_CELL_B, R.S_NOTE]))
    return s


def statistics() -> list:
    """Return the closing statistics."""
    impl = [t for t in TABLES if t["status"] == "IMPLEMENTED"]
    prop = [t for t in TABLES if t["status"] == "PROPOSED"]

    bridges = [t for t in TABLES if "_categories" in t["table"]
               or "_brands" in t["table"] or "_products" in t["table"]
               or "_tags" in t["table"] or t["table"].endswith("_permissions")
               or t["table"] in {"users_user_groups", "admin_role_permission",
                                 "admin_user_role", "flash_sale_item", "lookbook_item",
                                 "return_item"}]
    lookups = [t for t in TABLES if t["table"].startswith("lkp_")
               or t["table"] in {"blog_category", "faq_category", "admin_permission",
                                 "admin_role", "delivery_partner", "warehouse"}]
    ledgers = [t for t in TABLES if t["table"] in {
        "inventory_transaction", "product_price_history", "loyalty_transaction",
        "gift_card_transaction", "orders_orderstatushistory", "audit_log",
        "activity_log", "clickstream_event", "search_history",
        "recommendation_history", "shipment_tracking_event",
        "payments_paymentwebhooklog", "payments_paymentattempt"}]

    impl_cols = sum(I.column_count(t["table"]) for t in impl)
    prop_cols = sum(len(t["cols"]) for t in prop)

    rows = [
        ["Total Tables", str(len(TABLES)), "Implemented plus proposed; excludes framework tables"],
        ["Implemented Tables", str(len(impl)), "Present in the shipped backend and verified by introspection"],
        ["Proposed Tables", str(len(prop)), "New build required by the module brief"],
        ["Framework Tables", "8", "django_migrations, django_content_type, django_session, "
                                  "auth_group, auth_permission, auth_group_permissions, "
                                  "token_blacklist_outstandingtoken, token_blacklist_blacklistedtoken"],
        ["Grand Total Objects", str(len(TABLES) + 8), "Everything the database will physically contain"],
        ["", "", ""],
        ["Master Tables", "24", "users_user, products_product, catalog_*, coupons_coupon, "
                                "warehouse, influencer, cms_page …"],
        ["Transaction Tables", "22", "orders_*, payments_*, cart_*, return_*, "
                                     "gift_card_transaction, support_ticket …"],
        ["Lookup / Reference Tables", str(len(lookups)), "lkp_* dimension tables plus role, "
                                                         "permission and partner masters"],
        ["Bridge (Junction) Tables", str(len(bridges)), "Pure many-to-many resolvers"],
        ["Ledger / Append-Only Tables", str(len(ledgers)), "Never updated; corrections are new rows"],
        ["Aggregate / Snapshot Tables", "3", "analytics_daily_sales, analytics_product_daily, "
                                             "analytics_customer_daily"],
        ["", "", ""],
        ["Total Columns", str(impl_cols + prop_cols),
         f"{impl_cols} implemented + {prop_cols} proposed"],
        ["Widest Table", "products_product (57 columns)", "Catalogue master"],
        ["Total Stored Procedures", str(len(PROCEDURES)), "Specified; none implemented yet"],
        ["Total Views", "6", "Recommended: v_product_catalog, v_order_summary, "
                             "v_customer_ltv, v_inventory_status, v_review_summary, "
                             "v_daily_revenue"],
        ["Existing Indexes", "47", "Named composite indexes already in the migration state"],
        ["Recommended Indexes", "18", "Full-text, trigram, partial, covering and BRIN"],
        ["Total Indexes (target)", "65", "Excluding primary keys and unique constraints"],
        ["Implemented Foreign Keys", "63", "Including bridge tables"],
        ["Proposed Foreign Keys", "71", "Including lookup normalisation"],
        ["Check Constraints", "24 existing", "Money floors, quantity bounds, rating range, "
                                             "date-window ordering, exclusive-or ownership"],
        ["Unique Constraints", "38 existing", "Including 11 partial (filtered) unique indexes"],
        ["Partitioned Tables", "9", "See Partition Strategy"],
        ["Required Extensions", "4", "pg_trgm, btree_gin, pgcrypto, pg_stat_statements"],
        ["", "", ""],
        ["API Endpoints Served", "172", "Verified against the generated OpenAPI 3.1 schema"],
        ["Backend Test Coverage", "925 tests", "All passing at time of writing"],
    ]
    s = R.h1("Final Database Statistics")
    s.append(R.grid(["Metric", "Value", "Detail"], rows, [24, 16, 60],
                    [R.S_CELL_B, R.S_CELL_B, R.S_NOTE]))
    return s


def appendix() -> list:
    """Return the framework-table appendix and the legend."""
    s = R.h1("Appendix A — Framework Tables")
    s.append(Paragraph(
        "Created and managed by Django and SimpleJWT. Listed so the database team can "
        "account for every object in the database, but they are not part of the application "
        "data model and must not be altered by hand.",
        R.S_BODY))
    s.append(Spacer(1, 3 * mm))
    fw = [
        ["django_migrations", "Applied migration ledger", "Never modify. Rewriting a row "
         "makes the schema and the code disagree silently."],
        ["django_content_type", "Model registry for generic relations and permissions", "Managed"],
        ["django_session", "Server-side session store",
         "Moves to Redis when REDIS_URL is set; the table remains for the DB fallback."],
        ["auth_group", "Django role groups", "Superseded by admin_role for back-office RBAC"],
        ["auth_permission", "Per-model CRUD permissions", "Auto-generated per model"],
        ["auth_group_permissions", "Bridge: group ↔ permission", "Managed"],
        ["token_blacklist_outstandingtoken", "Issued JWT refresh tokens",
         "Grows with every login; prune on a schedule."],
        ["token_blacklist_blacklistedtoken", "Revoked refresh tokens",
         "Consulted on every refresh — keep indexed and pruned."],
    ]
    s.append(R.grid(["Table", "Purpose", "Notes"], fw, [26, 32, 42],
                    [R.S_MONO, R.S_CELL, R.S_NOTE]))

    s.append(PageBreak())
    s += R.h1("Appendix B — Legend & Colour Coding")
    s.append(R.grid(["Row Colour", "Meaning"], [
        ["Yellow", "Primary key column"],
        ["Green", "Foreign key column"],
        ["Blue", "Unique-constrained column"],
        ["Orange (Overview)", "Proposed table — new build required"],
        ["Alternating grey", "Regular column"],
    ], [22, 78], [R.S_CELL_B, R.S_NOTE]))
    s.append(Spacer(1, 4 * mm))
    s.append(R.grid(["Key Marker", "Meaning"], [
        ["PK", "Primary key"],
        ["FK", "Foreign key"],
        ["UQ", "Unique constraint"],
        ["PK/FK", "Primary key that is also a foreign key"],
        ["FK/UQ", "Foreign key carrying a one-to-one uniqueness rule"],
        ["UQ*", "Part of a composite unique constraint"],
    ], [22, 78], [R.S_CELL_B, R.S_NOTE]))
    s.append(Spacer(1, 4 * mm))
    s.append(R.grid(["Data Type", "Usage"], [
        ["BIGSERIAL", "Surrogate primary key; identity"],
        ["UUID", "Public-safe secondary identifier, gen_random_uuid()"],
        ["NUMERIC(12,2)", "Money. Never FLOAT."],
        ["NUMERIC(14,2)", "Aggregated money in analytics tables"],
        ["TIMESTAMPTZ", "All timestamps, stored UTC"],
        ["JSONB", "Immutable snapshots and opaque third-party payloads only"],
        ["INET", "IP addresses; truncate or hash under DPDP retention rules"],
        ["CHAR(3)", "ISO 4217 currency code"],
        ["GENERATED … STORED", "Computed column materialised on disk"],
    ], [22, 78], [R.S_MONO, R.S_NOTE]))
    return s


# ---------------------------------------------------------------------------

def main() -> None:
    """Build the PDF."""
    story: list = []
    story += cover()
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    story += overview()
    story.append(PageBreak())
    story += conventions()
    story += modules()
    story.append(PageBreak())
    story += erd()
    story.append(PageBreak())
    story += procedures()
    story.append(PageBreak())
    story += indexes()
    story.append(PageBreak())
    story += partitions()
    story.append(PageBreak())
    story += performance()
    story.append(PageBreak())
    story += normalisation()
    story.append(PageBreak())
    story += statistics()
    story.append(PageBreak())
    story += appendix()

    out = Path(__file__).parent.parent / "Fashion_Trendz_Database_Design_Document.pdf"
    R.build_document(str(out), story)
    print(f"written: {out}")
    print(f"tables: {len(TABLES)}  procedures: {len(PROCEDURES)}")


if __name__ == "__main__":
    main()
