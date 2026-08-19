// Response shapes returned by the Django backend (apps/*/serializers.py).
// Only the fields the frontend actually reads are declared.

export interface ApiImage {
  id: string;
  image: string;
  thumbnail: string | null;
  alt_text: string;
  display_order: number;
  is_primary: boolean;
}

export interface ApiBrandLite {
  id: string;
  name: string;
  slug: string;
  logo: string | null;
  is_luxury: boolean;
}

export interface ApiCategoryLite {
  id: string;
  name: string;
  slug: string;
  icon: string | null;
  image: string | null;
  display_order: number;
}

export interface ApiSubcategoryLite {
  id: string;
  name: string;
  slug: string;
  image: string | null;
  display_order: number;
}

export interface ApiProductCard {
  id: string;
  name: string;
  slug: string;
  short_description: string;
  brand: ApiBrandLite;
  category: ApiCategoryLite;
  subcategory: ApiSubcategoryLite;
  primary_image: ApiImage | null;
  hover_image: string | null;
  mrp: string;
  selling_price: string;
  discount_percentage: string;
  discount_amount: string;
  currency: string;
  rating_average: string;
  rating_count: number;
  review_count: number;
  stock_status: string;
  is_in_stock: boolean;
  is_on_sale: boolean;
  is_featured: boolean;
  is_new_arrival: boolean;
  is_best_seller: boolean;
  is_trending: boolean;
  is_luxury: boolean;
}

export interface ApiVariant {
  id: string;
  sku: string;
  color: string;
  color_code: string;
  size: string;
  price: string;
  image_override: string | null;
  available_stock: number;
  is_available: boolean;
  is_low_stock: boolean;
}

export interface ApiProductDetail extends ApiProductCard {
  sku: string;
  long_description: string;
  images: ApiImage[];
  variants: ApiVariant[];
  attributes: { key: string; value: string }[];
  specifications: { label: string; value: string; display_order: number }[];
  gender: string;
  material: string;
  material_display: string;
  fit: string;
  fit_display: string;
  occasion: string;
  occasion_display: string;
  care_instructions: string;
  return_policy: string;
  estimated_delivery_days: number;
  wishlist_count: number;
  tax_percentage: string;
}

export interface ApiHomepageProducts {
  featured: ApiProductCard[];
  trending: ApiProductCard[];
  new_arrivals: ApiProductCard[];
  best_sellers: ApiProductCard[];
  luxury: ApiProductCard[];
  flash_sale: ApiProductCard[];
  editors_picks: ApiProductCard[];
  trending_this_week: ApiProductCard[];
  recommended: ApiProductCard[];
  recently_added: ApiProductCard[];
}

export interface ApiFacets {
  price: { min: string; max: string };
  brands: { name: string; slug: string; product_count: number }[];
  categories: { name: string; slug: string; product_count: number }[];
  colors: { color: string; color_code: string; product_count: number }[];
  sizes: { size: string; product_count: number }[];
  materials: { material: string; product_count: number }[];
  discount_buckets: number[];
  rating_buckets: number[];
  sort_options: string[];
  availability: string[];
}

export interface ApiSearchSuggestions {
  products: { label: string; slug: string; type: string }[];
  brands: { label: string; slug: string; type: string }[];
  categories: { label: string; slug: string; type: string }[];
}

// -- Catalog homepage rails (categories/brands/collections) ---------------

export interface ApiCategory {
  id: string;
  name: string;
  slug: string;
  image: string | null;
  banner_image: string | null;
}

export interface ApiBrand {
  id: string;
  name: string;
  slug: string;
  description: string;
  logo: string | null;
  banner: string | null;
}

export interface ApiCollection {
  id: string;
  title: string;
  slug: string;
  description: string;
  image: string | null;
  banner: string | null;
}

export interface ApiBanner {
  id: string;
  title: string;
  subtitle: string;
  image: string;
  mobile_image: string;
  alt_text: string;
  button_text: string;
  button_link: string;
  display_order: number;
}

// -- Users --------------------------------------------------------------

export interface ApiUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  mobile_number: string;
  is_email_verified: boolean;
}

export interface ApiAuthResponse {
  access: string;
  refresh: string;
  user: ApiUser;
}

export interface ApiAddress {
  id: number;
  full_name: string;
  mobile: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  country: string;
  postal_code: string;
  is_default: boolean;
}

// -- Cart -----------------------------------------------------------------

export interface ApiCartItem {
  id: string;
  product: ApiProductCard;
  variant: ApiVariant;
  quantity: number;
  unit_price: string;
  unit_mrp: string;
  discount: string;
  tax: string;
  subtotal: string;
  total: string;
  saved_for_later: boolean;
  available_stock: number;
  is_available: boolean;
  max_quantity: number;
  added_at: string;
}

export interface ApiCartSummary {
  currency: string;
  item_count: number;
  unit_count: number;
  subtotal: string;
  discount: string;
  coupon_code: string;
  coupon_discount: string;
  tax: string;
  shipping: string;
  free_shipping_threshold: string;
  amount_to_free_shipping: string;
  platform_fee: string;
  grand_total: string;
  total_savings: string;
  estimated_delivery_days: number;
}

export interface ApiCart {
  id: string;
  is_guest: boolean;
  currency: string;
  coupon_code: string;
  items: ApiCartItem[];
  saved_items: ApiCartItem[];
  summary: ApiCartSummary | null;
  issues: { variant_sku: string; product: string; reason: string; requested: number; available: number }[];
}

// -- Wishlist ---------------------------------------------------------------

export interface ApiWishlistItem {
  id: string;
  product: ApiProductCard;
  added_at: string;
}

// -- Orders -----------------------------------------------------------------

export interface ApiOrderItem {
  id: string;
  product_name: string;
  product_slug: string;
  brand_name: string;
  sku: string;
  size: string;
  color: string;
  variant_label: string;
  image_url: string;
  mrp: string;
  selling_price: string;
  discount: string;
  tax: string;
  quantity: number;
  subtotal: string;
  grand_total: string;
}

export interface ApiAddressSnapshot {
  full_name: string;
  mobile: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  country: string;
  postal_code: string;
}

export interface ApiOrderSummary {
  id: string;
  order_number: string;
  status: string;
  status_display: string;
  payment_status: string;
  payment_method: string;
  grand_total: string;
  currency: string;
  item_count: number;
  unit_count: number;
  preview_items: { product_name: string; image_url: string }[];
  estimated_delivery_date: string | null;
  is_cancellable: boolean;
  created_at: string;
}

export interface ApiOrderDetail extends ApiOrderSummary {
  invoice_number: string;
  shipping_address: ApiAddressSnapshot;
  billing_address: ApiAddressSnapshot;
  items: ApiOrderItem[];
  subtotal: string;
  discount: string;
  coupon_code: string;
  coupon_discount: string;
  shipping_charge: string;
  platform_fee: string;
  tax: string;
  total_savings: string;
  delivery_method: string;
  payment_method_display: string;
}

export interface ApiCheckoutContext {
  cart: ApiCart;
  summary: ApiCartSummary;
  issues: ApiCart["issues"];
  addresses: ApiAddress[];
  default_address: ApiAddress | null;
  payment_methods: { code: string; label: string; available: boolean; is_placeholder: boolean }[];
  delivery_methods: { code: string; label: string }[];
  is_checkout_ready: boolean;
}
