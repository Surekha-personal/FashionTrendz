"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { Heart } from "lucide-react";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, staggerContainer, viewportOnce } from "@/lib/motion";
import { instagramPosts } from "@/data/instagram";

export function InstagramGallery() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="@fashiontrendz"
        title="Join The Community"
        subtitle="Tag @fashiontrendz for a chance to be featured."
        align="center"
      />
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="grid grid-cols-2 gap-3 sm:grid-cols-4"
      >
        {instagramPosts.map((post) => (
          <motion.div key={post.id} variants={fadeInUp}>
            <Link
              href={post.href}
              className="group relative flex aspect-square overflow-hidden rounded-xl bg-muted"
            >
              <Image
                src={post.image}
                alt={post.imageAlt}
                fill
                sizes="(min-width: 640px) 25vw, 50vw"
                className="object-cover transition-transform duration-500 group-hover:scale-110"
              />
              <div className="absolute inset-0 flex items-center justify-center gap-1.5 bg-black/0 text-white opacity-0 transition-all duration-300 group-hover:bg-black/50 group-hover:opacity-100">
                <Heart className="size-4 fill-white" />
                <span className="text-sm font-medium">{post.likes}</span>
              </div>
            </Link>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
