"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Compass, Home, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/components/layout/SearchBar";
import { fadeInUp, viewportOnce } from "@/lib/motion";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center px-4 py-16 text-center">
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="flex flex-col items-center gap-6"
      >
        <motion.div
          initial={{ scale: 0.6, opacity: 0, rotate: -8 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 16 }}
          className="flex size-24 items-center justify-center rounded-full bg-muted"
        >
          <SearchX className="size-10 text-muted-foreground" />
        </motion.div>
        <div className="flex flex-col gap-2">
          <span className="font-heading text-6xl font-semibold text-foreground/90">
            404
          </span>
          <h1 className="font-heading text-xl font-semibold">Page Not Found</h1>
          <p className="text-sm text-muted-foreground">
            The page you&apos;re looking for may have been moved or doesn&apos;t
            exist. Let&apos;s get you back on track.
          </p>
        </div>
        <SearchBar className="w-full max-w-sm" />
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button asChild>
            <Link href="/">
              <Home className="size-4" />
              Back to Home
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/women">
              <Compass className="size-4" />
              Explore Collections
            </Link>
          </Button>
        </div>
      </motion.div>
    </div>
  );
}
