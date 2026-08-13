# Seed assets — for the content team

Drop real fashion photography into these folders and run the seed command.
No code changes, no manifest required.

Nothing in this folder is written to the database as a path or URL. The seed
copies each file into `MEDIA_ROOT` through Django's normal upload machinery, so
the API returns exactly the image URLs it always has and the frontend needs no
change.

---

## Option A — just drop files in folders (easiest)

```
seed_assets/
├── products/
│   ├── _default/          ← used when a subcategory folder is empty
│   ├── dresses/           ← folder name = SUBCATEGORY SLUG
│   ├── shirts/
│   ├── kurta-sets/
│   ├── sneakers/
│   └── …
├── banners/
│   ├── hero/              ← wide, 2400×800 or similar
│   ├── strip/
│   ├── category/
│   └── sale/
├── brands/                ← logos
├── categories/            ← category tiles and banners
└── reviews/               ← customer-photo style shots
```

The folder name must match the **subcategory slug**. To see the exact list your
database expects:

```bash
python manage.py seed_products --list-asset-folders
```

Anything not covered falls back to `products/_default/`. Five or six images in
`_default` is enough to seed a browsable catalogue.

**Accepted formats:** `.jpg` `.jpeg` `.png` `.webp` `.avif`

**Product images** should be portrait, at least **400 × 600** — that floor is
enforced by `validate_product_image` and anything smaller is rejected.
**Banner images** need at least **1200 × 300**.

Selection is deterministic: a given SKU always picks the same photograph from a
folder, so re-running the seed does not reshuffle the catalogue's appearance.

---

## Option B — a manifest (when the shoot is already catalogued)

Rename one of the examples and edit it:

```bash
cp seed_assets/manifest.example.json seed_assets/manifest.json
#  or
cp seed_assets/manifest.example.csv  seed_assets/manifest.csv
```

JSON wins if both exist. A manifest takes priority over the folder scan for any
SKU it names; products it does not name fall back to folders.

### JSON

```json
{
  "FT-000001": [
    "products/dresses/midi-front.jpg",
    "products/dresses/midi-back.jpg"
  ]
}
```

Also accepts the verbose export shape:

```json
{"products": [{"sku": "FT-000001", "images": ["a.jpg", "b.jpg"]}]}
```

### CSV

One row per image — a spreadsheet is what people actually use, and quoting a
list inside a single cell is where those exports go wrong.

```csv
sku,image,display_order
FT-000001,products/dresses/midi-front.jpg,0
FT-000001,products/dresses/midi-back.jpg,1
```

`slug` works in place of `sku` in either format.

### Remote URLs

`http://` and `https://` entries are supported but **downloaded only with an
explicit flag**:

```bash
python manage.py seed_products --fetch-remote
```

Off by default because a seed that reaches the network fails on an air-gapped CI
box and makes the fixture depend on someone else's uptime. Downloads are capped
at 12 MB per file.

---

## Running it

```bash
python manage.py seed_everything                  # the whole catalogue
python manage.py seed_products --count 500        # products only
python manage.py seed_banners                     # banners only
```

Point at a different library without moving files:

```bash
python manage.py seed_products --assets-dir /mnt/photography/spring26
```

or set `SEED_ASSETS_DIR` in `.env`.

---

## What happens with no images

Rows are still created; the image field is left empty and the command prints
which folders it looked in. It does **not** invent a placeholder — a catalogue
with visibly missing photography is a problem someone fixes, whereas one full of
grey rectangles is one everybody learns to ignore.

If you genuinely want generated stand-ins for a demo, ask for them explicitly:

```bash
python manage.py seed_products --generate-placeholders
```

---

## Checklist

- [ ] Images are portrait for products, landscape for banners
- [ ] Product shots clear 400 × 600; banners clear 1200 × 300
- [ ] Folder names match subcategory slugs (`--list-asset-folders`)
- [ ] `_default/` has at least six images as a safety net
- [ ] Files are under ~2 MB each — these are copied into `MEDIA_ROOT`
- [ ] You have the right to use every image
