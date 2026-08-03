import { localStore, STORAGE_KEYS } from "@/lib/storage";
import type { Order } from "@/types/order";

export function getOrders(): Order[] {
  return localStore
    .read<Order[]>(STORAGE_KEYS.orders, [])
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export function getOrderById(orderId: string): Order | undefined {
  return getOrders().find((o) => o.orderId === orderId);
}

export function saveOrder(order: Order) {
  const orders = localStore.read<Order[]>(STORAGE_KEYS.orders, []);
  localStore.write(STORAGE_KEYS.orders, [order, ...orders]);
}

export function generateOrderNumber() {
  const stamp = Date.now().toString(36).toUpperCase().slice(-6);
  const rand = Math.floor(Math.random() * 900 + 100);
  return `FT${stamp}${rand}`;
}

export function generateInvoiceNumber() {
  const year = new Date().getFullYear();
  const rand = Math.floor(Math.random() * 90000 + 10000);
  return `INV-${year}-${rand}`;
}
