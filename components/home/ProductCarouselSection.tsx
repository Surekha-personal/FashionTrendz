"use client";

import { motion } from "framer-motion";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import { ProductCard } from "@/components/product/ProductCard";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import type { Product } from "@/types/product";

interface ProductCarouselSectionProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  viewAllHref?: string;
  products: Product[];
  tinted?: boolean;
}

export function ProductCarouselSection({
  eyebrow,
  title,
  subtitle,
  viewAllHref,
  products,
  tinted = false,
}: ProductCarouselSectionProps) {
  return (
    <section className={tinted ? "bg-muted/40" : undefined}>
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow={eyebrow}
          title={title}
          subtitle={subtitle}
          viewAllHref={viewAllHref}
        />
        <motion.div
          variants={fadeInUp}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
        >
          <Carousel opts={{ align: "start" }}>
            <CarouselContent>
              {products.map((product) => (
                <CarouselItem
                  key={product.id}
                  className="basis-1/2 sm:basis-1/3 lg:basis-1/4 xl:basis-1/5"
                >
                  <ProductCard product={product} />
                </CarouselItem>
              ))}
            </CarouselContent>
            <CarouselPrevious className="-left-4 hidden sm:flex" />
            <CarouselNext className="-right-4 hidden sm:flex" />
          </Carousel>
        </motion.div>
      </div>
    </section>
  );
}
