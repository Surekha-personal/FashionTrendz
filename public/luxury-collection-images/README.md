# The Luxury Collection — image sources

Local cover photos for the homepage "The Luxury Collection" editorial banners.
All sourced from Unsplash (free to use under the Unsplash License). Downloaded
via the photographer's original file, then cropped to a wide 1600x900 (16:9)
landscape frame — matching the wide `min-h-[420px]` cards in
`components/home/LuxuryCollection.tsx` which render the image with
`object-cover` — and re-encoded as quality-82 JPEG.

Images were chosen to avoid visible brand logos/wordmarks, watermarks, large
text, and overly crowded or risqué compositions, per the site's premium
fashion-editorial tone.

| Brand slug         | Local file              | Photographer          | Unsplash URL |
|---------------------|--------------------------|------------------------|--------------|
| aarohi-couture      | `aarohi-couture.jpg`     | Prateek Jaiswal        | https://unsplash.com/photos/a-woman-in-a-red-and-gold-bridal-outfit-zDWSlcSWOJc |
| casa-marbella       | `casa-marbella.jpg`      | Ola Szkolda            | https://unsplash.com/photos/elegant-woman-in-patterned-dress-and-coat-in-ornate-room-SXPTn6LCdlw |
| roux-atelier        | `roux-atelier.jpg`       | Vitaly Gariev          | https://unsplash.com/photos/a-fashion-designer-works-on-a-dress-form-_kLATTS2-oQ |
| lumiere-blanc       | `lumiere-blanc.jpg`      | Alex Roosso            | https://unsplash.com/photos/woman-in-white-outfit-posing-on-a-white-stool-alQXpeVVVaA |
| marchetti-pelle     | `marchetti-pelle.jpg`    | Cohen Berg             | https://unsplash.com/photos/person-tracing-leather-pattern-with-pen-GPdWubhjq-Q |
| tessuto-nero        | `tessuto-nero.jpg`       | Mokhalad Musavi        | https://unsplash.com/photos/woman-in-elegant-black-dress-seated-in-ornate-chair-n_3CrZr2_fc |
| anara-jewels        | `anara-jewels.jpg`       | Prateek Saxena         | https://unsplash.com/photos/a-woman-wears-jewelry-and-looks-directly-at-you-Y3WEAlwC8DE |
| odeon-timepieces    | `odeon-timepieces.jpg`   | Mdreza Jalali          | https://unsplash.com/photos/antique-gold-pocket-watch-on-display-stand-d6Gfvddn8oI |
| ravenna-rossi       | `ravenna-rossi.jpg`      | Mike Lloyd             | https://unsplash.com/photos/woman-in-red-sleeveless-dress-standing-on-stairs-PAbWftgJ7dg |
| alto-firenze        | `alto-firenze.jpg`       | Juan Carlos Pavon      | https://unsplash.com/photos/young-woman-with-hand-in-hair-outdoors-QxtaKgeiBTs |
| palazzo-verde       | `palazzo-verde.jpg`      | Mokhalad Musavi        | https://unsplash.com/photos/woman-with-curly-hair-in-ornate-room-yehc-RoynvI |
| auric-atelier       | `auric-atelier.jpg`      | Naeem Ad               | https://unsplash.com/photos/a-woman-in-elegant-attire-looks-out-a-window-YPHIg9uDJno |

License: [Unsplash License](https://unsplash.com/license) — free for commercial
and non-commercial use, no permission or attribution required (attribution
given above as courtesy).

## Slug assumption

These slugs (`aarohi-couture`, `casa-marbella`, etc.) were predicted from the
brand names shown on the homepage using the same slugify convention as
`django.utils.text.slugify` (lowercase, accents stripped, spaces → hyphens).
The live `/brands/luxury/` backend endpoint is not reachable from this
environment, so the actual `ApiBrand.slug` values returned by the backend
could not be directly verified — confirm they match before relying on this
mapping, and add/adjust entries in `LUXURY_COLLECTION_IMAGES`
(`lib/apiAdapters.ts`) if any differ.
