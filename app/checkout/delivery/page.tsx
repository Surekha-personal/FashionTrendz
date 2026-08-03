"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCheckout } from "@/context/CheckoutContext";
import { useCart } from "@/context/CartContext";
import { DELIVERY_OPTIONS, shippingFeeFor } from "@/lib/checkout";
import { formatPrice } from "@/utils/format";
import { fadeInUp } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { DeliveryMethod } from "@/types/order";

export default function DeliveryStep() {
  const router = useRouter();
  const { shippingAddress, deliveryMethod, setDeliveryMethod, hydrated } = useCheckout();
  const { subtotal } = useCart();
  const [selected, setSelected] = useState<DeliveryMethod>(deliveryMethod ?? "standard");

  useEffect(() => {
    if (hydrated && !shippingAddress) router.replace("/checkout");
  }, [hydrated, shippingAddress, router]);

  if (!shippingAddress) return null;

  const onContinue = () => {
    setDeliveryMethod(selected);
    router.push("/checkout/payment");
  };

  return (
    <motion.div variants={fadeInUp} initial="hidden" animate="visible">
      <Card className="mx-auto max-w-2xl p-6 sm:p-8">
        <h2 className="mb-6 font-heading text-xl font-semibold">Delivery Method</h2>
        <div className="flex flex-col gap-3">
          {DELIVERY_OPTIONS.map((option) => {
            const fee = shippingFeeFor(option.id, subtotal);
            const isSelected = selected === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => setSelected(option.id)}
                className={cn(
                  "flex items-center justify-between gap-4 rounded-xl border p-4 text-left transition-colors",
                  isSelected ? "border-accent bg-accent/5" : "border-border hover:border-foreground/30"
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "flex size-9 items-center justify-center rounded-full",
                      isSelected ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground"
                    )}
                  >
                    <Truck className="size-4" />
                  </span>
                  <div className="flex flex-col">
                    <span className="text-sm font-medium">{option.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {option.description}
                    </span>
                    <span className="text-xs font-medium text-accent">
                      {option.etaLabel}
                    </span>
                  </div>
                </div>
                <span className="shrink-0 text-sm font-semibold">
                  {fee === 0 ? "Free" : formatPrice(fee)}
                </span>
              </button>
            );
          })}
        </div>
        <Button size="lg" className="mt-6 w-full" onClick={onContinue}>
          Continue to Payment
        </Button>
      </Card>
    </motion.div>
  );
}
