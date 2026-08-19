import Link from "next/link";
import { Separator } from "@/components/ui/separator";
import { NewsletterForm } from "@/components/forms/NewsletterForm";

// Every href below resolves to a real route already in this app — no
// placeholder "coming soon" destinations, per the no-invented-links rule.
const footerColumns = [
  {
    heading: "Shop",
    links: [
      { label: "Women", href: "/women" },
      { label: "Men", href: "/men" },
      { label: "Kids", href: "/kids" },
      { label: "New In", href: "/new-in" },
      { label: "Sale", href: "/sale" },
    ],
  },
  {
    heading: "Shopping",
    links: [
      { label: "Search", href: "/search" },
      { label: "My Bag", href: "/cart" },
      { label: "My Wishlist", href: "/wishlist" },
      { label: "Track Orders", href: "/orders" },
    ],
  },
  {
    heading: "Account",
    links: [
      { label: "Sign In", href: "/login" },
      { label: "Create Account", href: "/register" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="mt-16 border-t bg-background">
      <div className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div className="flex flex-col gap-3">
            <span className="font-heading text-xl font-semibold">
              Fashion Trendz
            </span>
            <p className="max-w-xs text-sm text-muted-foreground">
              Premium fashion, footwear and accessories curated for the way you live.
            </p>
            <NewsletterForm className="mt-2 max-w-sm" />
          </div>
          {footerColumns.map((column) => (
            <div key={column.heading} className="flex flex-col gap-3">
              <span className="text-sm font-semibold">{column.heading}</span>
              <ul className="flex flex-col gap-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-muted-foreground hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <span className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} Fashion Trendz. All rights reserved.{" "}
            <Link href="/admin" className="underline hover:text-foreground">
              Admin Preview
            </Link>
          </span>
          <div className="flex items-center gap-4 text-xs font-medium text-muted-foreground">
            <Link href="https://instagram.com" className="hover:text-foreground">
              Instagram
            </Link>
            <Link href="https://twitter.com" className="hover:text-foreground">
              Twitter
            </Link>
            <Link href="https://facebook.com" className="hover:text-foreground">
              Facebook
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
