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
import { Separator } from "@/components/ui/separator";
import { useCheckout } from "@/context/CheckoutContext";
import { useCart } from "@/context/CartContext";
import { api, ApiError } from "@/lib/api";
import { DELIVERY_OPTIONS } from "@/lib/checkout";
import { formatPrice } from "@/utils/format";
import { fadeInUp } from "@/lib/motion";
import type { ApiOrderDetail } from "@/types/api";

export default function ReviewStep() {
  const router = useRouter();
  const {
    shippingAddress,
    deliveryMethod,
    paymentMethod,
    paymentLabel,
    hydrated: checkoutHydrated,
    resetCheckout,
  } = useCheckout();
  const {
    activeItems,
    summary,
    couponCode,
    applyCoupon,
    removeCoupon,
    refresh: refreshCart,
    hydrated: cartHydrated,
  } = useCart();
  const [couponInput, setCouponInput] = useState("");
  const [couponMessage, setCouponMessage] = useState<string | null>(null);
  const [applyingCoupon, setApplyingCoupon] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [placeError, setPlaceError] = useState<string | null>(null);

  useEffect(() => {
    if (checkoutHydrated && (!paymentMethod || !shippingAddress?.id)) {
      router.replace(shippingAddress?.id ? "/checkout/payment" : "/checkout");
    }
  }, [checkoutHydrated, paymentMethod, shippingAddress, router]);

  if (!paymentMethod || !shippingAddress?.id || !deliveryMethod || !cartHydrated || !summary) {
    return null;
  }

  const deliveryOption = DELIVERY_OPTIONS.find((o) => o.id === deliveryMethod)!;

  const onApplyCoupon = async () => {
    if (!couponInput.trim()) return;
    setApplyingCoupon(true);
    setCouponMessage(null);
    try {
      const message = await applyCoupon(couponInput.trim().toUpperCase());
      setCouponMessage(message);
    } catch (err) {
      setCouponMessage(err instanceof ApiError ? err.message : "Could not apply coupon.");
    } finally {
      setApplyingCoupon(false);
    }
  };

  const onRemoveCoupon = async () => {
    await removeCoupon();
    setCouponInput("");
    setCouponMessage(null);
  };

  const placeOrder = async () => {
    setPlacing(true);
    setPlaceError(null);
    try {
      const order = await api.post<ApiOrderDetail>("/checkout/place-order/", {
        shipping_address: shippingAddress.id,
        payment_method: paymentMethod,
        delivery_method: deliveryMethod,
      });
      resetCheckout();
      await refreshCart();
      router.push(`/checkout/success?order=${order.order_number}`);
    } catch (err) {
      setPlaceError(err instanceof ApiError ? err.message : "Could not place your order.");
      setPlacing(false);
    }
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
              <button type="button" onClick={onRemoveCoupon} className="text-xs underline">
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
              <Button variant="secondary" onClick={onApplyCoupon} disabled={applyingCoupon}>
                Apply
              </Button>
            </div>
          )}
          {couponMessage && !couponCode && (
            <p className="mt-2 text-xs text-destructive">{couponMessage}</p>
          )}
        </Card>

        <Card className="h-fit p-5 sm:p-6">
          <h2 className="font-heading text-lg font-semibold">Price Summary</h2>
          <div className="mt-4 flex flex-col gap-2.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>{formatPrice(Number(summary.subtotal))}</span>
            </div>
            {Number(summary.discount) > 0 && (
              <div className="flex justify-between text-accent">
                <span>Discount</span>
                <span>-{formatPrice(Number(summary.discount))}</span>
              </div>
            )}
            {Number(summary.coupon_discount) > 0 && (
              <div className="flex justify-between text-accent">
                <span>Coupon Discount</span>
                <span>-{formatPrice(Number(summary.coupon_discount))}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tax</span>
              <span>{formatPrice(Number(summary.tax))}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Shipping</span>
              <span>
                {Number(summary.shipping) === 0 ? "Free" : formatPrice(Number(summary.shipping))}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Platform Fee</span>
              <span>{formatPrice(Number(summary.platform_fee))}</span>
            </div>
            <Separator className="my-1" />
            <div className="flex justify-between text-base font-semibold">
              <span>Grand Total</span>
              <span>{formatPrice(Number(summary.grand_total))}</span>
            </div>
          </div>
          {placeError && <p className="mt-3 text-sm text-destructive">{placeError}</p>}
          <Button
            size="lg"
            className="mt-5 h-12 w-full text-base font-semibold"
            onClick={placeOrder}
            disabled={placing}
          >
            {placing ? "Placing Order…" : "Place Order"}
          </Button>
        </Card>
      </div>
    </motion.div>
  );
}
