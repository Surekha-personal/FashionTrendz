export function unsplash(id: string, width = 800) {
  return `https://images.unsplash.com/photo-${id}?w=${width}&q=80&auto=format&fit=crop`;
}

export function pravatar(seed: number) {
  return `https://i.pravatar.cc/150?img=${seed}`;
}
