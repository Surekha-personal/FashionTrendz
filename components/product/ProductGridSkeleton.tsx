import { Skeleton } from "@/components/ui/skeleton";
import { ProductCardSkeleton } from "@/components/product/ProductCardSkeleton";

export function ProductGridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Skeleton className="mb-4 h-4 w-64" />
      <Skeleton className="mb-6 h-8 w-48" />
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[240px_1fr]">
        <div className="hidden flex-col gap-4 lg:flex">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-9 w-40" />
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-6 xl:grid-cols-4">
            {Array.from({ length: count }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
