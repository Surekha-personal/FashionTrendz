# Fashion Trendz

Premium fashion ecommerce frontend — Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui (Radix), Framer Motion, React Hook Form + Zod, Embla Carousel.

## Getting Started

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Structure

- `app/` — routes (App Router)
- `components/ui` — shadcn primitives
- `components/layout` — Navbar, AnnouncementBar, MegaMenu, MobileNav, SearchBar, Footer, Header
- `components/common` — Modal, LoadingSpinner
- `components/product` — ProductCard, ProductCardSkeleton
- `components/cart` — CartDrawer
- `components/forms` — NewsletterForm
- `components/home`, `components/account` — reserved for upcoming phases
- `hooks/`, `lib/`, `utils/`, `types/`, `data/`, `styles/` — shared app code

Brand theme (colors, radius, fonts) is set in `app/globals.css`.
