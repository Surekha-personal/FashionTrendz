"use client";

import Image from "next/image";
import { Quote } from "lucide-react";
import { motion } from "framer-motion";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import { Card } from "@/components/ui/card";
import { Rating } from "@/components/common/Rating";
import { SectionHeading } from "@/components/home/SectionHeading";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import { testimonials } from "@/data/testimonials";

export function CustomerReviews() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeading
        eyebrow="Loved By Our Customers"
        title="Customer Reviews"
        subtitle="Real feedback from real Fashion Trendz shoppers."
        align="center"
      />
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
      >
        <Carousel opts={{ align: "start" }}>
          <CarouselContent>
            {testimonials.map((testimonial) => (
              <CarouselItem
                key={testimonial.id}
                className="basis-full sm:basis-1/2 lg:basis-1/3"
              >
                <Card className="flex h-full flex-col gap-4 p-6">
                  <Quote className="size-6 text-accent" />
                  <p className="flex-1 text-sm text-foreground/90">
                    {testimonial.review}
                  </p>
                  <Rating value={testimonial.rating} />
                  <div className="flex items-center gap-3 pt-1">
                    <div className="relative size-10 overflow-hidden rounded-full bg-muted">
                      <Image
                        src={testimonial.avatar}
                        alt={testimonial.name}
                        fill
                        sizes="40px"
                        className="object-cover"
                      />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {testimonial.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {testimonial.location}
                      </span>
                    </div>
                  </div>
                </Card>
              </CarouselItem>
            ))}
          </CarouselContent>
          <CarouselPrevious className="-left-4 hidden sm:flex" />
          <CarouselNext className="-right-4 hidden sm:flex" />
        </Carousel>
      </motion.div>
    </section>
  );
}
