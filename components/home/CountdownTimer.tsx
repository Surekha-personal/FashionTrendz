"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

function getTimeLeft(target: number) {
  const diff = Math.max(target - Date.now(), 0);
  return {
    days: Math.floor(diff / 86_400_000),
    hours: Math.floor((diff / 3_600_000) % 24),
    minutes: Math.floor((diff / 60_000) % 60),
    seconds: Math.floor((diff / 1000) % 60),
  };
}

function TimeBlock({ value, label }: { value: number; label: string }) {
  const padded = String(value).padStart(2, "0");
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative flex size-14 items-center justify-center overflow-hidden rounded-xl bg-foreground text-background sm:size-16">
        <AnimatePresence mode="popLayout">
          <motion.span
            key={padded}
            initial={{ y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -16, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="font-heading text-xl font-semibold sm:text-2xl"
          >
            {padded}
          </motion.span>
        </AnimatePresence>
      </div>
      <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase sm:text-xs">
        {label}
      </span>
    </div>
  );
}

export function CountdownTimer({ targetDate }: { targetDate: Date }) {
  const target = targetDate.getTime();
  // ponytail: static 0s on server avoids a Date.now() hydration mismatch; real countdown kicks in after mount.
  const [time, setTime] = useState({ days: 0, hours: 0, minutes: 0, seconds: 0 });

  useEffect(() => {
    setTime(getTimeLeft(target));
    const id = setInterval(() => setTime(getTimeLeft(target)), 1000);
    return () => clearInterval(id);
  }, [target]);

  return (
    <div className="flex items-center gap-3 sm:gap-4">
      <TimeBlock value={time.days} label="Days" />
      <TimeBlock value={time.hours} label="Hrs" />
      <TimeBlock value={time.minutes} label="Min" />
      <TimeBlock value={time.seconds} label="Sec" />
    </div>
  );
}
