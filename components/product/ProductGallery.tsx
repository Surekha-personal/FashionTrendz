"use client";

import { useState } from "react";
import Image from "next/image";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  type CarouselApi,
} from "@/components/ui/carousel";
import { cn } from "@/lib/utils";

export function ProductGallery({
  images,
  alt,
}: {
  images: string[];
  alt: string;
}) {
  const [api, setApi] = useState<CarouselApi>();
  const [current, setCurrent] = useState(0);

  return (
    <div className="flex flex-col gap-3">
      <Carousel
        setApi={(a) => {
          setApi(a);
          a?.on("select", () => setCurrent(a.selectedScrollSnap()));
        }}
      >
        <CarouselContent className="ml-0">
          {images.map((image, index) => (
            <CarouselItem key={image + index} className="pl-0">
              <div className="group relative aspect-[3/4] w-full overflow-hidden rounded-2xl bg-muted">
                <Image
                  src={image}
                  alt={`${alt} — view ${index + 1}`}
                  fill
                  priority={index === 0}
                  sizes="(min-width: 1024px) 40vw, 100vw"
                  className="object-cover transition-transform duration-500 group-hover:scale-105"
                />
              </div>
            </CarouselItem>
          ))}
        </CarouselContent>
      </Carousel>
      <div className="flex gap-2">
        {images.map((image, index) => (
          <button
            key={image + index}
            type="button"
            aria-label={`View image ${index + 1}`}
            aria-current={current === index}
            onClick={() => api?.scrollTo(index)}
            className={cn(
              "relative aspect-square w-16 shrink-0 overflow-hidden rounded-lg ring-2 ring-transparent",
              current === index && "ring-accent"
            )}
          >
            <Image
              src={image}
              alt={`${alt} thumbnail ${index + 1}`}
              fill
              sizes="64px"
              className="object-cover"
            />
          </button>
        ))}
      </div>
    </div>
  );
}
