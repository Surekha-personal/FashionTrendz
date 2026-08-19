"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import Autoplay from "embla-carousel-autoplay";
import { AnimatePresence, motion } from "framer-motion";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from "@/components/ui/carousel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { HeroSlide } from "@/types/home";

export function HeroCarousel({ slides }: { slides: HeroSlide[] }) {
  const [api, setApi] = useState<CarouselApi>();
  const [current, setCurrent] = useState(0);

  if (slides.length === 0) return null;

  return (
    <section className="relative">
      <Carousel
        opts={{ loop: true }}
        plugins={[Autoplay({ delay: 5500, stopOnInteraction: false })]}
        setApi={(a) => {
          setApi(a);
          a?.on("select", () => setCurrent(a.selectedScrollSnap()));
        }}
      >
        <CarouselContent className="ml-0">
          {slides.map((slide, index) => (
            <CarouselItem key={slide.id} className="pl-0">
              <div className="relative h-[70vh] min-h-[420px] w-full overflow-hidden sm:h-[80vh] sm:min-h-[520px]">
                <Image
                  src={slide.image}
                  alt={slide.imageAlt}
                  fill
                  priority={index <= 1}
                  sizes="100vw"
                  className="object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
                <div className="relative flex h-full max-w-7xl flex-col justify-end gap-4 px-4 pb-16 sm:mx-auto sm:px-6 sm:pb-24 lg:px-8">
                  <AnimatePresence mode="wait">
                    {current === index && (
                      <motion.div
                        key={slide.id}
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -12 }}
                        transition={{ duration: 0.5, ease: "easeOut" }}
                        className="flex flex-col gap-3 text-white"
                      >
                        {slide.eyebrow && (
                          <span className="text-xs font-semibold tracking-[0.25em] text-white/80 uppercase">
                            {slide.eyebrow}
                          </span>
                        )}
                        <h1 className="font-heading max-w-lg text-3xl font-semibold sm:text-5xl">
                          {slide.title}
                        </h1>
                        <p className="max-w-md text-sm text-white/85 sm:text-base">
                          {slide.subtitle}
                        </p>
                        <Button
                          asChild
                          size="lg"
                          className="mt-2 w-fit rounded-full bg-white text-xs font-semibold tracking-[0.15em] text-primary uppercase hover:bg-white/90"
                        >
                          <Link href={slide.ctaHref}>{slide.ctaLabel}</Link>
                        </Button>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            </CarouselItem>
          ))}
        </CarouselContent>
        <CarouselPrevious className="left-4 border-none bg-white/20 text-white backdrop-blur-sm hover:bg-white/30 hover:text-white sm:left-8" />
        <CarouselNext className="right-4 border-none bg-white/20 text-white backdrop-blur-sm hover:bg-white/30 hover:text-white sm:right-8" />
      </Carousel>
      <div className="absolute inset-x-0 bottom-5 flex items-center justify-center gap-2">
        {slides.map((slide, index) => (
          <button
            key={slide.id}
            type="button"
            aria-label={`Go to slide ${index + 1}`}
            onClick={() => api?.scrollTo(index)}
            className={cn(
              "h-1.5 rounded-full bg-white/50 transition-all",
              current === index ? "w-6 bg-white" : "w-1.5"
            )}
          />
        ))}
      </div>
    </section>
  );
}
