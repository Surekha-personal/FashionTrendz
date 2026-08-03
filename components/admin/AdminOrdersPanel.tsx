"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getOrders } from "@/lib/orders";
import { formatPrice } from "@/utils/format";
import type { Order } from "@/types/order";

const FALLBACK_ORDERS: Pick<Order, "orderId" | "createdAt" | "shippingAddress" | "totals">[] = [
  {
    orderId: "FT8K2M91",
    createdAt: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    shippingAddress: { fullName: "Rohan Verma" } as Order["shippingAddress"],
    totals: { grandTotal: 4290 } as Order["totals"],
  },
  {
    orderId: "FT7J1L84",
    createdAt: new Date(Date.now() - 5 * 86_400_000).toISOString(),
    shippingAddress: { fullName: "Priya Nair" } as Order["shippingAddress"],
    totals: { grandTotal: 2870 } as Order["totals"],
  },
  {
    orderId: "FT6H9K73",
    createdAt: new Date(Date.now() - 9 * 86_400_000).toISOString(),
    shippingAddress: { fullName: "Arjun Mehta" } as Order["shippingAddress"],
    totals: { grandTotal: 6120 } as Order["totals"],
  },
];

export function AdminOrdersPanel() {
  const [orders, setOrders] = useState<
    Pick<Order, "orderId" | "createdAt" | "shippingAddress" | "totals">[]
  >([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const stored = getOrders();
    setOrders(stored.length > 0 ? stored : FALLBACK_ORDERS);
    setHydrated(true);
  }, []);

  if (!hydrated) return null;

  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-heading text-lg font-semibold">Recent Orders</h2>
        <Badge variant="secondary">{orders.length} shown</Badge>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase">
              <th className="pb-2 font-medium">Order</th>
              <th className="pb-2 font-medium">Customer</th>
              <th className="pb-2 font-medium">Date</th>
              <th className="pb-2 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {orders.slice(0, 6).map((order) => (
              <tr key={order.orderId} className="border-b border-border last:border-0">
                <td className="py-2.5 font-medium">{order.orderId}</td>
                <td className="py-2.5 text-muted-foreground">
                  {order.shippingAddress.fullName}
                </td>
                <td className="py-2.5 text-muted-foreground">
                  {new Date(order.createdAt).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                  })}
                </td>
                <td className="py-2.5 text-right font-medium">
                  {formatPrice(order.totals.grandTotal)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
