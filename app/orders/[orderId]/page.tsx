"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Download, Package } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import { apiOrderDetailToOrder } from "@/lib/apiAdapters";
import { downloadInvoicePdf, formatPdfAmount } from "@/lib/generateInvoicePdf";
import { formatPrice } from "@/utils/format";
import { fadeInUp } from "@/lib/motion";
import type { ApiOrderDetail } from "@/types/api";
import type { Order } from "@/types/order";

export default function OrderDetailPage() {
  const params = useParams<{ orderId: string }>();
  const router = useRouter();
  const { isAuthenticated, hydrated: authHydrated } = useAuth();
  const [order, setOrder] = useState<Order | null | undefined>(undefined);

  useEffect(() => {
    if (!authHydrated) return;
    if (!isAuthenticated) {
      router.replace(`/login?next=/orders/${params.orderId}`);
      return;
    }
    api
      .get<ApiOrderDetail>(`/orders/${params.orderId}/`)
      .then((data) => setOrder(apiOrderDetailToOrder(data)))
      .catch((err) => {
        if (!(err instanceof ApiError)) throw err;
        setOrder(null);
      });
  }, [params.orderId, authHydrated, isAuthenticated, router]);

  if (order === undefined) return null;

  if (order === null) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-24 text-center">
        <Package className="size-10 text-muted-foreground" />
        <p className="font-medium">Order not found</p>
        <Button asChild>
          <Link href="/orders">Back to Orders</Link>
        </Button>
      </div>
    );
  }

  const handleDownload = () => {
    downloadInvoicePdf(`${order.invoiceNumber}.pdf`, [
      `Invoice: ${order.invoiceNumber}`,
      `Order Number: ${order.orderId}`,
      `Order Date: ${new Date(order.createdAt).toLocaleDateString("en-IN")}`,
      "",
      ...order.items.map(
        (item) =>
          `${item.name} x${item.quantity} - ${formatPdfAmount(item.discountedPrice * item.quantity)}`
      ),
      "",
      `Grand Total: ${formatPdfAmount(order.totals.grandTotal)}`,
      `Payment Method: ${order.paymentLabel}`,
    ]);
  };

  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      animate="visible"
      className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8"
    >
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">Home</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/orders">My Orders</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{order.orderId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-semibold">{order.orderId}</h1>
          <p className="text-sm text-muted-foreground">
            Placed on{" "}
            {new Date(order.createdAt).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="secondary">{order.statusDisplay}</Badge>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="size-3.5" />
            Invoice
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <Card className="flex flex-col gap-4 p-5 sm:p-6">
          <h2 className="font-heading text-lg font-semibold">
            Items ({order.items.length})
          </h2>
          {order.items.map((item) => (
            <div key={item.lineId} className="flex gap-3 border-b border-border pb-4 last:border-b-0 last:pb-0">
              <div className="relative size-16 shrink-0 overflow-hidden rounded-lg bg-muted">
                <Image src={item.image} alt={item.name} fill className="object-cover" />
              </div>
              <div className="flex flex-1 flex-col">
                <span className="text-xs text-muted-foreground">{item.brand}</span>
                <span className="text-sm font-medium">{item.name}</span>
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

          <Separator />
          <div>
            <h3 className="mb-1 text-sm font-semibold">Shipping Address</h3>
            <p className="text-sm text-muted-foreground">
              {order.shippingAddress.fullName} · {order.shippingAddress.mobile}
              <br />
              {order.shippingAddress.address}, {order.shippingAddress.city},{" "}
              {order.shippingAddress.state} - {order.shippingAddress.pincode}
            </p>
          </div>
        </Card>

        <Card className="h-fit p-5 sm:p-6">
          <h2 className="font-heading text-lg font-semibold">Order Summary</h2>
          <div className="mt-4 flex flex-col gap-2.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>{formatPrice(order.totals.subtotal)}</span>
            </div>
            {order.totals.couponDiscount > 0 && (
              <div className="flex justify-between text-accent">
                <span>Coupon ({order.totals.couponCode})</span>
                <span>-{formatPrice(order.totals.couponDiscount)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">GST</span>
              <span>{formatPrice(order.totals.gst)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Shipping</span>
              <span>{order.totals.shipping === 0 ? "Free" : formatPrice(order.totals.shipping)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Platform Fee</span>
              <span>{formatPrice(order.totals.platformFee)}</span>
            </div>
            <Separator className="my-1" />
            <div className="flex justify-between text-base font-semibold">
              <span>Grand Total</span>
              <span>{formatPrice(order.totals.grandTotal)}</span>
            </div>
          </div>
          <Separator className="my-4" />
          <div className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Payment</span>
            <span className="text-muted-foreground">{order.paymentLabel}</span>
          </div>
          <div className="mt-3 flex flex-col gap-1 text-sm">
            <span className="font-medium">Estimated Delivery</span>
            <span className="text-muted-foreground">{order.estimatedDelivery}</span>
          </div>
        </Card>
      </div>
    </motion.div>
  );
}
