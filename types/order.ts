import type { CartLine } from "@/types/cart";

export type AddressType = "home" | "work" | "other";

export interface ShippingAddress {
  fullName: string;
  mobile: string;
  email: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  country: string;
  addressType: AddressType;
}

export type DeliveryMethod = "standard" | "express" | "sameday";

export type PaymentMethod =
  | "upi"
  | "card"
  | "debit"
  | "netbanking"
  | "wallet"
  | "cod"
  | "giftcard";

export interface OrderTotals {
  subtotal: number;
  productDiscount: number;
  couponCode?: string;
  couponDiscount: number;
  gst: number;
  shipping: number;
  platformFee: number;
  grandTotal: number;
}

export interface Order {
  orderId: string;
  invoiceNumber: string;
  createdAt: string;
  items: CartLine[];
  shippingAddress: ShippingAddress;
  deliveryMethod: DeliveryMethod;
  paymentMethod: PaymentMethod;
  paymentLabel: string;
  totals: OrderTotals;
  estimatedDelivery: string;
}
