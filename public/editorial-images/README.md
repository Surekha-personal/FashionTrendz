# Editor's Picks — image sources

Local cover photos for the homepage "Editor's Picks" cards
(`components/home/EditorsPicks.tsx`). All sourced from Unsplash (free to use
under the Unsplash License), downloaded via the photographer's original
file, then re-encoded as quality-82 JPEG.

Card aspect ratios are preserved from the existing component: the first
card ("Editor's Picks") renders `aspect-[16/9]` and spans both grid
columns, the remaining cards render `aspect-[4/5]`.

| Collection slug       | Local file                  | Crop      | Photographer       | Unsplash URL |
|------------------------|-------------------------------|-----------|---------------------|--------------|
| editors-picks          | `editors-picks.jpg`          | 1600x900  | Vitaly Gariev       | https://unsplash.com/photos/model-posing-for-photographer-in-studio-setting-MfNVQxUAZB0 |
| workwear-edit          | `workwear-edit.jpg`          | 1200x1500 | Nassim Boughazi     | https://unsplash.com/photos/woman-in-black-blazer-and-black-pants-standing-on-road-during-daytime-dodzmVtjoKs |
| statement-jewellery    | `statement-jewellery.jpg`    | 1200x1500 | Apostolos Vamvouras | https://unsplash.com/photos/a-woman-wearing-a-black-shirt-and-gold-earrings-XUBJb1TR3DM |

License: [Unsplash License](https://unsplash.com/license) — free for commercial
and non-commercial use, no permission or attribution required (attribution
given above as courtesy).

## Slug source

Unlike the category/luxury batches, these three slugs were not predicted —
they were read directly from a cached response of the live
`/collections/editors-picks/` endpoint (found in `.next_old/cache/`), which
confirmed exactly 3 editorial entries exist (`pagination.count: 3`):
Editor's Picks (`editors-picks`), Workwear Edit (`workwear-edit`), and
Statement Jewellery (`statement-jewellery`). No other editorial cards are
currently defined in the backend.
