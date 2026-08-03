import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "My Orders | Fashion Trendz",
  description: "Track and review your Fashion Trendz order history.",
  robots: { index: false, follow: true },
};

export default function OrdersLayout({ children }: { children: React.ReactNode }) {
  return children;
}
