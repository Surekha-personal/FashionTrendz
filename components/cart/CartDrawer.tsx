"use client";

import { useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { CartLineItem } from "@/components/cart/CartLineItem";
import { useCart } from "@/context/CartContext";
import { formatPrice } from "@/utils/format";

export function CartDrawer() {
  const [open, setOpen] = useState(false);
  const { activeItems, itemCount, subtotal, totalSavings } = useCart();

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="relative transition-colors hover:text-accent">
          <ShoppingBag />
          <AnimatePresence>
            {itemCount > 0 && (
              <motion.span
                key={itemCount}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                exit={{ scale: 0 }}
                transition={{ type: "spring", stiffness: 500, damping: 20 }}
                className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-accent text-[10px] font-medium text-accent-foreground"
              >
                {itemCount}
              </motion.span>
            )}
          </AnimatePresence>
          <span className="sr-only">Open bag</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex w-full flex-col sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Your Bag ({itemCount})</SheetTitle>
        </SheetHeader>

        {activeItems.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
            <ShoppingBag className="size-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Your bag is empty</p>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Continue Shopping
            </Button>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto px-4">
              <AnimatePresence initial={false}>
                {activeItems.map((line) => (
                  <div key={line.lineId} className="border-b border-border py-4 first:pt-0">
                    <CartLineItem line={line} />
                  </div>
                ))}
              </AnimatePresence>
            </div>
            <div className="flex flex-col gap-3 border-t border-border p-4">
              {totalSavings > 0 && (
                <div className="flex items-center justify-between text-sm text-accent">
                  <span>Your Savings</span>
                  <span>{formatPrice(totalSavings)}</span>
                </div>
              )}
              <div className="flex items-center justify-between text-base font-semibold">
                <span>Subtotal</span>
                <span>{formatPrice(subtotal)}</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Taxes and shipping calculated at checkout.
              </p>
              <Separator />
              <div className="flex gap-2">
                <Button
                  asChild
                  variant="outline"
                  className="flex-1"
                  onClick={() => setOpen(false)}
                >
                  <Link href="/cart">View Bag</Link>
                </Button>
                <Button asChild className="flex-1" onClick={() => setOpen(false)}>
                  <Link href="/checkout">Checkout</Link>
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
