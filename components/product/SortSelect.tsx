"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { SortKey } from "@/types/catalog";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "newest", label: "Newest First" },
  { value: "popularity", label: "Popularity" },
  { value: "price-asc", label: "Price: Low to High" },
  { value: "price-desc", label: "Price: High to Low" },
  { value: "discount", label: "Discount" },
  { value: "rating", label: "Top Rated" },
];

export function SortSelect() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = (searchParams.get("sort") as SortKey) ?? "newest";

  return (
    <select
      aria-label="Sort by"
      value={current}
      onChange={(e) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set("sort", e.target.value);
        params.delete("page");
        router.push(`${pathname}?${params.toString()}`, { scroll: false });
      }}
      className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {SORT_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          Sort: {option.label}
        </option>
      ))}
    </select>
  );
}
