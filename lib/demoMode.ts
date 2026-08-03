import { localStore, STORAGE_KEYS } from "@/lib/storage";

export interface DemoUser {
  name: string;
  email: string;
}

export function isDemoModeEnabled() {
  return localStore.read(STORAGE_KEYS.demoMode, false);
}

export function getDemoUser(): DemoUser | null {
  return localStore.read<DemoUser | null>(STORAGE_KEYS.demoUser, null);
}

export async function enableDemoMode() {
  const res = await fetch("/api/demo-seed");
  const data = await res.json();
  localStore.write(STORAGE_KEYS.cart, data.cart);
  localStore.write(STORAGE_KEYS.wishlist, data.wishlist);
  localStore.write(STORAGE_KEYS.orders, data.orders);
  localStore.write(STORAGE_KEYS.recentlyViewed, data.recentlyViewed);
  localStore.write(STORAGE_KEYS.demoUser, data.user);
  localStore.write(STORAGE_KEYS.demoMode, true);
  window.location.reload();
}

export function disableDemoMode() {
  localStore.remove(STORAGE_KEYS.cart);
  localStore.remove(STORAGE_KEYS.wishlist);
  localStore.remove(STORAGE_KEYS.orders);
  localStore.remove(STORAGE_KEYS.recentlyViewed);
  localStore.remove(STORAGE_KEYS.demoUser);
  localStore.write(STORAGE_KEYS.demoMode, false);
  window.location.reload();
}
