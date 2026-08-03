"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { Home, MapPin, Briefcase } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCheckout } from "@/context/CheckoutContext";
import { fadeInUp } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { AddressType } from "@/types/order";

const INDIAN_STATES = [
  "Andhra Pradesh", "Bihar", "Delhi", "Goa", "Gujarat", "Haryana",
  "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha",
  "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh",
  "Uttarakhand", "West Bengal",
];

const shippingSchema = z.object({
  fullName: z.string().min(2, "Enter your full name"),
  mobile: z.string().regex(/^[6-9]\d{9}$/, "Enter a valid 10-digit mobile number"),
  email: z.email("Enter a valid email address"),
  address: z.string().min(10, "Enter your complete address"),
  city: z.string().min(2, "Enter your city"),
  state: z.string().min(1, "Select your state"),
  pincode: z.string().regex(/^\d{6}$/, "Enter a valid 6-digit pincode"),
  country: z.string().min(2),
  addressType: z.enum(["home", "work", "other"]),
});

type ShippingFormValues = z.infer<typeof shippingSchema>;

const ADDRESS_TYPES: { value: AddressType; label: string; icon: typeof Home }[] = [
  { value: "home", label: "Home", icon: Home },
  { value: "work", label: "Work", icon: Briefcase },
  { value: "other", label: "Other", icon: MapPin },
];

export default function ShippingStep() {
  const router = useRouter();
  const { shippingAddress, setShippingAddress } = useCheckout();
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<ShippingFormValues>({
    resolver: zodResolver(shippingSchema),
    defaultValues: shippingAddress ?? {
      fullName: "",
      mobile: "",
      email: "",
      address: "",
      city: "",
      state: "",
      pincode: "",
      country: "India",
      addressType: "home",
    },
  });
  const addressType = watch("addressType");

  const onSubmit = (values: ShippingFormValues) => {
    setShippingAddress(values);
    router.push("/checkout/delivery");
  };

  return (
    <motion.div variants={fadeInUp} initial="hidden" animate="visible">
      <Card className="mx-auto max-w-2xl p-6 sm:p-8">
        <h2 className="mb-6 font-heading text-xl font-semibold">Shipping Address</h2>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="fullName">Full Name</Label>
              <Input id="fullName" {...register("fullName")} />
              {errors.fullName && (
                <span className="text-xs text-destructive">{errors.fullName.message}</span>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="mobile">Mobile Number</Label>
              <Input id="mobile" type="tel" {...register("mobile")} />
              {errors.mobile && (
                <span className="text-xs text-destructive">{errors.mobile.message}</span>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" {...register("email")} />
            {errors.email && (
              <span className="text-xs text-destructive">{errors.email.message}</span>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="address">Address</Label>
            <Input
              id="address"
              placeholder="Flat / House no., Building, Street, Area"
              {...register("address")}
            />
            {errors.address && (
              <span className="text-xs text-destructive">{errors.address.message}</span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="city">City</Label>
              <Input id="city" {...register("city")} />
              {errors.city && (
                <span className="text-xs text-destructive">{errors.city.message}</span>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="state">State</Label>
              <select
                id="state"
                {...register("state")}
                className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <option value="">Select state</option>
                {INDIAN_STATES.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
              {errors.state && (
                <span className="text-xs text-destructive">{errors.state.message}</span>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pincode">Pincode</Label>
              <Input id="pincode" inputMode="numeric" {...register("pincode")} />
              {errors.pincode && (
                <span className="text-xs text-destructive">{errors.pincode.message}</span>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="country">Country</Label>
            <Input id="country" {...register("country")} />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Address Type</Label>
            <div className="flex gap-2">
              {ADDRESS_TYPES.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setValue("addressType", value)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm",
                    addressType === value
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border text-foreground/80"
                  )}
                >
                  <Icon className="size-3.5" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <Button type="submit" size="lg" className="mt-2 w-full">
            Continue to Delivery
          </Button>
        </form>
      </Card>
    </motion.div>
  );
}
