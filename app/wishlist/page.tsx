"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Heart } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { WishlistCard } from "@/components/wishlist/WishlistCard";
import { EmptyState } from "@/components/common/EmptyState";
import { useWishlist } from "@/context/WishlistContext";
import { fadeInUp, staggerContainer } from "@/lib/motion";

export default function WishlistPage() {
  const { items, count, hydrated } = useWishlist();

  if (!hydrated) return null;

  const recentFirst = [...items].sort((a, b) => b.addedAt - a.addedAt);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">Home</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Wishlist</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <h1 className="mb-6 font-heading text-2xl font-semibold sm:text-3xl">
        My Wishlist {count > 0 && `(${count})`}
      </h1>

      {recentFirst.length === 0 ? (
        <EmptyState
          icon={Heart}
          title="Your wishlist is empty"
          description="Save your favorite pieces to shop them later."
          action={
            <Button asChild>
              <Link href="/">Explore Products</Link>
            </Button>
          }
        />
      ) : (
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-6 xl:grid-cols-4"
        >
          <AnimatePresence>
            {recentFirst.map((item) => (
              <motion.div key={item.productId} variants={fadeInUp}>
                <WishlistCard item={item} />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  );
}
