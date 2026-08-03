const DEFAULT_MESSAGES = [
  "Free shipping on orders above ₹1,999",
  "New season arrivals just dropped",
  "Extra 10% off on your first order — use FIRST10",
];

export function AnnouncementBar({
  messages = DEFAULT_MESSAGES,
}: {
  messages?: string[];
}) {
  const loop = [...messages, ...messages];

  return (
    <div className="overflow-hidden bg-primary text-primary-foreground">
      <div className="flex w-max animate-marquee gap-16 py-2 text-xs font-medium tracking-wide whitespace-nowrap">
        {loop.map((message, i) => (
          <span key={i}>{message}</span>
        ))}
      </div>
    </div>
  );
}
