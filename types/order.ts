import type { CartLine } from "@/types/cart";

// Matches apps/core/choices.AddressType on the backend.
export type AddressType = "home" | "work" | "billing" | "shipping" | "other";

export interface ShippingAddress {
  id?: number; // backend Address id, once saved via POST /addresses/
  fullName: string;
  mobile: string;
  email?: string; // the backend address book carries no email column
  address: string;
  city: string;
  state: string;
  pincode: string;
  country: string;
  addressType: AddressType;
}

// Matches apps/orders/models.DeliveryMethod.
export type DeliveryMethod = "standard" | "express" | "scheduled";

// Matches apps/core/choices.PaymentMethod.
export type PaymentMethod = "upi" | "card" | "net_banking" | "wallet" | "cod";

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
  // Backend fulfilment state (apps/orders/models.OrderStatus), e.g. "placed",
  // "shipped", "delivered", "cancelled". statusDisplay is the human label.
  status: string;
  statusDisplay: string;
}
