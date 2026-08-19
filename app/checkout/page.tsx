"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { Home, MapPin, Briefcase, Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCheckout } from "@/context/CheckoutContext";
import { api, ApiError } from "@/lib/api";
import { apiAddressToShipping } from "@/lib/apiAdapters";
import { fadeInUp } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { ApiAddress } from "@/types/api";

const INDIAN_STATES = [
  "Andhra Pradesh", "Bihar", "Delhi", "Goa", "Gujarat", "Haryana",
  "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha",
  "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh",
  "Uttarakhand", "West Bengal",
];

const shippingSchema = z.object({
  fullName: z.string().min(2, "Enter your full name"),
  mobile: z.string().regex(/^[6-9]\d{9}$/, "Enter a valid 10-digit mobile number"),
  address: z.string().min(10, "Enter your complete address"),
  city: z.string().min(2, "Enter your city"),
  state: z.string().min(1, "Select your state"),
  pincode: z.string().regex(/^\d{6}$/, "Enter a valid 6-digit pincode"),
  country: z.string().min(2),
  addressType: z.enum(["home", "work", "other"]),
});

type ShippingFormValues = z.infer<typeof shippingSchema>;

const ADDRESS_TYPES: { value: ShippingFormValues["addressType"]; label: string; icon: typeof Home }[] = [
  { value: "home", label: "Home", icon: Home },
  { value: "work", label: "Work", icon: Briefcase },
  { value: "other", label: "Other", icon: MapPin },
];

export default function ShippingStep() {
  const router = useRouter();
  const { shippingAddress, setShippingAddress } = useCheckout();
  const [savedAddresses, setSavedAddresses] = useState<ApiAddress[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    // /addresses/ is paginated (StandardPagination, 20/page, 100 max) — request
    // the max page size so a customer with more than the default page's worth
    // of saved addresses doesn't have older ones silently disappear.
    api
      .get<ApiAddress[]>("/addresses/?page_size=100")
      .then((addresses) => {
        setSavedAddresses(addresses);
        setShowForm(addresses.length === 0);
      })
      .catch(() => {
        setSavedAddresses([]);
        setShowForm(true);
      });
  }, []);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<ShippingFormValues>({
    resolver: zodResolver(shippingSchema),
    defaultValues: {
      fullName: "",
      mobile: "",
      address: "",
      city: "",
      state: "",
      pincode: "",
      country: "India",
      addressType: "home",
    },
  });
  const addressType = watch("addressType");

  const selectAddress = (address: ApiAddress) => {
    setShippingAddress(apiAddressToShipping(address));
    router.push("/checkout/delivery");
  };

  const onSubmit = async (values: ShippingFormValues) => {
    setSubmitting(true);
    try {
      const created = await api.post<ApiAddress>("/addresses/", {
        full_name: values.fullName,
        mobile: values.mobile,
        address_line_1: values.address,
        address_line_2: "",
        city: values.city,
        state: values.state,
        postal_code: values.pincode,
        country: values.country,
        is_default: (savedAddresses?.length ?? 0) === 0,
      });
      setShippingAddress(apiAddressToShipping(created));
      router.push("/checkout/delivery");
    } catch (err) {
      // Field errors from the backend surface inline via react-hook-form's
      // own validation message area is overkill here — a toast is enough
      // for a form this short.
      if (err instanceof ApiError) {
        alert(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div variants={fadeInUp} initial="hidden" animate="visible">
      <Card className="mx-auto max-w-2xl p-6 sm:p-8">
        <h2 className="mb-6 font-heading text-xl font-semibold">Shipping Address</h2>

        {savedAddresses && savedAddresses.length > 0 && (
          <div className="mb-6 flex flex-col gap-3">
            {savedAddresses.map((addr) => (
              <button
                key={addr.id}
                type="button"
                onClick={() => selectAddress(addr)}
                className={cn(
                  "flex items-start justify-between gap-3 rounded-xl border p-4 text-left transition-colors",
                  shippingAddress?.id === addr.id
                    ? "border-accent bg-accent/5"
                    : "border-border hover:border-foreground/30"
                )}
              >
                <div className="flex flex-col gap-0.5 text-sm">
                  <span className="font-medium">
                    {addr.full_name} · {addr.mobile}
                  </span>
                  <span className="text-muted-foreground">
                    {[addr.address_line_1, addr.address_line_2].filter(Boolean).join(", ")},{" "}
                    {addr.city}, {addr.state} - {addr.postal_code}
                  </span>
                </div>
                {shippingAddress?.id === addr.id && (
                  <Check className="size-4 shrink-0 text-accent" />
                )}
              </button>
            ))}
            {!showForm && (
              <Button variant="outline" onClick={() => setShowForm(true)}>
                Add a new address
              </Button>
            )}
          </div>
        )}

        {showForm && (
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

          <Button
            type="submit"
            size="lg"
            className="mt-2 h-12 w-full text-base font-semibold"
            disabled={submitting}
          >
            {submitting ? "Saving…" : "Continue to Delivery"}
          </Button>
        </form>
        )}
      </Card>
    </motion.div>
  );
}
