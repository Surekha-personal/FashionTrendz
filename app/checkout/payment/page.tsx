"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Banknote,
  CreditCard,
  Gift,
  Landmark,
  Smartphone,
  Wallet,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCheckout } from "@/context/CheckoutContext";
import { PAYMENT_METHODS } from "@/lib/checkout";
import { fadeInUp } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { PaymentMethod } from "@/types/order";

const PAYMENT_ICONS: Record<PaymentMethod, typeof CreditCard> = {
  upi: Smartphone,
  card: CreditCard,
  debit: CreditCard,
  netbanking: Landmark,
  wallet: Wallet,
  cod: Banknote,
  giftcard: Gift,
};

const BANKS = ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank", "Kotak Mahindra Bank"];
const WALLETS = ["Paytm", "PhonePe", "Amazon Pay", "Mobikwik"];

export default function PaymentStep() {
  const router = useRouter();
  const { deliveryMethod, setPayment, hydrated } = useCheckout();
  const [method, setMethod] = useState<PaymentMethod>("upi");
  const [upiId, setUpiId] = useState("");
  const [cardNumber, setCardNumber] = useState("");
  const [cardExpiry, setCardExpiry] = useState("");
  const [cardCvv, setCardCvv] = useState("");
  const [bank, setBank] = useState(BANKS[0]);
  const [wallet, setWallet] = useState(WALLETS[0]);
  const [giftCardCode, setGiftCardCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hydrated && !deliveryMethod) router.replace("/checkout/delivery");
  }, [hydrated, deliveryMethod, router]);

  if (!deliveryMethod) return null;

  const onContinue = () => {
    setError(null);
    let label = "";

    if (method === "upi") {
      if (!/^[\w.-]+@[\w.-]+$/.test(upiId)) {
        setError("Enter a valid UPI ID, e.g. name@bank");
        return;
      }
      label = `UPI · ${upiId}`;
    } else if (method === "card" || method === "debit") {
      if (!/^\d{16}$/.test(cardNumber.replace(/\s/g, ""))) {
        setError("Enter a valid 16-digit card number");
        return;
      }
      if (!/^\d{2}\/\d{2}$/.test(cardExpiry)) {
        setError("Enter expiry as MM/YY");
        return;
      }
      if (!/^\d{3}$/.test(cardCvv)) {
        setError("Enter a valid 3-digit CVV");
        return;
      }
      const last4 = cardNumber.replace(/\s/g, "").slice(-4);
      label = `${method === "card" ? "Credit" : "Debit"} Card ending in ${last4}`;
    } else if (method === "netbanking") {
      label = `Net Banking · ${bank}`;
    } else if (method === "wallet") {
      label = `Wallet · ${wallet}`;
    } else if (method === "giftcard") {
      if (giftCardCode.trim().length < 6) {
        setError("Enter a valid gift card code");
        return;
      }
      label = `Gift Card · ${giftCardCode.trim().toUpperCase()}`;
    } else {
      label = "Cash on Delivery";
    }

    setPayment(method, label);
    router.push("/checkout/review");
  };

  return (
    <motion.div variants={fadeInUp} initial="hidden" animate="visible">
      <Card className="mx-auto max-w-2xl p-6 sm:p-8">
        <h2 className="mb-6 font-heading text-xl font-semibold">Payment Method</h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PAYMENT_METHODS.map(({ id, label }) => {
            const Icon = PAYMENT_ICONS[id];
            const isSelected = method === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setMethod(id);
                  setError(null);
                }}
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-xl border p-3 text-center text-xs font-medium transition-colors",
                  isSelected
                    ? "border-accent bg-accent/5 text-accent"
                    : "border-border text-foreground/80 hover:border-foreground/30"
                )}
              >
                <Icon className="size-5" />
                {label}
              </button>
            );
          })}
        </div>

        <div className="mt-6 flex flex-col gap-4">
          {method === "upi" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="upi">UPI ID</Label>
              <Input
                id="upi"
                placeholder="yourname@okhdfcbank"
                value={upiId}
                onChange={(e) => setUpiId(e.target.value)}
              />
            </div>
          )}

          {(method === "card" || method === "debit") && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <Label htmlFor="cardNumber">Card Number</Label>
                <Input
                  id="cardNumber"
                  placeholder="1234 5678 9012 3456"
                  inputMode="numeric"
                  maxLength={19}
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="expiry">Expiry (MM/YY)</Label>
                <Input
                  id="expiry"
                  placeholder="MM/YY"
                  maxLength={5}
                  value={cardExpiry}
                  onChange={(e) => setCardExpiry(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cvv">CVV</Label>
                <Input
                  id="cvv"
                  placeholder="123"
                  inputMode="numeric"
                  maxLength={3}
                  value={cardCvv}
                  onChange={(e) => setCardCvv(e.target.value)}
                />
              </div>
            </div>
          )}

          {method === "netbanking" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bank">Select Bank</Label>
              <select
                id="bank"
                value={bank}
                onChange={(e) => setBank(e.target.value)}
                className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {BANKS.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </div>
          )}

          {method === "wallet" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="wallet">Select Wallet</Label>
              <select
                id="wallet"
                value={wallet}
                onChange={(e) => setWallet(e.target.value)}
                className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {WALLETS.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>
          )}

          {method === "giftcard" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="giftcard">Gift Card Code</Label>
              <Input
                id="giftcard"
                placeholder="FTGIFT-XXXXXX"
                value={giftCardCode}
                onChange={(e) => setGiftCardCode(e.target.value)}
              />
            </div>
          )}

          {method === "cod" && (
            <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
              Pay with cash when your order is delivered.
            </p>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <Button size="lg" className="mt-6 w-full" onClick={onContinue}>
          Continue to Review
        </Button>
      </Card>
    </motion.div>
  );
}
