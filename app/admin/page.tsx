import type { Metadata } from "next";
import Image from "next/image";
import { Package, ShoppingCart, IndianRupee, Users } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/admin/StatCard";
import { SalesOverviewChart } from "@/components/admin/SalesOverviewChart";
import { AdminOrdersPanel } from "@/components/admin/AdminOrdersPanel";
import { products, brands, categories } from "@/data/catalog";
import { formatPrice } from "@/utils/format";

export const metadata: Metadata = {
  title: "Admin Dashboard | Fashion Trendz",
  robots: { index: false, follow: false },
};

export default function AdminPage() {
  const recentProducts = products.slice(0, 6);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col gap-1">
        <Badge variant="outline" className="w-fit">
          Admin Preview
        </Badge>
        <h1 className="font-heading text-2xl font-semibold sm:text-3xl">
          Dashboard
        </h1>
        <p className="text-sm text-muted-foreground">
          A frontend-only preview of what the Fashion Trendz team would see.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Products"
          value={products.length.toLocaleString("en-IN")}
          delta="4.2%"
          icon={Package}
        />
        <StatCard
          label="Total Orders"
          value="1,284"
          delta="8.1%"
          icon={ShoppingCart}
        />
        <StatCard
          label="Revenue"
          value={formatPrice(1842600)}
          delta="12.6%"
          icon={IndianRupee}
        />
        <StatCard label="Customers" value="3,410" delta="5.4%" icon={Users} />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
        <SalesOverviewChart />
        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 font-heading text-lg font-semibold">Catalog Snapshot</h2>
          <div className="flex flex-col gap-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Categories</span>
              <span className="font-medium">{categories.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Brands</span>
              <span className="font-medium">{brands.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Products On Sale</span>
              <span className="font-medium">
                {products.filter((p) => p.discount > 0).length}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Out of Stock</span>
              <span className="font-medium">
                {products.filter((p) => p.stock === 0).length}
              </span>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <AdminOrdersPanel />

        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 font-heading text-lg font-semibold">Recent Products</h2>
          <div className="flex flex-col gap-3">
            {recentProducts.map((product) => (
              <div key={product.id} className="flex items-center gap-3">
                <div className="relative size-11 shrink-0 overflow-hidden rounded-lg bg-muted">
                  <Image
                    src={product.images[0]}
                    alt={product.title}
                    fill
                    className="object-cover"
                  />
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{product.title}</span>
                  <span className="text-xs text-muted-foreground">{product.brand}</span>
                </div>
                <span className="text-sm font-semibold">
                  {formatPrice(product.discountedPrice)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
