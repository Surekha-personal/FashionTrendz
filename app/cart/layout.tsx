import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Your Bag | Fashion Trendz",
  description: "Review the items in your Fashion Trendz shopping bag.",
  robots: { index: false, follow: true },
};

export default function CartLayout({ children }: { children: React.ReactNode }) {
  return children;
}
