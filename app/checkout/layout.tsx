"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CheckoutStepper } from "@/components/checkout/CheckoutStepper";
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
  const isSuccess = pathname === "/checkout/success";
  const currentStep = STEP_FOR_PATH[pathname];

  useEffect(() => {
    if (hydrated && !isSuccess && activeItems.length === 0) {
      router.replace("/cart");
    }
  }, [hydrated, isSuccess, activeItems.length, router]);

  if (!hydrated) return null;
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
