"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Heart, Sparkles, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MegaMenu } from "@/components/layout/MegaMenu";
import { MobileNav } from "@/components/layout/MobileNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { CartDrawer } from "@/components/cart/CartDrawer";
import { useScroll } from "@/hooks/use-scroll";
import { useWishlist } from "@/context/WishlistContext";
import {
  disableDemoMode,
  enableDemoMode,
  getDemoUser,
  isDemoModeEnabled,
} from "@/lib/demoMode";
import { cn } from "@/lib/utils";

export function Navbar() {
  const scrolled = useScroll();
  const { count: wishlistCount } = useWishlist();
  const [demoOn, setDemoOn] = useState(false);
  const [demoUserName, setDemoUserName] = useState<string | null>(null);

  useEffect(() => {
    setDemoOn(isDemoModeEnabled());
    setDemoUserName(getDemoUser()?.name ?? null);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 bg-background/95 backdrop-blur-sm transition-shadow",
        scrolled ? "shadow-sm" : "border-b border-transparent"
      )}
    >
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <MobileNav />
        <Link
          href="/"
          className="font-heading text-xl font-semibold tracking-tight"
        >
          Fashion Trendz
        </Link>
        <div className="hidden flex-1 md:flex md:justify-center">
          <MegaMenu />
        </div>
        <div className="ml-auto hidden max-w-xs flex-1 md:block">
          <SearchBar />
        </div>
        <div className="ml-auto flex items-center gap-1 md:ml-0">
          <Button
            variant="ghost"
            size="icon"
            className="relative hidden sm:inline-flex"
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
              <Button variant="ghost" size="icon" aria-label="Account">
                <User />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {demoUserName ? (
                <DropdownMenuLabel>Hi, {demoUserName}</DropdownMenuLabel>
              ) : (
                <DropdownMenuItem asChild>
                  <Link href="/account/login">Login</Link>
                </DropdownMenuItem>
              )}
              <DropdownMenuItem asChild>
                <Link href="/account">My Account</Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/orders">Orders</Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => (demoOn ? disableDemoMode() : enableDemoMode())}
              >
                <Sparkles className="text-accent" />
                {demoOn ? "Disable Demo Mode" : "Enable Demo Mode"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <CartDrawer />
        </div>
      </div>
    </header>
  );
}
