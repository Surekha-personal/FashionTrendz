"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { luxuryBanners } from "@/data/editorial";

export function LuxuryCollection() {
  return (
    <section className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-16 sm:px-6 lg:px-8">
      {luxuryBanners.map((banner, index) => (
        <motion.div
          key={banner.id}
          variants={fadeInUp}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
          className={cn(
            "relative flex min-h-[420px] items-center overflow-hidden rounded-3xl",
            index % 2 === 1 && "sm:justify-end"
          )}
        >
          <Image
            src={banner.image}
            alt={banner.imageAlt}
            fill
            sizes="100vw"
            className="object-cover"
          />
          <div
            className={cn(
              "absolute inset-0 bg-gradient-to-r from-black/70 via-black/25 to-transparent",
              index % 2 === 1 && "bg-gradient-to-l"
            )}
          />
          <div className="relative flex max-w-md flex-col gap-3 p-8 text-white sm:p-12">
            <span className="text-xs font-semibold tracking-[0.25em] text-white/80 uppercase">
              {banner.eyebrow}
            </span>
            <h2 className="font-heading text-3xl font-semibold sm:text-4xl">
              {banner.title}
            </h2>
            <p className="text-sm text-white/85 sm:text-base">
              {banner.description}
            </p>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="mt-2 w-fit rounded-full border-white bg-transparent text-white hover:bg-white hover:text-primary"
            >
              <Link href={banner.ctaHref}>{banner.ctaLabel}</Link>
            </Button>
          </div>
        </motion.div>
      ))}
    </section>
  );
}
