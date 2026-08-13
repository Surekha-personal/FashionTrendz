// Maps backend API payloads (types/api.ts) onto the view models the existing
// UI components already render (types/product.ts, types/cart.ts,
// types/order.ts). Keeping the adapters in one place means ProductCard,
// CartLineItem, WishlistCard, the order pages etc. never need to know the
// wire shape changed.

import type {
  ApiAddress,
  ApiAddressSnapshot,
  ApiBrand,
  ApiCartItem,
  ApiCategory,
  ApiCollection,
  ApiOrderDetail,
  ApiOrderSummary,
  ApiProductCard,
  ApiProductDetail,
  ApiWishlistItem,
} from "@/types/api";
import type { CartLine, WishlistLine } from "@/types/cart";
import type { Brand as HomeBrand, Category as HomeCategory, EditorialBanner } from "@/types/home";
import type { Order, ShippingAddress } from "@/types/order";
import type { Product, ProductVariantOption } from "@/types/product";

const PLACEHOLDER_IMAGE = "/placeholder-product.svg";

const num = (value: string | number | null | undefined) =>
  value === null || value === undefined ? 0 : Number(value);

export function apiProductCardToProduct(p: ApiProductCard): Product {
  return {
    id: p.id,
    slug: p.slug,
    name: p.name,
    brand: p.brand?.name ?? "",
    price: num(p.selling_price),
    compareAtPrice: p.is_on_sale ? num(p.mrp) : undefined,
    image: p.primary_image?.image ?? PLACEHOLDER_IMAGE,
    hoverImage: p.hover_image ?? undefined,
    imageAlt: p.primary_image?.alt_text ?? p.name,
    rating: num(p.rating_average) || undefined,
    reviewCount: p.review_count,
    isNew: p.is_new_arrival,
    stock: p.is_in_stock ? 99 : 0,
    description: p.short_description,
  };
}

export function apiProductCardsToProducts(list: ApiProductCard[]): Product[] {
  return list.map(apiProductCardToProduct);
}

export function apiVariantsToOptions(variants: ApiProductDetail["variants"]): ProductVariantOption[] {
  return variants.map((v) => ({
    sku: v.sku,
    color: v.color,
    colorCode: v.color_code || undefined,
    size: v.size,
    availableStock: v.available_stock,
  }));
}

export function apiProductDetailToProduct(p: ApiProductDetail): Product {
  const variants = apiVariantsToOptions(p.variants);
  return {
    ...apiProductCardToProduct(p),
    description: p.long_description || p.short_description,
    sizes: [...new Set(variants.map((v) => v.size))],
    colors: [...new Set(variants.map((v) => v.color))],
    stock: variants.reduce((sum, v) => sum + v.availableStock, 0),
    variants,
  };
}

export function apiCartItemToLine(item: ApiCartItem): CartLine {
  return {
    lineId: item.variant.sku,
    productId: item.product.id,
    slug: item.product.slug,
    name: item.product.name,
    brand: item.product.brand?.name ?? "",
    image: item.product.primary_image?.image ?? PLACEHOLDER_IMAGE,
    price: num(item.unit_mrp),
    discountedPrice: num(item.unit_price),
    size: item.variant.size || undefined,
    color: item.variant.color || undefined,
    quantity: item.quantity,
    savedForLater: item.saved_for_later,
  };
}

export function apiWishlistItemToLine(item: ApiWishlistItem): WishlistLine {
  return {
    productId: item.product.id,
    slug: item.product.slug,
    name: item.product.name,
    brand: item.product.brand?.name ?? "",
    image: item.product.primary_image?.image ?? PLACEHOLDER_IMAGE,
    price: num(item.product.mrp),
    discountedPrice: num(item.product.selling_price),
    addedAt: Date.parse(item.added_at) || Date.now(),
  };
}

export function apiAddressToShipping(a: ApiAddress): ShippingAddress {
  return {
    id: a.id,
    fullName: a.full_name,
    mobile: a.mobile,
    address: [a.address_line_1, a.address_line_2].filter(Boolean).join(", "),
    city: a.city,
    state: a.state,
    pincode: a.postal_code,
    country: a.country,
    addressType: "home",
  };
}

function snapshotToShipping(a: ApiAddressSnapshot): ShippingAddress {
  return {
    fullName: a.full_name,
    mobile: a.mobile,
    address: [a.address_line_1, a.address_line_2].filter(Boolean).join(", "),
    city: a.city,
    state: a.state,
    pincode: a.postal_code,
    country: a.country,
    addressType: "home",
  };
}

function apiOrderItemsToLines(items: ApiOrderDetail["items"]): CartLine[] {
  return items.map((item) => ({
    lineId: item.id,
    productId: item.sku,
    slug: item.product_slug,
    name: item.product_name,
    brand: item.brand_name,
    image: item.image_url || PLACEHOLDER_IMAGE,
    price: num(item.mrp),
    discountedPrice: num(item.selling_price),
    size: item.size || undefined,
    color: item.color || undefined,
    quantity: item.quantity,
    savedForLater: false,
  }));
}

export function apiOrderDetailToOrder(o: ApiOrderDetail): Order {
  return {
    orderId: o.order_number,
    invoiceNumber: o.invoice_number,
    createdAt: o.created_at,
    items: apiOrderItemsToLines(o.items),
    shippingAddress: snapshotToShipping(o.shipping_address),
    deliveryMethod: (o.delivery_method || "standard") as Order["deliveryMethod"],
    paymentMethod: o.payment_method as Order["paymentMethod"],
    paymentLabel: o.payment_method_display,
    status: o.status,
    statusDisplay: o.status_display,
    totals: {
      subtotal: num(o.subtotal),
      productDiscount: num(o.discount),
      couponCode: o.coupon_code || undefined,
      couponDiscount: num(o.coupon_discount),
      gst: num(o.tax),
      shipping: num(o.shipping_charge),
      platformFee: num(o.platform_fee),
      grandTotal: num(o.grand_total),
    },
    estimatedDelivery: o.estimated_delivery_date ?? "",
  };
}

// -- Homepage catalog rails (categories/brands/collections) ---------------

export function apiCategoryToHomeCategory(c: ApiCategory): HomeCategory {
  return {
    id: c.id,
    name: c.name,
    href: `/${c.slug}`,
    image: c.image ?? c.banner_image ?? PLACEHOLDER_IMAGE,
    imageAlt: c.name,
  };
}

export function apiBrandToHomeBrand(b: ApiBrand): HomeBrand {
  return {
    id: b.id,
    name: b.name,
    href: `/search?brand=${b.slug}`,
  };
}

// Luxury Collection renders large editorial banners, which is what
// EditorialBanner already models — reused here rather than inventing a
// second banner shape for the same UI.
export function apiBrandToEditorialBanner(b: ApiBrand): EditorialBanner {
  return {
    id: b.id,
    eyebrow: "The Luxury Collection",
    title: b.name,
    description: b.description || "",
    ctaLabel: "Shop The Edit",
    ctaHref: `/search?brand=${b.slug}`,
    image: b.banner ?? b.logo ?? PLACEHOLDER_IMAGE,
    imageAlt: b.name,
  };
}

export function apiCollectionToEditorialBanner(c: ApiCollection): EditorialBanner {
  return {
    id: c.id,
    eyebrow: "Editor's Pick",
    title: c.title,
    description: c.description || "",
    ctaLabel: "Shop The Edit",
    // Routes through the search page's `collection` param, which filters the
    // real /products/ listing by collection slug (backend's confirmed
    // ProductFilter.collection) instead of running the title as free text.
    ctaHref: `/search?collection=${encodeURIComponent(c.slug)}`,
    image: c.banner ?? c.image ?? PLACEHOLDER_IMAGE,
    imageAlt: c.title,
  };
}

export function apiOrderSummaryToOrder(o: ApiOrderSummary): Order {
  return {
    orderId: o.order_number,
    invoiceNumber: "",
    createdAt: o.created_at,
    items: o.preview_items.map((item, i) => ({
      lineId: `${o.order_number}-${i}`,
      productId: "",
      slug: "",
      name: item.product_name,
      brand: "",
      image: item.image_url || PLACEHOLDER_IMAGE,
      price: 0,
      discountedPrice: 0,
      quantity: 1,
      savedForLater: false,
    })),
    shippingAddress: {
      fullName: "",
      mobile: "",
      address: "",
      city: "",
      state: "",
      pincode: "",
      country: "",
      addressType: "home",
    },
    deliveryMethod: "standard",
    paymentMethod: o.payment_method as Order["paymentMethod"],
    paymentLabel: o.status_display,
    status: o.status,
    statusDisplay: o.status_display,
    totals: {
      subtotal: num(o.grand_total),
      productDiscount: 0,
      couponDiscount: 0,
      gst: 0,
      shipping: 0,
      platformFee: 0,
      grandTotal: num(o.grand_total),
    },
    estimatedDelivery: o.estimated_delivery_date ?? "",
  };
}
