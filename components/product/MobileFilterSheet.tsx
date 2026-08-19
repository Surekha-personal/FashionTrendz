"use client";

import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ProductFilters } from "@/components/product/ProductFilters";
import type { FilterFacets } from "@/types/catalog";

// Mobile-only filter entry point. Was previously a native <details> panel
// positioned `absolute` with no positioned ancestor, so it rendered detached
// from the trigger instead of anchored beneath it. A bottom sheet sidesteps
// that class of bug entirely and gives large, thumb-friendly controls.
export function MobileFilterSheet({
  facets,
  showGender,
}: {
  facets: FilterFacets;
  showGender?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 rounded-lg lg:hidden"
        >
          <SlidersHorizontal className="size-3.5" />
          Filters
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom" className="flex max-h-[85vh] flex-col rounded-t-2xl">
        <SheetHeader>
          <SheetTitle>Filters</SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <ProductFilters facets={facets} showGender={showGender} />
        </div>
        <div className="border-t border-border p-4">
          <Button className="w-full" size="lg" onClick={() => setOpen(false)}>
            Show Results
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
