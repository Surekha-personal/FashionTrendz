"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { sessionStore, STORAGE_KEYS } from "@/lib/storage";
import type { DeliveryMethod, PaymentMethod, ShippingAddress } from "@/types/order";

interface CheckoutDraft {
  shippingAddress: ShippingAddress | null;
  deliveryMethod: DeliveryMethod | null;
  paymentMethod: PaymentMethod | null;
  paymentLabel: string;
  couponCode: string | null;
  couponDiscount: number;
}

const EMPTY_DRAFT: CheckoutDraft = {
  shippingAddress: null,
  deliveryMethod: null,
  paymentMethod: null,
  paymentLabel: "",
  couponCode: null,
  couponDiscount: 0,
};

interface CheckoutContextValue extends CheckoutDraft {
  hydrated: boolean;
  setShippingAddress: (address: ShippingAddress) => void;
  setDeliveryMethod: (method: DeliveryMethod) => void;
  setPayment: (method: PaymentMethod, label: string) => void;
  setCoupon: (code: string | null, discount: number) => void;
  resetCheckout: () => void;
}

const CheckoutContext = createContext<CheckoutContextValue | null>(null);

export function CheckoutProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<CheckoutDraft>(EMPTY_DRAFT);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setDraft(sessionStore.read(STORAGE_KEYS.checkoutDraft, EMPTY_DRAFT));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) sessionStore.write(STORAGE_KEYS.checkoutDraft, draft);
  }, [draft, hydrated]);

  const value = useMemo<CheckoutContextValue>(
    () => ({
      ...draft,
      hydrated,
      setShippingAddress: (address) =>
        setDraft((prev) => ({ ...prev, shippingAddress: address })),
      setDeliveryMethod: (method) =>
        setDraft((prev) => ({ ...prev, deliveryMethod: method })),
      setPayment: (method, label) =>
        setDraft((prev) => ({ ...prev, paymentMethod: method, paymentLabel: label })),
      setCoupon: (code, discount) =>
        setDraft((prev) => ({ ...prev, couponCode: code, couponDiscount: discount })),
      resetCheckout: () => {
        setDraft(EMPTY_DRAFT);
        sessionStore.remove(STORAGE_KEYS.checkoutDraft);
      },
    }),
    [draft, hydrated]
  );

  return (
    <CheckoutContext.Provider value={value}>{children}</CheckoutContext.Provider>
  );
}

export function useCheckout() {
  const ctx = useContext(CheckoutContext);
  if (!ctx) throw new Error("useCheckout must be used within a CheckoutProvider");
  return ctx;
}
