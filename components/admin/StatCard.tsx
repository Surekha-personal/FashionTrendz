import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  delta?: string;
  trend?: "up" | "down";
  icon: LucideIcon;
}

export function StatCard({ label, value, delta, trend = "up", icon: Icon }: StatCardProps) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="flex size-9 items-center justify-center rounded-full bg-accent/10 text-accent">
          <Icon className="size-4" />
        </span>
      </div>
      <span className="font-heading text-2xl font-semibold">{value}</span>
      {delta && (
        <span
          className={cn(
            "text-xs font-medium",
            trend === "up" ? "text-emerald-600" : "text-destructive"
          )}
        >
          {trend === "up" ? "↑" : "↓"} {delta} vs last month
        </span>
      )}
    </Card>
  );
}
