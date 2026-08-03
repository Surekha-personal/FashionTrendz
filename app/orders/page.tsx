"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { Package } from "lucide-react";
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
import { EmptyState } from "@/components/common/EmptyState";
import { getOrders } from "@/lib/orders";
import { formatPrice } from "@/utils/format";
import { fadeInUp, staggerContainer } from "@/lib/motion";
import type { Order } from "@/types/order";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setOrders(getOrders());
    setHydrated(true);
  }, []);

  if (!hydrated) return null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">Home</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>My Orders</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <h1 className="mb-6 font-heading text-2xl font-semibold sm:text-3xl">My Orders</h1>

      {orders.length === 0 ? (
        <EmptyState
          icon={Package}
          title="No orders yet"
          description="Your placed orders will show up here."
          action={
            <Button asChild>
              <Link href="/">Start Shopping</Link>
            </Button>
          }
        />
      ) : (
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="flex flex-col gap-4"
        >
          {orders.map((order) => (
            <motion.div key={order.orderId} variants={fadeInUp}>
              <Link href={`/orders/${order.orderId}`}>
                <Card className="flex flex-col gap-4 p-5 transition-shadow hover:shadow-md sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-4">
                    <div className="flex -space-x-3">
                      {order.items.slice(0, 3).map((item) => (
                        <div
                          key={item.lineId}
                          className="relative size-14 shrink-0 overflow-hidden rounded-lg border-2 border-background bg-muted"
                        >
                          <Image
                            src={item.image}
                            alt={item.name}
                            fill
                            className="object-cover"
                          />
                        </div>
                      ))}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{order.orderId}</span>
                      <span className="text-xs text-muted-foreground">
                        Placed on{" "}
                        {new Date(order.createdAt).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {order.items.length} {order.items.length === 1 ? "item" : "items"}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="secondary">Confirmed</Badge>
                    <span className="text-sm font-semibold">
                      {formatPrice(order.totals.grandTotal)}
                    </span>
                  </div>
                </Card>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
