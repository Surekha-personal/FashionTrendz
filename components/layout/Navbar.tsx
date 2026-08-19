"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Heart, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MegaMenu } from "@/components/layout/MegaMenu";
import { MobileNav } from "@/components/layout/MobileNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { CartDrawer } from "@/components/cart/CartDrawer";
import { useScroll } from "@/hooks/use-scroll";
import { useAuth } from "@/context/AuthContext";
import { useWishlist } from "@/context/WishlistContext";
import { cn } from "@/lib/utils";

export function Navbar() {
  const scrolled = useScroll();
  const { count: wishlistCount } = useWishlist();
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <header
      className={cn(
        "sticky top-0 z-40 bg-background/95 backdrop-blur-sm transition-shadow duration-200",
        scrolled ? "shadow-sm" : "border-b border-transparent"
      )}
    >
      <div className="mx-auto flex max-w-7xl items-center gap-5 px-4 py-4 sm:px-6 lg:px-8">
        <MobileNav />
        <Link
          href="/"
          className="font-heading text-xl font-semibold tracking-tight transition-opacity hover:opacity-80 sm:text-2xl"
        >
          Fashion Trendz
        </Link>
        {/* The mega menu lists every category (9 + Sale) as its own trigger,
            which is too dense to share a row with the search bar below
            ~1024px — tablets fall back to the mobile drawer nav instead of
            a cramped desktop bar. */}
        <div className="hidden flex-1 lg:flex lg:justify-center">
          <MegaMenu />
        </div>
        {/* The search input is a single flexible-width field (unlike the
            dense mega menu), so it can safely come back a breakpoint
            earlier than the category nav — tablets get a real search box
            instead of just a hamburger and empty space. */}
        <div className="ml-auto hidden max-w-md flex-1 md:block">
          <SearchBar />
        </div>
        <div className="ml-auto flex items-center gap-0.5 md:ml-0">
          <Button
            variant="ghost"
            size="icon"
            className="relative hidden transition-colors hover:text-accent sm:inline-flex"
            asChild
          >
            <Link href="/wishlist" aria-label="Wishlist">
              <Heart />
              <AnimatePresence>
                {wishlistCount > 0 && (
                  <motion.span
                    key={wishlistCount}
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    transition={{ type: "spring", stiffness: 500, damping: 20 }}
                    className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-accent text-[10px] font-medium text-accent-foreground"
                  >
                    {wishlistCount}
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Account"
                className="transition-colors hover:text-accent"
              >
                <User />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {isAuthenticated ? (
                <DropdownMenuLabel>Hi, {user?.first_name || user?.email}</DropdownMenuLabel>
              ) : (
                <DropdownMenuItem asChild>
                  <Link href="/login">Login</Link>
                </DropdownMenuItem>
              )}
              <DropdownMenuItem asChild>
                <Link href="/orders">Orders</Link>
              </DropdownMenuItem>
              {isAuthenticated && (
                <DropdownMenuItem onSelect={() => logout()}>Logout</DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <CartDrawer />
        </div>
      </div>
    </header>
  );
}
