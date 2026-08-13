"use client";

import Link from "next/link";
import { SearchX } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";

// ProductListingLayout is a Server Component; EmptyState is a Client
// Component whose `icon` prop is a live component reference (LucideIcon),
// which can't cross the server->client boundary as a prop. Keeping the icon
// selection inside this small client wrapper — instead of passing SearchX
// down from the server — avoids that without changing EmptyState's API or
// converting the listing layout itself to a Client Component.
export function ProductEmptyState({
  description,
  basePath,
}: {
  description?: string;
  basePath: string;
}) {
  return (
    <EmptyState
      icon={SearchX}
      title="No products found"
      description={description}
      action={
        <Button asChild variant="outline">
          <Link href={basePath}>Clear Filters</Link>
        </Button>
      }
    />
  );
}
