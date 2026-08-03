"use client";

import Image from "next/image";
import { motion } from "framer-motion";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { inspirationImages } from "@/data/inspiration";

export function FashionInspiration() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="Get Inspired"
        title="Fashion Inspiration"
        subtitle="Real styling ideas from our community and creative team."
        align="center"
      />
      <div className="columns-2 gap-4 sm:columns-3 lg:columns-4 [&>*]:mb-4">
        {inspirationImages.map((item, index) => (
          <motion.div
            key={item.id}
            variants={fadeInUp}
            initial="hidden"
            whileInView="visible"
            viewport={viewportOnce}
            transition={{ delay: (index % 4) * 0.05 }}
            className={cn(
              "group relative break-inside-avoid overflow-hidden rounded-2xl bg-muted",
              item.tall ? "aspect-[3/4]" : "aspect-square"
            )}
          >
            <Image
              src={item.image}
              alt={item.imageAlt}
              fill
              sizes="(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw"
              className="object-cover transition-transform duration-500 group-hover:scale-110"
            />
            <div className="absolute inset-0 flex items-end bg-black/0 p-4 opacity-0 transition-all duration-300 group-hover:bg-black/40 group-hover:opacity-100">
              <span className="text-sm font-medium text-white">
                {item.caption}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
