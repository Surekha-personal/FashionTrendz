"use client";

import { useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Home, RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fadeInUp, viewportOnce } from "@/lib/motion";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center px-4 py-16 text-center">
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="flex flex-col items-center gap-6"
      >
        <motion.div
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 16 }}
          className="flex size-24 items-center justify-center rounded-full bg-destructive/10"
        >
          <TriangleAlert className="size-10 text-destructive" />
        </motion.div>
        <div className="flex flex-col gap-2">
          <span className="font-heading text-5xl font-semibold text-foreground/90">
            500
          </span>
          <h1 className="font-heading text-xl font-semibold">
            Something Went Wrong
          </h1>
          <p className="text-sm text-muted-foreground">
            An unexpected error occurred while loading this page. Please try
            again, or head back home.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button onClick={reset}>
            <RotateCcw className="size-4" />
            Try Again
          </Button>
          <Button asChild variant="outline">
            <Link href="/">
              <Home className="size-4" />
              Back to Home
            </Link>
          </Button>
        </div>
      </motion.div>
    </div>
  );
}
