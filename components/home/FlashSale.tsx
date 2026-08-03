"use client";

import { motion } from "framer-motion";
import { Zap } from "lucide-react";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import { Badge } from "@/components/ui/badge";
import { ProductCard } from "@/components/product/ProductCard";
import { CountdownTimer } from "@/components/home/CountdownTimer";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import { getFlashSaleProducts } from "@/data/catalog";
import { toCardProducts } from "@/data/catalog/adapters";

const flashSaleProducts = toCardProducts(getFlashSaleProducts(10));

const SALE_END = new Date();
SALE_END.setHours(SALE_END.getHours() + 18, 30, 0, 0);

export function FlashSale() {
  return (
    <section className="bg-primary text-primary-foreground">
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <motion.div
          variants={fadeInUp}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
          className="mb-10 flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center"
        >
          <div className="flex flex-col gap-2">
            <Badge className="w-fit gap-1 bg-accent text-accent-foreground">
              <Zap className="size-3" />
              Flash Sale
            </Badge>
            <h2 className="font-heading text-2xl font-semibold sm:text-3xl">
              Today Only — Up To 40% Off
            </h2>
            <p className="text-sm text-primary-foreground/70">
              Prices drop back the moment the clock hits zero.
            </p>
          </div>
          <CountdownTimer targetDate={SALE_END} />
        </motion.div>
        <Carousel opts={{ align: "start" }}>
          <CarouselContent>
            {flashSaleProducts.map((product) => (
              <CarouselItem
                key={product.id}
                className="basis-1/2 sm:basis-1/3 lg:basis-1/4 xl:basis-1/5"
              >
                <ProductCard product={product} />
              </CarouselItem>
            ))}
          </CarouselContent>
          <CarouselPrevious className="-left-4 hidden border-none bg-white/15 text-white hover:bg-white/25 hover:text-white sm:flex" />
          <CarouselNext className="-right-4 hidden border-none bg-white/15 text-white hover:bg-white/25 hover:text-white sm:flex" />
        </Carousel>
      </div>
    </section>
  );
}
