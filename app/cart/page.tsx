"use client";

import Link from "next/link";
import { AnimatePresence } from "framer-motion";
import { ShoppingBag, Trash2 } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { CartLineItem } from "@/components/cart/CartLineItem";
import { EmptyState } from "@/components/common/EmptyState";
import { useCart } from "@/context/CartContext";
import { formatPrice } from "@/utils/format";

export default function CartPage() {
  const { activeItems, savedItems, itemCount, subtotal, totalSavings, hydrated, emptyCart } =
    useCart();

  if (!hydrated) return null;

  const isEmpty = activeItems.length === 0 && savedItems.length === 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">Home</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Bag</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-heading text-2xl font-semibold sm:text-3xl">
          Your Bag {itemCount > 0 && `(${itemCount})`}
        </h1>
        {activeItems.length > 0 && (
          <Button variant="ghost" size="sm" onClick={emptyCart} className="text-muted-foreground">
            <Trash2 className="size-3.5" />
            Empty Bag
          </Button>
        )}
      </div>

      {isEmpty ? (
        <EmptyState
          icon={ShoppingBag}
          title="Your bag is empty"
          description="Looks like you haven't added anything yet."
          action={
            <Button asChild>
              <Link href="/">Continue Shopping</Link>
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_360px]">
          <div className="flex flex-col gap-8">
            {activeItems.length > 0 && (
              <Card className="p-4 sm:p-6">
                <AnimatePresence initial={false}>
                  {activeItems.map((line) => (
                    <div
                      key={line.lineId}
                      className="border-b border-border py-4 first:pt-0 last:border-b-0 last:pb-0"
                    >
                      <CartLineItem line={line} />
                    </div>
                  ))}
                </AnimatePresence>
              </Card>
            )}

            {savedItems.length > 0 && (
              <div className="flex flex-col gap-4">
                <h2 className="font-heading text-lg font-semibold">
                  Saved For Later ({savedItems.length})
                </h2>
                <Card className="p-4 sm:p-6">
                  <AnimatePresence initial={false}>
                    {savedItems.map((line) => (
                      <div
                        key={line.lineId}
                        className="border-b border-border py-4 first:pt-0 last:border-b-0 last:pb-0"
                      >
                        <CartLineItem line={line} />
                      </div>
                    ))}
                  </AnimatePresence>
                </Card>
              </div>
            )}
          </div>

          {activeItems.length > 0 && (
            <Card className="h-fit p-5 sm:p-6">
              <h2 className="font-heading text-lg font-semibold">Order Summary</h2>
              <div className="mt-4 flex flex-col gap-2.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    Subtotal ({itemCount} {itemCount === 1 ? "item" : "items"})
                  </span>
                  <span>{formatPrice(subtotal + totalSavings)}</span>
                </div>
                {totalSavings > 0 && (
                  <div className="flex justify-between text-accent">
                    <span>Discount</span>
                    <span>-{formatPrice(totalSavings)}</span>
                  </div>
                )}
                <Separator className="my-1" />
                <div className="flex justify-between text-base font-semibold">
                  <span>Total</span>
                  <span>{formatPrice(subtotal)}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Taxes and shipping calculated at checkout.
                </p>
              </div>
              <Button asChild size="lg" className="mt-4 h-12 w-full text-base font-semibold">
                <Link href="/checkout">Proceed to Checkout</Link>
              </Button>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
