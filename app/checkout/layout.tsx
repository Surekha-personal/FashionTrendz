"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CheckoutStepper } from "@/components/checkout/CheckoutStepper";
import { useAuth } from "@/context/AuthContext";
import { useCart } from "@/context/CartContext";

const STEP_FOR_PATH: Record<string, number> = {
  "/checkout": 1,
  "/checkout/delivery": 2,
  "/checkout/payment": 3,
  "/checkout/review": 4,
};

export default function CheckoutLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { activeItems, hydrated } = useCart();
  const { isAuthenticated, hydrated: authHydrated } = useAuth();
  const isSuccess = pathname === "/checkout/success";
  const currentStep = STEP_FOR_PATH[pathname];

  useEffect(() => {
    // Placing an order is an account action on the backend (apps/orders
    // requires IsAuthenticated), so checkout starts with a sign-in gate
    // rather than failing on the last step.
    if (authHydrated && !isSuccess && !isAuthenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (hydrated && !isSuccess && activeItems.length === 0) {
      router.replace("/cart");
    }
  }, [hydrated, isSuccess, activeItems.length, router, authHydrated, isAuthenticated, pathname]);

  if (!authHydrated || !hydrated) return null;
  if (!isSuccess && !isAuthenticated) return null;
  if (!isSuccess && activeItems.length === 0) return null;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      {!isSuccess && (
        <>
          <h1 className="mb-8 text-center font-heading text-2xl font-semibold sm:text-3xl">
            Checkout
          </h1>
          <CheckoutStepper currentStep={currentStep} />
        </>
      )}
      {children}
    </div>
  );
}
