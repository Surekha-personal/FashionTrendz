"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Clock, Search, SearchX, Tag, TrendingUp } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatPrice } from "@/utils/format";
import { POPULAR_SEARCHES } from "@/lib/search";
import { api } from "@/lib/api";
import { apiBrandToHomeBrand } from "@/lib/apiAdapters";
import { fetchRecentlyViewed } from "@/lib/apiCatalog";
import type { ApiBrand } from "@/types/api";
import type { Brand as HomeBrand } from "@/types/home";
import type { Product } from "@/types/product";

interface SearchBarProps {
  className?: string;
  placeholder?: string;
  onSearch?: (query: string) => void;
}

interface SuggestionProduct {
  slug: string;
  title: string;
  brand: string;
  image: string;
  price: number;
}

interface CategoryMatch {
  label: string;
  href: string;
}

interface Suggestions {
  products: SuggestionProduct[];
  brands: { name: string; slug: string }[];
  categories: CategoryMatch[];
}

interface SuggestionAction {
  key: string;
  label: string;
  run: () => void;
}

const RECENT_KEY = "ft_recent_searches";
const EMPTY_SUGGESTIONS: Suggestions = { products: [], brands: [], categories: [] };

function highlight(text: string, query: string) {
  if (!query.trim()) return text;
  const index = text.toLowerCase().indexOf(query.toLowerCase());
  if (index === -1) return text;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-sm bg-accent/20 text-accent">
        {text.slice(index, index + query.length)}
      </mark>
      {text.slice(index + query.length)}
    </>
  );
}

export function SearchBar({
  className,
  placeholder = "Search for products, brands and more",
  onSearch,
}: SearchBarProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const [recentlyViewed, setRecentlyViewed] = useState<Product[]>([]);
  const [popularBrands, setPopularBrands] = useState<HomeBrand[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestions>(EMPTY_SUGGESTIONS);
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => {
    try {
      setRecent(JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]"));
    } catch {
      setRecent([]);
    }
    fetchRecentlyViewed(4)
      .then(setRecentlyViewed)
      .catch(() => setRecentlyViewed([]));
    api
      .get<ApiBrand[]>("/brands/popular/")
      .then((data) => setPopularBrands(data.slice(0, 8).map(apiBrandToHomeBrand)))
      .catch(() => setPopularBrands([]));
  }, []);

  useEffect(() => {
    setActiveIndex(-1);
    if (!value.trim()) {
      setSuggestions(EMPTY_SUGGESTIONS);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetch(`/api/search-suggestions?q=${encodeURIComponent(value)}`, {
        signal: controller.signal,
      })
        .then((res) => res.json())
        .then(setSuggestions)
        .catch(() => {});
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function commitSearch(query: string) {
    const trimmed = query.trim();
    if (!trimmed) return;
    const next = [
      trimmed,
      ...recent.filter((r) => r.toLowerCase() !== trimmed.toLowerCase()),
    ].slice(0, 6);
    setRecent(next);
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch {
      // localStorage unavailable, skip persistence
    }
    setOpen(false);
    setValue("");
    if (onSearch) onSearch(trimmed);
    else router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  function clearRecent() {
    setRecent([]);
    try {
      localStorage.removeItem(RECENT_KEY);
    } catch {
      // ignore
    }
  }

  const hasResults =
    suggestions.products.length > 0 ||
    suggestions.brands.length > 0 ||
    suggestions.categories.length > 0;
  const showIdle = !value.trim();

  const actions = useMemo<SuggestionAction[]>(() => {
    if (showIdle) {
      return [
        ...recent.map((term) => ({
          key: `recent-${term}`,
          label: term,
          run: () => commitSearch(term),
        })),
        ...POPULAR_SEARCHES.map((term) => ({
          key: `popular-${term}`,
          label: term,
          run: () => commitSearch(term),
        })),
        ...popularBrands.map((brand) => ({
          key: `brand-${brand.id}`,
          label: brand.name,
          run: () => {
            setOpen(false);
            router.push(brand.href);
          },
        })),
      ];
    }
    if (hasResults) {
      return [
        ...suggestions.categories.map((cat) => ({
          key: `cat-${cat.href}`,
          label: cat.label,
          run: () => {
            setOpen(false);
            router.push(cat.href);
          },
        })),
        ...suggestions.brands.map((brand) => ({
          key: `sbrand-${brand.slug}`,
          label: brand.name,
          run: () => {
            setOpen(false);
            router.push(`/search?brand=${brand.slug}`);
          },
        })),
        ...suggestions.products.map((product) => ({
          key: `product-${product.slug}`,
          label: product.title,
          run: () => {
            setOpen(false);
            router.push(`/product/${product.slug}`);
          },
        })),
        {
          key: "see-all",
          label: `See all results for "${value}"`,
          run: () => commitSearch(value),
        },
      ];
    }
    return [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showIdle, hasResults, recent, suggestions, value, popularBrands]);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => (actions.length ? (i + 1) % actions.length : -1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) =>
        actions.length ? (i - 1 + actions.length) % actions.length : -1
      );
    } else if (e.key === "Escape") {
      setOpen(false);
      e.currentTarget.blur();
    } else if (e.key === "Enter" && activeIndex >= 0 && actions[activeIndex]) {
      e.preventDefault();
      actions[activeIndex].run();
    }
  }

  const isActive = (key: string) => actions[activeIndex]?.key === key;

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          commitSearch(value);
        }}
      >
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          aria-label="Search"
          role="combobox"
          aria-expanded={open}
          aria-controls="search-suggestions"
          aria-activedescendant={
            activeIndex >= 0 ? `option-${actions[activeIndex]?.key}` : undefined
          }
          autoComplete="off"
          className="rounded-full bg-muted pl-9"
        />
      </form>

      {open && (
        <div
          id="search-suggestions"
          role="listbox"
          className="absolute top-full z-50 mt-2 w-full min-w-72 overflow-hidden rounded-xl border border-border bg-popover shadow-lg"
        >
          {showIdle ? (
            <div className="flex max-h-[28rem] flex-col gap-4 overflow-y-auto p-4">
              {recent.length > 0 && (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                      Recent Searches
                    </span>
                    <button
                      type="button"
                      onClick={clearRecent}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Clear
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {recent.map((term) => (
                      <button
                        key={term}
                        id={`option-recent-${term}`}
                        role="option"
                        aria-selected={isActive(`recent-${term}`)}
                        type="button"
                        onClick={() => commitSearch(term)}
                        className={cn(
                          "flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs hover:border-accent hover:text-accent",
                          isActive(`recent-${term}`) && "border-accent bg-accent/10 text-accent"
                        )}
                      >
                        <Clock className="size-3" />
                        {term}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {recentlyViewed.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    Recently Viewed
                  </span>
                  <div className="flex gap-2 overflow-x-auto">
                    {recentlyViewed.map((item) => (
                      <button
                        key={item.slug}
                        type="button"
                        onClick={() => {
                          setOpen(false);
                          router.push(`/product/${item.slug}`);
                        }}
                        className="relative size-14 shrink-0 overflow-hidden rounded-lg bg-muted"
                      >
                        <Image
                          src={item.image}
                          alt={item.name}
                          fill
                          sizes="56px"
                          className="object-cover"
                        />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2">
                <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Trending Searches
                </span>
                <div className="flex flex-wrap gap-2">
                  {POPULAR_SEARCHES.map((term) => (
                    <button
                      key={term}
                      id={`option-popular-${term}`}
                      role="option"
                      aria-selected={isActive(`popular-${term}`)}
                      type="button"
                      onClick={() => commitSearch(term)}
                      className={cn(
                        "flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs hover:border-accent hover:text-accent",
                        isActive(`popular-${term}`) && "border-accent bg-accent/10 text-accent"
                      )}
                    >
                      <TrendingUp className="size-3" />
                      {term}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Popular Brands
                </span>
                <div className="flex flex-wrap gap-2">
                  {popularBrands.map((brand) => (
                    <button
                      key={brand.id}
                      id={`option-brand-${brand.id}`}
                      role="option"
                      aria-selected={isActive(`brand-${brand.id}`)}
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        router.push(brand.href);
                      }}
                      className={cn(
                        "flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs hover:border-accent hover:text-accent",
                        isActive(`brand-${brand.id}`) && "border-accent bg-accent/10 text-accent"
                      )}
                    >
                      <Tag className="size-3" />
                      {brand.name}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : hasResults ? (
            <div className="flex max-h-[28rem] flex-col gap-4 overflow-y-auto p-4">
              {suggestions.categories.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    Categories
                  </span>
                  {suggestions.categories.map((cat) => (
                    <button
                      key={cat.href}
                      id={`option-cat-${cat.href}`}
                      role="option"
                      aria-selected={isActive(`cat-${cat.href}`)}
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        router.push(cat.href);
                      }}
                      className={cn(
                        "rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted",
                        isActive(`cat-${cat.href}`) && "bg-muted"
                      )}
                    >
                      {highlight(cat.label, value)}
                    </button>
                  ))}
                </div>
              )}
              {suggestions.brands.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    Brands
                  </span>
                  {suggestions.brands.map((brand) => (
                    <button
                      key={brand.slug}
                      id={`option-sbrand-${brand.slug}`}
                      role="option"
                      aria-selected={isActive(`sbrand-${brand.slug}`)}
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        router.push(`/search?brand=${brand.slug}`);
                      }}
                      className={cn(
                        "rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted",
                        isActive(`sbrand-${brand.slug}`) && "bg-muted"
                      )}
                    >
                      {highlight(brand.name, value)}
                    </button>
                  ))}
                </div>
              )}
              {suggestions.products.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    Products
                  </span>
                  {suggestions.products.map((product) => (
                    <button
                      key={product.slug}
                      id={`option-product-${product.slug}`}
                      role="option"
                      aria-selected={isActive(`product-${product.slug}`)}
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        router.push(`/product/${product.slug}`);
                      }}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-muted",
                        isActive(`product-${product.slug}`) && "bg-muted"
                      )}
                    >
                      <div className="relative size-10 shrink-0 overflow-hidden rounded-md bg-muted">
                        <Image
                          src={product.image}
                          alt={product.title}
                          fill
                          sizes="40px"
                          className="object-cover"
                        />
                      </div>
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate text-sm">
                          {highlight(product.title, value)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {product.brand} · {formatPrice(product.price)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                id="option-see-all"
                role="option"
                aria-selected={isActive("see-all")}
                onClick={() => commitSearch(value)}
                className={cn(
                  "rounded-lg border border-dashed border-border px-2 py-2 text-center text-sm text-muted-foreground hover:border-accent hover:text-accent",
                  isActive("see-all") && "border-accent text-accent"
                )}
              >
                See all results for &ldquo;{value}&rdquo;
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 p-6 text-center">
              <SearchX className="size-8 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">
                  No matches for &ldquo;{value}&rdquo;
                </p>
                <p className="text-xs text-muted-foreground">
                  Try a different keyword or browse trending searches below.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {POPULAR_SEARCHES.slice(0, 5).map((term) => (
                  <button
                    key={term}
                    type="button"
                    onClick={() => commitSearch(term)}
                    className="rounded-full border border-border px-3 py-1 text-xs hover:border-accent hover:text-accent"
                  >
                    {term}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setValue("")}
                aria-label="Clear search"
                className="text-xs text-muted-foreground underline hover:text-foreground"
              >
                Clear search
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
