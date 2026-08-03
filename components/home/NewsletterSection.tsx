"use client";

import { motion } from "framer-motion";
import { Mail } from "lucide-react";
import { NewsletterForm } from "@/components/forms/NewsletterForm";
import { fadeInUp, viewportOnce } from "@/lib/motion";

export function NewsletterSection() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="flex flex-col items-center gap-4 rounded-3xl bg-primary px-6 py-14 text-center text-primary-foreground sm:px-12"
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-white/10">
          <Mail className="size-5" />
        </span>
        <h2 className="font-heading max-w-lg text-2xl font-semibold sm:text-3xl">
          Get 10% Off Your First Order
        </h2>
        <p className="max-w-md text-sm text-primary-foreground/75">
          Subscribe for early access to new arrivals, exclusive edits and
          member-only sales.
        </p>
        <NewsletterForm className="mt-2 w-full max-w-md [&_input]:h-11 [&_input]:rounded-full [&_input]:border-white/20 [&_input]:bg-white/10 [&_input]:text-white [&_input]:placeholder:text-white/60 [&_button]:h-11 [&_button]:rounded-full [&_button]:bg-accent [&_button]:text-accent-foreground [&_button]:hover:bg-accent/90" />
      </motion.div>
    </section>
  );
}
