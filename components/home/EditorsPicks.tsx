"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, staggerContainer, viewportOnce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { editorsPicks } from "@/data/editorial";

export function EditorsPicks() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="From The Magazine"
        title="Editor's Picks"
        subtitle="Style stories from our editorial desk, updated weekly."
      />
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="grid grid-cols-1 gap-6 sm:grid-cols-2"
      >
        {editorsPicks.map((pick, index) => (
          <motion.div
            key={pick.id}
            variants={fadeInUp}
            className={cn(index === 0 && "sm:col-span-2")}
          >
            <Link
              href={pick.ctaHref}
              className={cn(
                "group relative flex w-full overflow-hidden rounded-2xl bg-muted shadow-sm transition-shadow hover:shadow-xl",
                index === 0 ? "aspect-[16/9]" : "aspect-[4/5]"
              )}
            >
              <Image
                src={pick.image}
                alt={pick.imageAlt}
                fill
                sizes={index === 0 ? "100vw" : "(min-width: 640px) 50vw, 100vw"}
                className="object-cover transition-transform duration-500 group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
              <div className="relative mt-auto flex max-w-md flex-col gap-2 p-6 text-white">
                <span className="text-xs font-semibold tracking-[0.2em] text-white/80 uppercase">
                  {pick.eyebrow}
                </span>
                <h3 className="font-heading text-xl font-semibold sm:text-2xl">
                  {pick.title}
                </h3>
                <p className="text-sm text-white/85">{pick.description}</p>
                <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium">
                  {pick.ctaLabel}
                  <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
                </span>
              </div>
            </Link>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
