"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { BadgePercent, Pencil, Tag } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useCheckout } from "@/context/CheckoutContext";
import { useCart } from "@/context/CartContext";
import {
  calculateTotals,
  DELIVERY_OPTIONS,
  estimatedDeliveryDate,
  validateCoupon,
} from "@/lib/checkout";
import { generateInvoiceNumber, generateOrderNumber, saveOrder } from "@/lib/orders";
import { formatPrice } from "@/utils/format";
import { fadeInUp } from "@/lib/motion";
import type { Order } from "@/types/order";

export default function ReviewStep() {
  const router = useRouter();
  const {
    shippingAddress,
    deliveryMethod,
    paymentMethod,
    paymentLabel,
    couponCode,
    couponDiscount,
    setCoupon,
    hydrated: checkoutHydrated,
  } = useCheckout();
  const { activeItems, subtotal, totalSavings, hydrated: cartHydrated } = useCart();
  const [couponInput, setCouponInput] = useState(couponCode ?? "");
  const [couponMessage, setCouponMessage] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    if (checkoutHydrated && !paymentMethod) router.replace("/checkout/payment");
  }, [checkoutHydrated, paymentMethod, router]);

  if (!paymentMethod || !shippingAddress || !deliveryMethod || !cartHydrated) return null;

  const totals = calculateTotals({
    subtotal,
    productDiscount: totalSavings,
    couponCode: couponCode ?? undefined,
    couponDiscount,
    deliveryMethod,
  });
  const deliveryOption = DELIVERY_OPTIONS.find((o) => o.id === deliveryMethod)!;

  const applyCoupon = () => {
    if (!couponInput.trim()) return;
    const result = validateCoupon(couponInput, subtotal);
    setCouponMessage(result.message);
    if (result.valid) {
      setCoupon(couponInput.trim().toUpperCase(), result.discount);
    } else {
      setCoupon(null, 0);
    }
  };

  const removeCoupon = () => {
    setCoupon(null, 0);
    setCouponInput("");
    setCouponMessage(null);
  };

  const placeOrder = () => {
    setPlacing(true);
    const order: Order = {
      orderId: generateOrderNumber(),
      invoiceNumber: generateInvoiceNumber(),
      createdAt: new Date().toISOString(),
      items: activeItems,
      shippingAddress,
      deliveryMethod,
      paymentMethod,
      paymentLabel,
      totals,
      estimatedDelivery: estimatedDeliveryDate(deliveryMethod),
    };
    saveOrder(order);
    router.push(`/checkout/success?order=${order.orderId}`);
  };

  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      animate="visible"
      className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_360px]"
    >
      <div className="flex flex-col gap-6">
        <Card className="p-5 sm:p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold">
              Products ({activeItems.length})
            </h2>
          </div>
          <div className="flex flex-col gap-4">
            {activeItems.map((item) => (
              <div key={item.lineId} className="flex gap-3">
                <div className="relative size-16 shrink-0 overflow-hidden rounded-lg bg-muted">
                  <Image src={item.image} alt={item.name} fill className="object-cover" />
                </div>
                <div className="flex flex-1 flex-col">
                  <span className="text-xs text-muted-foreground">{item.brand}</span>
                  <span className="line-clamp-1 text-sm font-medium">{item.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {[item.size, item.color].filter(Boolean).join(" · ")}
                    {item.size || item.color ? " · " : ""}
                    Qty: {item.quantity}
                  </span>
                </div>
                <span className="text-sm font-semibold">
                  {formatPrice(item.discountedPrice * item.quantity)}
                </span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="flex flex-col gap-1 p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold">Shipping Address</h2>
            <Link
              href="/checkout"
              className="flex items-center gap-1 text-xs font-medium text-accent"
            >
              <Pencil className="size-3" /> Edit
            </Link>
          </div>
          <p className="text-sm">
            {shippingAddress.fullName} · {shippingAddress.mobile}
          </p>
          <p className="text-sm text-muted-foreground">
            {shippingAddress.address}, {shippingAddress.city}, {shippingAddress.state} -{" "}
            {shippingAddress.pincode}, {shippingAddress.country}
          </p>
          <Badge variant="outline" className="mt-1 w-fit capitalize">
            {shippingAddress.addressType}
          </Badge>
        </Card>

        <Card className="flex flex-col gap-1 p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold">Delivery</h2>
            <Link
              href="/checkout/delivery"
              className="flex items-center gap-1 text-xs font-medium text-accent"
            >
              <Pencil className="size-3" /> Edit
            </Link>
          </div>
          <p className="text-sm">{deliveryOption.label}</p>
          <p className="text-sm text-muted-foreground">
            Estimated delivery: {estimatedDeliveryDate(deliveryMethod)}
          </p>
        </Card>

        <Card className="flex flex-col gap-1 p-5 sm:p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-heading text-lg font-semibold">Payment</h2>
            <Link
              href="/checkout/payment"
              className="flex items-center gap-1 text-xs font-medium text-accent"
            >
              <Pencil className="size-3" /> Edit
            </Link>
          </div>
          <p className="text-sm text-muted-foreground">{paymentLabel}</p>
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        <Card className="p-5 sm:p-6">
          <h2 className="mb-3 flex items-center gap-1.5 font-heading text-base font-semibold">
            <Tag className="size-4" /> Coupon
          </h2>
          {couponCode ? (
            <div className="flex items-center justify-between rounded-lg bg-accent/10 px-3 py-2 text-sm text-accent">
              <span className="flex items-center gap-1.5 font-medium">
                <BadgePercent className="size-3.5" />
                {couponCode} applied
              </span>
              <button type="button" onClick={removeCoupon} className="text-xs underline">
                Remove
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Input
                placeholder="Enter coupon code"
                value={couponInput}
                onChange={(e) => setCouponInput(e.target.value)}
                className="uppercase"
              />
              <Button variant="secondary" onClick={applyCoupon}>
                Apply
              </Button>
            </div>
          )}
          {couponMessage && !couponCode && (
            <p className="mt-2 text-xs text-destructive">{couponMessage}</p>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            Try WELCOME10, FLAT500, FASHION20 or LUXE15
          </p>
        </Card>

        <Card className="h-fit p-5 sm:p-6">
          <h2 className="font-heading text-lg font-semibold">Price Summary</h2>
          <div className="mt-4 flex flex-col gap-2.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>{formatPrice(subtotal + totalSavings)}</span>
            </div>
            {totalSavings > 0 && (
              <div className="flex justify-between text-accent">
                <span>Discount</span>
                <span>-{formatPrice(totalSavings)}</span>
              </div>
            )}
            {totals.couponDiscount > 0 && (
              <div className="flex justify-between text-accent">
                <span>Coupon Discount</span>
                <span>-{formatPrice(totals.couponDiscount)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">GST (5%)</span>
              <span>{formatPrice(totals.gst)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Shipping</span>
              <span>{totals.shipping === 0 ? "Free" : formatPrice(totals.shipping)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Platform Fee</span>
              <span>{formatPrice(totals.platformFee)}</span>
            </div>
            <Separator className="my-1" />
            <div className="flex justify-between text-base font-semibold">
              <span>Grand Total</span>
              <span>{formatPrice(totals.grandTotal)}</span>
            </div>
          </div>
          <Button size="lg" className="mt-5 w-full" onClick={placeOrder} disabled={placing}>
            Place Order
          </Button>
        </Card>
      </div>
    </motion.div>
  );
}
