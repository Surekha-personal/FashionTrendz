import { NextResponse } from "next/server";
import { products } from "@/data/catalog";
import { calculateTotals, estimatedDeliveryDate } from "@/lib/checkout";
import { generateInvoiceNumber, generateOrderNumber } from "@/lib/orders";
import type { CartLine, WishlistLine } from "@/types/cart";
import type { RecentlyViewedEntry } from "@/lib/recentlyViewed";
import type { Order, ShippingAddress } from "@/types/order";

function lineFrom(index: number, quantity = 1): CartLine {
  const p = products[index];
  const size = p.sizes[0] !== "One Size" ? p.sizes[Math.min(1, p.sizes.length - 1)] : undefined;
  const color = p.colors[0];
  return {
    lineId: [p.id, size ?? "_", color ?? "_"].join("::"),
    productId: p.id,
    slug: p.slug,
    name: p.title,
    brand: p.brand,
    image: p.images[0],
    price: p.price,
    discountedPrice: p.discountedPrice,
    size,
    color,
    quantity,
    savedForLater: false,
  };
}

function wishlistFrom(index: number, daysAgo: number): WishlistLine {
  const p = products[index];
  return {
    productId: p.id,
    slug: p.slug,
    name: p.title,
    brand: p.brand,
    image: p.images[0],
    price: p.price,
    discountedPrice: p.discountedPrice,
    addedAt: Date.now() - daysAgo * 86_400_000,
  };
}

function viewedFrom(index: number, daysAgo: number): RecentlyViewedEntry {
  const p = products[index];
  return {
    slug: p.slug,
    title: p.title,
    brand: p.brand,
    image: p.images[0],
    price: p.price,
    discountedPrice: p.discountedPrice,
    viewedAt: Date.now() - daysAgo * 3_600_000,
  };
}

const DEMO_ADDRESS: ShippingAddress = {
  fullName: "Ananya Sharma",
  mobile: "9876543210",
  email: "ananya.sharma@example.com",
  address: "221B Residency Road, Near City Mall",
  city: "Bengaluru",
  state: "Karnataka",
  pincode: "560025",
  country: "India",
  addressType: "home",
};

function pastOrder(itemIndexes: number[], daysAgo: number): Order {
  const items = itemIndexes.map((i) => lineFrom(i));
  const subtotal = items.reduce((sum, i) => sum + i.discountedPrice * i.quantity, 0);
  const productDiscount = items.reduce(
    (sum, i) => sum + (i.price - i.discountedPrice) * i.quantity,
    0
  );
  const totals = calculateTotals({
    subtotal,
    productDiscount,
    couponDiscount: 0,
    deliveryMethod: "standard",
  });
  const createdAt = new Date(Date.now() - daysAgo * 86_400_000).toISOString();
  return {
    orderId: generateOrderNumber(),
    invoiceNumber: generateInvoiceNumber(),
    createdAt,
    items,
    shippingAddress: DEMO_ADDRESS,
    deliveryMethod: "standard",
    paymentMethod: "upi",
    paymentLabel: "UPI · ananya.sharma@okhdfcbank",
    totals,
    estimatedDelivery: estimatedDeliveryDate("standard"),
  };
}

export async function GET() {
  const cart: CartLine[] = [lineFrom(4, 1), lineFrom(18, 2), lineFrom(32, 1)];
  const wishlist: WishlistLine[] = [
    wishlistFrom(7, 1),
    wishlistFrom(21, 2),
    wishlistFrom(45, 4),
    wishlistFrom(60, 6),
  ];
  const recentlyViewed: RecentlyViewedEntry[] = [12, 27, 39, 51, 63, 8].map((i, idx) =>
    viewedFrom(i, idx)
  );
  const orders: Order[] = [
    pastOrder([70, 71], 12),
    pastOrder([82], 28),
  ];

  return NextResponse.json({
    user: { name: "Ananya Sharma", email: "ananya.sharma@example.com" },
    cart,
    wishlist,
    recentlyViewed,
    orders,
  });
}
