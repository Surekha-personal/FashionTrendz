"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import { cn } from "@/lib/utils";

interface SectionHeadingProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  viewAllHref?: string;
  align?: "left" | "center";
  className?: string;
}

export function SectionHeading({
  eyebrow,
  title,
  subtitle,
  viewAllHref,
  align = "left",
  className,
}: SectionHeadingProps) {
  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      className={cn(
        "mb-8 flex flex-col gap-2 sm:mb-10 sm:flex-row sm:items-end sm:justify-between",
        align === "center" && "sm:flex-col sm:items-center sm:text-center",
        className
      )}
    >
      <div className={cn("flex flex-col gap-2", align === "center" && "items-center")}>
        {eyebrow && (
          <span className="text-xs font-semibold tracking-[0.2em] text-accent uppercase">
            {eyebrow}
          </span>
        )}
        <h2 className="font-heading text-2xl font-semibold sm:text-3xl">
          {title}
        </h2>
        {subtitle && (
          <p className="max-w-xl text-sm text-muted-foreground sm:text-base">
            {subtitle}
          </p>
        )}
      </div>
      {viewAllHref && (
        <Link
          href={viewAllHref}
          className="group inline-flex shrink-0 items-center gap-1 text-sm font-medium text-foreground hover:text-accent"
        >
          View All
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
        </Link>
      )}
    </motion.div>
  );
}
