"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "@/components/home/SectionHeading";
import { ProductCard } from "@/components/product/ProductCard";
import { fadeInUp, staggerContainer, viewportOnce } from "@/lib/motion";
import { getNewArrivals } from "@/data/catalog";
import { toCardProducts } from "@/data/catalog/adapters";

const newArrivalProducts = toCardProducts(getNewArrivals(8));

export function NewArrivals() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="Just In"
        title="New Arrivals"
        subtitle="Fresh drops from our most-loved labels, updated every week."
        viewAllHref="/new-in"
      />
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-6 lg:grid-cols-4"
      >
        {newArrivalProducts.map((product) => (
          <motion.div key={product.id} variants={fadeInUp}>
            <ProductCard product={product} />
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
