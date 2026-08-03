"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { step: 1, label: "Shipping" },
  { step: 2, label: "Delivery" },
  { step: 3, label: "Payment" },
  { step: 4, label: "Review" },
];

export function CheckoutStepper({ currentStep }: { currentStep: number }) {
  return (
    <ol className="mx-auto mb-10 flex w-full max-w-2xl items-center">
      {STEPS.map((s, index) => {
        const isComplete = currentStep > s.step;
        const isActive = currentStep === s.step;
        return (
          <li key={s.step} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <motion.div
                initial={false}
                animate={{
                  scale: isActive ? 1.1 : 1,
                }}
                className={cn(
                  "flex size-8 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors sm:size-9",
                  isComplete
                    ? "border-accent bg-accent text-accent-foreground"
                    : isActive
                      ? "border-accent text-accent"
                      : "border-border text-muted-foreground"
                )}
              >
                {isComplete ? <Check className="size-4" /> : s.step}
              </motion.div>
              <span
                className={cn(
                  "hidden text-xs font-medium sm:block",
                  isActive || isComplete ? "text-foreground" : "text-muted-foreground"
                )}
              >
                {s.label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <div className="mx-2 h-0.5 flex-1 bg-border sm:mx-3">
                <motion.div
                  initial={false}
                  animate={{ width: isComplete ? "100%" : "0%" }}
                  transition={{ duration: 0.3 }}
                  className="h-full bg-accent"
                />
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
