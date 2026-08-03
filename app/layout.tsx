import type { Metadata } from "next";
import { Inter, Playfair_Display, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { BackToTop } from "@/components/common/BackToTop";
import { DemoModeBadge } from "@/components/common/DemoModeBadge";
import { ShopProviders } from "@/context/ShopProviders";
import "./globals.css";

const bodyFont = Inter({
  variable: "--font-body",
  subsets: ["latin"],
});

const headingFont = Playfair_Display({
  variable: "--font-heading",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const siteDescription =
  "Fashion Trendz is a premium fashion destination for clothing, footwear, and accessories.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Fashion Trendz | Premium Fashion, Curated for You",
    template: "%s",
  },
  description: siteDescription,
  keywords: [
    "Fashion Trendz",
    "premium fashion",
    "online clothing store",
    "ecommerce fashion",
    "footwear",
    "accessories",
  ],
  openGraph: {
    type: "website",
    siteName: "Fashion Trendz",
    title: "Fashion Trendz | Premium Fashion, Curated for You",
    description: siteDescription,
    url: siteUrl,
  },
  twitter: {
    card: "summary_large_image",
    title: "Fashion Trendz | Premium Fashion, Curated for You",
    description: siteDescription,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${bodyFont.variable} ${headingFont.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ShopProviders>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
          <Toaster />
          <BackToTop />
          <DemoModeBadge />
        </ShopProviders>
      </body>
    </html>
  );
}
