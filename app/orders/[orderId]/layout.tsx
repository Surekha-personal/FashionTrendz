import type { Metadata } from "next";

interface LayoutProps {
  children: React.ReactNode;
  params: Promise<{ orderId: string }>;
}

export async function generateMetadata({ params }: LayoutProps): Promise<Metadata> {
  const { orderId } = await params;
  return {
    title: `Order ${orderId} | Fashion Trendz`,
    robots: { index: false, follow: true },
  };
}

export default function OrderDetailLayout({ children }: LayoutProps) {
  return children;
}
