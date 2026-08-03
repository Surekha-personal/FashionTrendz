import type { DeliveryMethod, OrderTotals, PaymentMethod } from "@/types/order";

export interface Coupon {
  code: string;
  description: string;
  type: "percent" | "flat";
  value: number;
  minOrder: number;
  maxDiscount?: number;
}

export const COUPONS: Record<string, Coupon> = {
  WELCOME10: {
    code: "WELCOME10",
    description: "10% off on your first order",
    type: "percent",
    value: 10,
    minOrder: 999,
    maxDiscount: 1000,
  },
  FLAT500: {
    code: "FLAT500",
    description: "Flat ₹500 off on orders above ₹2,999",
    type: "flat",
    value: 500,
    minOrder: 2999,
  },
  FASHION20: {
    code: "FASHION20",
    description: "20% off on fashion picks",
    type: "percent",
    value: 20,
    minOrder: 1999,
    maxDiscount: 1500,
  },
  LUXE15: {
    code: "LUXE15",
    description: "15% off on luxury orders above ₹5,000",
    type: "percent",
    value: 15,
    minOrder: 5000,
    maxDiscount: 3000,
  },
};

export interface CouponResult {
  valid: boolean;
  discount: number;
  message: string;
}

export function validateCoupon(code: string, subtotal: number): CouponResult {
  const coupon = COUPONS[code.trim().toUpperCase()];
  if (!coupon) {
    return { valid: false, discount: 0, message: "Invalid coupon code" };
  }
  if (subtotal < coupon.minOrder) {
    return {
      valid: false,
      discount: 0,
      message: `Add items worth ₹${coupon.minOrder} or more to use this coupon`,
    };
  }
  const raw = coupon.type === "percent" ? (subtotal * coupon.value) / 100 : coupon.value;
  const discount = Math.round(coupon.maxDiscount ? Math.min(raw, coupon.maxDiscount) : raw);
  return { valid: true, discount, message: coupon.description };
}

export interface DeliveryOption {
  id: DeliveryMethod;
  label: string;
  description: string;
  etaLabel: string;
  etaDays: number;
}

export const DELIVERY_OPTIONS: DeliveryOption[] = [
  {
    id: "standard",
    label: "Standard Delivery",
    description: "Reliable delivery, free above ₹1,999",
    etaLabel: "5-7 business days",
    etaDays: 6,
  },
  {
    id: "express",
    label: "Express Delivery",
    description: "Faster delivery for when you need it sooner",
    etaLabel: "2-3 business days",
    etaDays: 3,
  },
  {
    id: "sameday",
    label: "Same Day Delivery",
    description: "Order before 12 PM for delivery today",
    etaLabel: "Today, by 9 PM",
    etaDays: 0,
  },
];

export const PAYMENT_METHODS: { id: PaymentMethod; label: string }[] = [
  { id: "upi", label: "UPI" },
  { id: "card", label: "Credit Card" },
  { id: "debit", label: "Debit Card" },
  { id: "netbanking", label: "Net Banking" },
  { id: "wallet", label: "Wallet" },
  { id: "cod", label: "Cash on Delivery" },
  { id: "giftcard", label: "Gift Card" },
];

const FREE_SHIPPING_THRESHOLD = 1999;
const STANDARD_SHIPPING_FEE = 99;
const EXPRESS_SHIPPING_FEE = 149;
const SAMEDAY_SHIPPING_FEE = 249;
export const PLATFORM_FEE = 20;
const GST_RATE = 0.05;

export function shippingFeeFor(method: DeliveryMethod, amountAfterDiscount: number) {
  if (method === "express") return EXPRESS_SHIPPING_FEE;
  if (method === "sameday") return SAMEDAY_SHIPPING_FEE;
  return amountAfterDiscount >= FREE_SHIPPING_THRESHOLD ? 0 : STANDARD_SHIPPING_FEE;
}

export function calculateTotals(params: {
  subtotal: number;
  productDiscount: number;
  couponCode?: string;
  couponDiscount: number;
  deliveryMethod: DeliveryMethod;
}): OrderTotals {
  const { subtotal, productDiscount, couponCode, couponDiscount, deliveryMethod } = params;
  const amountAfterDiscount = Math.max(subtotal - couponDiscount, 0);
  const shipping = shippingFeeFor(deliveryMethod, amountAfterDiscount);
  const gst = Math.round(amountAfterDiscount * GST_RATE);
  const grandTotal = amountAfterDiscount + gst + shipping + PLATFORM_FEE;

  return {
    subtotal,
    productDiscount,
    couponCode,
    couponDiscount,
    gst,
    shipping,
    platformFee: PLATFORM_FEE,
    grandTotal,
  };
}

export function estimatedDeliveryDate(method: DeliveryMethod) {
  const option = DELIVERY_OPTIONS.find((o) => o.id === method) ?? DELIVERY_OPTIONS[0];
  const date = new Date();
  date.setDate(date.getDate() + option.etaDays);
  return date.toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}
