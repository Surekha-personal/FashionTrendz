"use client";

import { motion } from "framer-motion";
import { fadeInUp, viewportOnce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      className={cn(
        "flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border py-20 text-center",
        className
      )}
    >
      <div className="flex size-20 items-center justify-center rounded-full bg-gradient-to-br from-accent/15 to-accent/5">
        <Icon className="size-9 text-accent" />
      </div>
      <div className="flex flex-col gap-1">
        <p className="font-medium">{title}</p>
        {description && (
          <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </motion.div>
  );
}
