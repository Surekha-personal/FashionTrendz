"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, staggerContainer, viewportOnce } from "@/lib/motion";
import { blogPosts } from "@/data/blog";

export function FashionBlog() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="Fashion Trendz Journal"
        title="From The Blog"
        subtitle="Style guides, trend reports and behind-the-scenes stories."
        viewAllHref="/blog"
      />
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="grid grid-cols-1 gap-6 sm:grid-cols-3"
      >
        {blogPosts.map((post) => (
          <motion.div key={post.id} variants={fadeInUp}>
            <Card className="group h-full gap-3 overflow-hidden p-0 shadow-sm transition-shadow hover:shadow-lg">
              <Link href={post.href} className="block">
                <div className="relative aspect-[16/10] w-full overflow-hidden bg-muted">
                  <Image
                    src={post.image}
                    alt={post.imageAlt}
                    fill
                    sizes="(min-width: 640px) 33vw, 100vw"
                    className="object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                  <Badge className="absolute top-3 left-3">{post.category}</Badge>
                </div>
                <div className="flex flex-col gap-2 px-5 pb-5">
                  <span className="text-xs text-muted-foreground">
                    {post.readTime}
                  </span>
                  <h3 className="font-heading text-lg leading-snug font-semibold">
                    {post.title}
                  </h3>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {post.excerpt}
                  </p>
                  <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-accent">
                    Read More
                    <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-1" />
                  </span>
                </div>
              </Link>
            </Card>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
