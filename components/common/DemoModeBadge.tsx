"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { isDemoModeEnabled } from "@/lib/demoMode";

export function DemoModeBadge() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    setEnabled(isDemoModeEnabled());
  }, []);

  if (!enabled) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="fixed bottom-5 left-5 z-40 flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-lg sm:bottom-8 sm:left-8"
    >
      <Sparkles className="size-3.5 text-accent" />
      Demo Mode
    </motion.div>
  );
}
