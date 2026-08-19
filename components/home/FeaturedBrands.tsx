"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, staggerContainer, viewportOnce } from "@/lib/motion";
import type { Brand } from "@/types/home";

export function FeaturedBrands({ brands }: { brands: Brand[] }) {
  if (brands.length === 0) return null;

  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="Handpicked"
        title="Featured Brands"
        subtitle="In-house and partner labels known for craft over trend cycles."
        align="center"
      />
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
      >
        {brands.map((brand) => (
          <motion.div key={brand.id} variants={fadeInUp}>
            <Link
              href={brand.href}
              className="group flex h-24 flex-col items-center justify-center gap-2 rounded-2xl border border-border bg-card px-4 shadow-sm transition-all hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg sm:h-28"
            >
              {brand.logo ? (
                <span className="relative h-9 w-full sm:h-10">
                  <Image
                    src={brand.logo}
                    alt={brand.name}
                    fill
                    sizes="140px"
                    className="object-contain grayscale transition-all duration-200 group-hover:grayscale-0"
                  />
                </span>
              ) : (
                <span className="font-heading text-center text-base font-medium text-foreground/80 transition-colors group-hover:text-accent sm:text-lg">
                  {brand.name}
                </span>
              )}
            </Link>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
