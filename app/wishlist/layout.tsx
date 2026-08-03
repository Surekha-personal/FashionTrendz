import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "My Wishlist | Fashion Trendz",
  description: "Products you've saved to shop later on Fashion Trendz.",
  robots: { index: false, follow: true },
};

export default function WishlistLayout({ children }: { children: React.ReactNode }) {
  return children;
}
