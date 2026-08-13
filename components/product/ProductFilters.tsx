"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { X } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { parseFilterState } from "@/lib/filters";
import { cn } from "@/lib/utils";
import type { FilterFacets, Gender } from "@/types/catalog";

const DISCOUNT_TIERS = [10, 20, 30, 40, 50];
const RATING_TIERS = [4, 3];
const GENDER_LABELS: Record<Gender, string> = {
  women: "Women",
  men: "Men",
  kids: "Kids",
  unisex: "Unisex",
};

function titleCase(value: string) {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ProductFilters({
  facets,
  showGender = true,
}: {
  facets: FilterFacets;
  showGender?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = useMemo(
    () => parseFilterState(Object.fromEntries(searchParams.entries())),
    [searchParams]
  );

  const navigate = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const params = new URLSearchParams(searchParams.toString());
      mutate(params);
      params.delete("page");
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const toggleCsv = (key: string, value: string, current: string[]) => {
    navigate((params) => {
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      if (next.length) params.set(key, next.join(","));
      else params.delete(key);
    });
  };

  const setSingle = (key: string, value: string | undefined) => {
    navigate((params) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });
  };

  const clearAll = () => router.push(pathname, { scroll: false });

  const activeChips: { key: string; label: string; onRemove: () => void }[] = [
    ...state.brands.map((slug) => ({
      key: `brand-${slug}`,
      label: facets.brandNames?.[slug] ?? slug,
      onRemove: () => toggleCsv("brand", slug, state.brands),
    })),
    ...state.colors.map((c) => ({
      key: `color-${c}`,
      label: c,
      onRemove: () => toggleCsv("color", c, state.colors),
    })),
    ...state.sizes.map((s) => ({
      key: `size-${s}`,
      label: s,
      onRemove: () => toggleCsv("size", s, state.sizes),
    })),
    ...state.genders.map((g) => ({
      key: `gender-${g}`,
      label: GENDER_LABELS[g as Gender] ?? g,
      onRemove: () => toggleCsv("gender", g, state.genders),
    })),
    ...(state.minDiscount
      ? [
          {
            key: "discount",
            label: `${state.minDiscount}% off or more`,
            onRemove: () => setSingle("minDiscount", undefined),
          },
        ]
      : []),
    ...(state.minRating
      ? [
          {
            key: "rating",
            label: `${state.minRating}★ & up`,
            onRemove: () => setSingle("minRating", undefined),
          },
        ]
      : []),
    ...(state.inStockOnly
      ? [
          {
            key: "stock",
            label: "In Stock",
            onRemove: () => setSingle("inStock", undefined),
          },
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-4">
      {activeChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {activeChips.map((chip) => (
            <Badge key={chip.key} variant="secondary" className="gap-1 pr-1">
              {chip.label}
              <button
                type="button"
                onClick={chip.onRemove}
                aria-label={`Remove ${chip.label} filter`}
                className="rounded-full p-0.5 hover:bg-foreground/10"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          <Button variant="ghost" size="sm" onClick={clearAll} className="h-6 text-xs">
            Clear All
          </Button>
        </div>
      )}

      <Accordion
        type="multiple"
        defaultValue={["price", "brand", "gender", "discount"]}
        className="w-full"
      >
        <AccordionItem value="price">
          <AccordionTrigger>Price</AccordionTrigger>
          <AccordionContent>
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                navigate((params) => {
                  const min = form.get("minPrice");
                  const max = form.get("maxPrice");
                  if (min) params.set("minPrice", String(min));
                  else params.delete("minPrice");
                  if (max) params.set("maxPrice", String(max));
                  else params.delete("maxPrice");
                });
              }}
            >
              <Input
                type="number"
                name="minPrice"
                placeholder={String(facets.priceMin)}
                defaultValue={state.minPrice ?? ""}
                className="h-8"
              />
              <span className="text-muted-foreground">-</span>
              <Input
                type="number"
                name="maxPrice"
                placeholder={String(facets.priceMax)}
                defaultValue={state.maxPrice ?? ""}
                className="h-8"
              />
              <Button type="submit" size="sm" variant="secondary">
                Go
              </Button>
            </form>
          </AccordionContent>
        </AccordionItem>

        {showGender && facets.genders.length > 1 && (
          <AccordionItem value="gender">
            <AccordionTrigger>Gender</AccordionTrigger>
            <AccordionContent>
              <div className="flex flex-col gap-2.5">
                {facets.genders.map((g) => (
                  <Label key={g} className="flex items-center gap-2 font-normal">
                    <Checkbox
                      checked={state.genders.includes(g)}
                      onCheckedChange={() => toggleCsv("gender", g, state.genders)}
                    />
                    {GENDER_LABELS[g]}
                  </Label>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        )}

        <AccordionItem value="discount">
          <AccordionTrigger>Discount</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-2.5">
              {DISCOUNT_TIERS.map((tier) => (
                <Label key={tier} className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={state.minDiscount === tier}
                    onCheckedChange={() =>
                      setSingle(
                        "minDiscount",
                        state.minDiscount === tier ? undefined : String(tier)
                      )
                    }
                  />
                  {tier}% off or more
                </Label>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="rating">
          <AccordionTrigger>Rating</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-2.5">
              {RATING_TIERS.map((tier) => (
                <Label key={tier} className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={state.minRating === tier}
                    onCheckedChange={() =>
                      setSingle(
                        "minRating",
                        state.minRating === tier ? undefined : String(tier)
                      )
                    }
                  />
                  {tier}★ & up
                </Label>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="brand">
          <AccordionTrigger>Brand</AccordionTrigger>
          <AccordionContent>
            <div className="flex max-h-48 flex-col gap-2.5 overflow-y-auto pr-2">
              {facets.brands.map((slug) => (
                <Label key={slug} className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={state.brands.includes(slug)}
                    onCheckedChange={() => toggleCsv("brand", slug, state.brands)}
                  />
                  {facets.brandNames?.[slug] ?? slug}
                </Label>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="color">
          <AccordionTrigger>Color</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-wrap gap-2">
              {facets.colors.map((color) => (
                <button
                  key={color}
                  type="button"
                  onClick={() => toggleCsv("color", color, state.colors)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    state.colors.includes(color)
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border text-foreground/80"
                  )}
                >
                  {color}
                </button>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="size">
          <AccordionTrigger>Size</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-wrap gap-2">
              {facets.sizes.map((size) => (
                <button
                  key={size}
                  type="button"
                  onClick={() => toggleCsv("size", size, state.sizes)}
                  className={cn(
                    "min-w-9 rounded-lg border px-2.5 py-1 text-xs",
                    state.sizes.includes(size)
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border text-foreground/80"
                  )}
                >
                  {size}
                </button>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="material">
          <AccordionTrigger>Material</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-2.5">
              {facets.materials.map((material) => (
                <Label key={material} className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={state.materials.includes(material)}
                    onCheckedChange={() =>
                      toggleCsv("material", material, state.materials)
                    }
                  />
                  {material}
                </Label>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="occasion">
          <AccordionTrigger>Occasion</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-2.5">
              {facets.occasions.map((occasion) => (
                <Label key={occasion} className="flex items-center gap-2 font-normal">
                  <Checkbox
                    checked={state.occasions.includes(occasion)}
                    onCheckedChange={() =>
                      toggleCsv("occasion", occasion, state.occasions)
                    }
                  />
                  {titleCase(occasion)}
                </Label>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="availability">
          <AccordionTrigger>Availability</AccordionTrigger>
          <AccordionContent>
            <Label className="flex items-center gap-2 font-normal">
              <Checkbox
                checked={state.inStockOnly}
                onCheckedChange={() =>
                  setSingle("inStock", state.inStockOnly ? undefined : "1")
                }
              />
              In Stock Only
            </Label>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
