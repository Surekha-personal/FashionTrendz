"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const newsletterSchema = z.object({
  email: z.email("Enter a valid email address"),
});

type NewsletterValues = z.infer<typeof newsletterSchema>;

export function NewsletterForm({ className }: { className?: string }) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<NewsletterValues>({
    resolver: zodResolver(newsletterSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = async (values: NewsletterValues) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    toast.success(`Subscribed with ${values.email}`);
    reset();
  };

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className={cn("flex flex-col gap-2", className)}
    >
      <div className="flex gap-2">
        <Input
          type="email"
          placeholder="Enter your email"
          aria-label="Email address"
          aria-invalid={!!errors.email}
          className="bg-background"
          {...register("email")}
        />
        <Button type="submit" disabled={isSubmitting}>
          Subscribe
        </Button>
      </div>
      {errors.email && (
        <span className="text-xs text-destructive">{errors.email.message}</span>
      )}
    </form>
  );
}
