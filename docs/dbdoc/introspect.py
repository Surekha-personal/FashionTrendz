"""Turns the Django introspection dump into documentation rows.

The 41 implemented tables are described from ``schema.json``, which was
produced by walking Django's model metadata against the live migration state.
Transcribing four hundred columns by hand would guarantee drift between the
document and the database; deriving them guarantees the opposite.

Only the prose — purpose, relationships, consuming APIs and frontend pages —
is authored by hand, in ``spec.py``.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

HERE = pathlib.Path(__file__).parent
SCHEMA = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))

BY_TABLE: dict[str, dict[str, Any]] = {t["table"]: t for t in SCHEMA}

# Django creates many-to-many bridge tables implicitly, so they carry no model
# and do not appear in the introspection dump. Their shape is fixed by the ORM:
# a surrogate key and the two foreign keys, unique together.
BRIDGE_SPEC: dict[str, tuple[str, str, str, str]] = {
    "users_user_groups": ("user_id", "users_user", "group_id", "auth_group"),
    "users_user_user_permissions": (
        "user_id", "users_user", "permission_id", "auth_permission"),
    "catalog_brand_categories": (
        "brand_id", "catalog_brand", "category_id", "catalog_category"),
    "catalog_collection_categories": (
        "collection_id", "catalog_collection", "category_id", "catalog_category"),
    "products_product_tags": (
        "product_id", "products_product", "producttag_id", "products_producttag"),
    "coupons_coupon_categories": (
        "coupon_id", "coupons_coupon", "category_id", "catalog_category"),
    "coupons_coupon_brands": ("coupon_id", "coupons_coupon", "brand_id", "catalog_brand"),
    "coupons_coupon_products": (
        "coupon_id", "coupons_coupon", "product_id", "products_product"),
}


def _bridge_rows(name: str) -> list[list[str]]:
    """Return the three columns of an implicit many-to-many bridge table."""
    lcol, ltab, rcol, rtab = BRIDGE_SPEC[name]
    return [
        ["id", "BIGSERIAL", "NOT NULL", "identity", "PK", "", "Surrogate key"],
        [lcol, "BIGINT", "NOT NULL", "", "FK/UQ*", ltab,
         "ON DELETE CASCADE; composite UQ with the other side"],
        [rcol, "BIGINT", "NOT NULL", "", "FK/UQ*", rtab,
         "ON DELETE CASCADE; composite UQ with the other side"],
    ]


def _bridge_constraints(name: str) -> list[list[str]]:
    """Return the constraint rows for an implicit bridge table."""
    lcol, ltab, rcol, rtab = BRIDGE_SPEC[name]
    return [
        ["PRIMARY KEY", f"pk_{name}", "id", "Surrogate identity key."],
        ["UNIQUE", f"uq_{name}", f"{lcol}, {rcol}",
         "One row per pair — the relationship itself carries no attributes."],
        ["FOREIGN KEY", f"fk_{name}_{lcol}", lcol,
         f"REFERENCES {ltab}(id) ON DELETE CASCADE ON UPDATE CASCADE"],
        ["FOREIGN KEY", f"fk_{name}_{rcol}", rcol,
         f"REFERENCES {rtab}(id) ON DELETE CASCADE ON UPDATE CASCADE"],
        ["INDEX", f"idx_{name}_{rcol}", rcol,
         "Reverse traversal; the composite UQ already covers the forward direction."],
    ]

# Django internal type -> PostgreSQL type.
PG: dict[str, str] = {
    "BigAutoField": "BIGSERIAL",
    "AutoField": "SERIAL",
    "BigIntegerField": "BIGINT",
    "IntegerField": "INTEGER",
    "PositiveIntegerField": "INTEGER",
    "PositiveSmallIntegerField": "SMALLINT",
    "SmallIntegerField": "SMALLINT",
    "BooleanField": "BOOLEAN",
    "DateTimeField": "TIMESTAMPTZ",
    "DateField": "DATE",
    "TextField": "TEXT",
    "JSONField": "JSONB",
    "UUIDField": "UUID",
    "FloatField": "DOUBLE PRECISION",
    "ForeignKey": "BIGINT",
    "OneToOneField": "BIGINT",
    "FileField": "VARCHAR(100)",
    "ImageField": "VARCHAR(100)",
}

# Columns every table inherits from the BaseModel mixin. Documented once in
# the conventions section rather than repeated on 41 grids.
INHERITED = {"created_at", "updated_at"}


def pg_type(f: dict[str, Any]) -> str:
    """Return the PostgreSQL column type for an introspected field."""
    t = f["type"]
    if t in ("CharField", "SlugField", "EmailField"):
        return f"VARCHAR({f.get('max_length', 255)})"
    if t == "DecimalField":
        return f"NUMERIC({f['max_digits']},{f['decimal_places']})"
    if t == "TextField" and f.get("max_length"):
        return "TEXT"
    return PG.get(t, t.upper())


def _default(f: dict[str, Any]) -> str:
    """Return a readable DEFAULT clause."""
    if f["type"] == "BigAutoField":
        return "identity"
    if "default" not in f:
        return ""
    d = str(f["default"])
    if d == "True":
        return "TRUE"
    if d == "False":
        return "FALSE"
    if d == "{}":
        return "'{}'::jsonb"
    if re.fullmatch(r"[0-9a-f-]{36}", d):
        return "gen_random_uuid()"
    if re.match(r"\d{4}-\d{2}-\d{2}", d):
        return "now()"
    if d == "":
        return "''"
    return d


def _key(f: dict[str, Any]) -> str:
    """Return the PK/FK/UQ marker for the Key column."""
    marks = []
    if f["pk"]:
        marks.append("PK")
    if f.get("fk"):
        marks.append("FK")
    if f["unique"] and not f["pk"]:
        marks.append("UQ")
    return "/".join(marks)


def _notes(f: dict[str, Any], table: dict[str, Any]) -> str:
    """Return the Notes cell: choices, cascade rule, index membership."""
    bits: list[str] = []

    if f.get("choices"):
        vals = [str(c) for c in f["choices"]]
        joined = " | ".join(vals)
        bits.append(joined if len(joined) <= 92 else joined[:89] + "…")

    if f.get("fk") and f.get("on_delete"):
        bits.append(f"ON DELETE {f['on_delete'].replace('_', ' ')}")

    if f.get("o2o"):
        bits.append("one-to-one")

    if f["col"] in INHERITED:
        bits.append("auto-maintained")

    named = [i["name"] for i in table["indexes"]
             if any(x.lstrip("-") == f["name"] for x in i["fields"])]
    if named:
        bits.append("idx: " + ", ".join(named[:2]))
    elif f.get("db_index") and not f["pk"] and not f["unique"]:
        bits.append("B-tree index")

    return "; ".join(bits)


def columns(table_name: str) -> list[list[str]]:
    """Return documentation rows for one implemented table."""
    if table_name in BRIDGE_SPEC:
        return _bridge_rows(table_name)
    t = BY_TABLE[table_name]
    rows = []
    for f in t["fields"]:
        if f["type"] == "ManyToManyField":
            continue  # bridge tables are documented on their own
        rows.append([
            f["col"],
            pg_type(f),
            "NULL" if f["null"] else "NOT NULL",
            _default(f),
            _key(f),
            f.get("fk", ""),
            _notes(f, t),
        ])
    return rows


def shading(table_name: str) -> dict[int, Any]:
    """Return row-index -> colour, tinting PK and FK rows like the reference."""
    from render import FK_BG, PK_BG, UQ_BG

    if table_name in BRIDGE_SPEC:
        return {1: PK_BG, 2: FK_BG, 3: FK_BG}

    t = BY_TABLE[table_name]
    out: dict[int, Any] = {}
    idx = 0
    for f in t["fields"]:
        if f["type"] == "ManyToManyField":
            continue
        idx += 1
        if f["pk"]:
            out[idx] = PK_BG
        elif f.get("fk"):
            out[idx] = FK_BG
        elif f["unique"]:
            out[idx] = UQ_BG
    return out


def _readable_constraint(detail: str, name: str) -> str:
    """Turn a Django constraint repr into something a DBA can read."""
    d = detail
    d = re.sub(r"<(Check|Unique)Constraint: ", "", d).rstrip(">")
    d = d.replace("condition=", "").replace("fields=", "COLUMNS ")
    d = d.replace("(AND: ", "(").replace("(OR: ", "(")
    d = d.replace("__gte", " >= ").replace("__lte", " <= ")
    d = d.replace("__gt", " > ").replace("__lt", " < ")
    d = d.replace("__isnull", " IS NULL ")
    d = re.sub(r"name='[^']*'", "", d)
    d = re.sub(r"\s+", " ", d).strip().strip(",")
    return d


def constraints(table_name: str) -> list[list[str]]:
    """Return the constraint rows: PK, UQ, CK, FK and named indexes."""
    if table_name in BRIDGE_SPEC:
        return _bridge_constraints(table_name)
    t = BY_TABLE[table_name]
    rows: list[list[str]] = []

    pk = next((f["col"] for f in t["fields"] if f["pk"]), "id")
    rows.append(["PRIMARY KEY", f"pk_{table_name}", pk, "Surrogate identity key."])

    for f in t["fields"]:
        if f["unique"] and not f["pk"]:
            rows.append(["UNIQUE", f"uq_{table_name}_{f['col']}", f["col"],
                         "Column-level uniqueness."])

    for c in t["constraints"]:
        kind = "CHECK" if c["cls"] == "CheckConstraint" else "UNIQUE"
        rows.append([kind, c["name"], "", _readable_constraint(c["detail"], c["name"])])

    for f in t["fields"]:
        if f.get("fk"):
            rows.append([
                "FOREIGN KEY", f"fk_{table_name}_{f['col']}", f["col"],
                f"REFERENCES {f['fk']}(id) ON DELETE "
                f"{(f.get('on_delete') or 'CASCADE').replace('_', ' ')} ON UPDATE CASCADE",
            ])

    for i in t["indexes"]:
        cols = ", ".join(
            f"{c.lstrip('-')}{' DESC' if c.startswith('-') else ''}" for c in i["fields"]
        )
        rows.append(["INDEX", i["name"], cols, "Composite B-tree."])

    return rows


def ordering(table_name: str) -> str:
    """Return the model's default ordering, as a human sentence."""
    if table_name in BRIDGE_SPEC:
        return "None (unordered)."
    o = BY_TABLE[table_name]["ordering"]
    if not o:
        return "None (unordered)."
    return ", ".join(f"{c.lstrip('-')} {'DESC' if c.startswith('-') else 'ASC'}" for c in o)


def column_count(table_name: str) -> int:
    """Return how many physical columns a table has."""
    return len(columns(table_name))
