"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, staggerContainer, viewportOnce } from "@/lib/motion";
import type { Category } from "@/types/home";

export function ShopByCategory({ categories }: { categories: Category[] }) {
  if (categories.length === 0) return null;

  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="Curated For You"
        title="Shop By Category"
        subtitle="Explore edits designed around the way you actually shop."
      />
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-3 xl:grid-cols-3"
      >
        {categories.map((category, index) => (
          <motion.div
            key={category.id}
            variants={fadeInUp}
            className={index === 0 ? "col-span-2 sm:col-span-1" : undefined}
          >
            <Link
              href={category.href}
              className="group relative flex aspect-square w-full overflow-hidden rounded-2xl bg-muted shadow-sm transition-shadow hover:shadow-xl"
            >
              <Image
                src={category.image}
                alt={category.imageAlt}
                fill
                sizes="(min-width: 1024px) 30vw, (min-width: 640px) 33vw, 50vw"
                className="object-cover transition-transform duration-500 group-hover:scale-110"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/5 to-transparent" />
              <div className="relative mt-auto flex w-full items-center justify-between p-4 text-white">
                <span className="font-heading text-lg font-semibold sm:text-xl">
                  {category.name}
                </span>
                <span className="flex size-8 items-center justify-center rounded-full bg-white/20 backdrop-blur-sm transition-transform group-hover:translate-x-1 group-hover:-translate-y-1">
                  <ArrowUpRight className="size-4" />
                </span>
              </div>
            </Link>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
