import { Card } from "@/components/ui/card";

const MONTHLY_SALES = [
  { month: "Jan", value: 62 },
  { month: "Feb", value: 58 },
  { month: "Mar", value: 71 },
  { month: "Apr", value: 66 },
  { month: "May", value: 78 },
  { month: "Jun", value: 74 },
  { month: "Jul", value: 85 },
  { month: "Aug", value: 91 },
  { month: "Sep", value: 83 },
  { month: "Oct", value: 96 },
  { month: "Nov", value: 88 },
  { month: "Dec", value: 100 },
];

export function SalesOverviewChart() {
  const max = Math.max(...MONTHLY_SALES.map((m) => m.value));

  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="font-heading text-lg font-semibold">Sales Overview</h2>
        <span className="text-xs text-muted-foreground">Last 12 months</span>
      </div>
      <div className="flex h-40 items-end gap-2 sm:h-48">
        {MONTHLY_SALES.map((entry) => (
          <div key={entry.month} className="flex flex-1 flex-col items-center gap-2">
            <div className="flex h-full w-full items-end">
              <div
                className="w-full rounded-t-md bg-accent/80 transition-all hover:bg-accent"
                style={{ height: `${(entry.value / max) * 100}%` }}
                title={`${entry.month}: index ${entry.value}`}
              />
            </div>
            <span className="text-[10px] text-muted-foreground">{entry.month}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
