"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircle2, Download, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useCheckout } from "@/context/CheckoutContext";
import { useCart } from "@/context/CartContext";
import { getOrderById } from "@/lib/orders";
import { downloadInvoicePdf, formatPdfAmount } from "@/lib/generateInvoicePdf";
import { formatPrice } from "@/utils/format";
import type { Order } from "@/types/order";

export default function OrderSuccessPage() {
  const searchParams = useSearchParams();
  const orderId = searchParams.get("order");
  const { resetCheckout } = useCheckout();
  const { emptyCart } = useCart();
  const [order, setOrder] = useState<Order | null | undefined>(undefined);

  useEffect(() => {
    const found = orderId ? getOrderById(orderId) : undefined;
    setOrder(found ?? null);
    if (found) {
      resetCheckout();
      emptyCart();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  if (order === undefined) return null;

  if (order === null) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-24 text-center">
        <Package className="size-10 text-muted-foreground" />
        <p className="font-medium">We couldn&apos;t find that order</p>
        <Button asChild>
          <Link href="/">Continue Shopping</Link>
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
      `Bill To: ${order.shippingAddress.fullName}`,
      `${order.shippingAddress.address}, ${order.shippingAddress.city}`,
      `${order.shippingAddress.state} - ${order.shippingAddress.pincode}`,
      "",
      ...order.items.map(
        (item) =>
          `${item.name} x${item.quantity} - ${formatPdfAmount(item.discountedPrice * item.quantity)}`
      ),
      "",
      `Subtotal: ${formatPdfAmount(order.totals.subtotal)}`,
      `Coupon Discount: ${formatPdfAmount(order.totals.couponDiscount)}`,
      `GST: ${formatPdfAmount(order.totals.gst)}`,
      `Shipping: ${formatPdfAmount(order.totals.shipping)}`,
      `Platform Fee: ${formatPdfAmount(order.totals.platformFee)}`,
      `Grand Total: ${formatPdfAmount(order.totals.grandTotal)}`,
      "",
      `Payment Method: ${order.paymentLabel}`,
      `Estimated Delivery: ${order.estimatedDelivery}`,
      "",
      "Thank you for shopping with Fashion Trendz.",
    ]);
  };

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-16 text-center">
      <motion.div
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
      >
        <CheckCircle2 className="size-16 text-accent" />
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.4 }}
        className="mt-4 flex flex-col gap-2"
      >
        <h1 className="font-heading text-2xl font-semibold sm:text-3xl">
          Order Confirmed!
        </h1>
        <p className="text-sm text-muted-foreground">
          Thank you for shopping with Fashion Trendz. A confirmation has been sent to{" "}
          {order.shippingAddress.email}.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.4 }}
        className="mt-8 w-full"
      >
        <Card className="flex flex-col gap-3 p-6 text-left">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Order Number</span>
            <span className="font-medium">{order.orderId}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Invoice Number</span>
            <span className="font-medium">{order.invoiceNumber}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Estimated Delivery</span>
            <span className="font-medium">{order.estimatedDelivery}</span>
          </div>
          <Separator />
          <div className="flex justify-between text-base font-semibold">
            <span>Grand Total</span>
            <span>{formatPrice(order.totals.grandTotal)}</span>
          </div>
        </Card>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.4 }}
        className="mt-6 flex w-full flex-col gap-3 sm:flex-row"
      >
        <Button variant="outline" className="flex-1" onClick={handleDownload}>
          <Download className="size-4" />
          Download Invoice
        </Button>
        <Button asChild className="flex-1">
          <Link href="/">Continue Shopping</Link>
        </Button>
      </motion.div>
      <Link
        href="/orders"
        className="mt-4 text-sm font-medium text-accent hover:underline"
      >
        View My Orders
      </Link>
    </div>
  );
}
