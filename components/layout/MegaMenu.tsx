import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
} from "@/components/ui/navigation-menu";
import { mainNav } from "@/data/navigation";

export function MegaMenu() {
  return (
    <NavigationMenu viewport={false} className="max-w-none justify-start">
      <NavigationMenuList>
        {mainNav.map((item, index) =>
          item.columns ? (
            <NavigationMenuItem key={item.label}>
              <NavigationMenuTrigger className="text-sm font-medium">
                {item.label}
              </NavigationMenuTrigger>
              <NavigationMenuContent
                className={cn(
                  // viewport={false} anchors each panel to its own trigger
                  // (left-0) with no built-in collision detection. This menu
                  // is wide enough that triggers past the row's midpoint
                  // would push it off the right edge of the viewport, so
                  // those panels anchor from the right instead.
                  index >= mainNav.length / 2 && "left-auto right-0"
                )}
              >
                <div className="grid w-[min(64rem,90vw)] grid-cols-[1fr_1fr_1fr_9rem_9rem] gap-6 p-6">
                  {item.columns.map((column) => (
                    <div key={column.heading} className="flex flex-col gap-3">
                      <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        {column.heading}
                      </span>
                      <ul className="flex flex-col gap-2.5">
                        {column.links.map((link) => (
                          <li key={link.href}>
                            <NavigationMenuLink asChild className="p-0">
                              <Link
                                href={link.href}
                                className="text-sm text-foreground/80 transition-colors hover:text-accent"
                              >
                                {link.label}
                              </Link>
                            </NavigationMenuLink>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                  {item.featured?.map((tile) => (
                    <Link
                      key={tile.href}
                      href={tile.href}
                      className="group relative flex aspect-square w-full flex-col justify-end overflow-hidden rounded-xl bg-muted shadow-sm"
                    >
                      <Image
                        src={tile.image}
                        alt={tile.imageAlt}
                        fill
                        sizes="9rem"
                        className="object-cover transition-transform duration-300 group-hover:scale-110"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
                      <span className="relative flex items-center justify-between gap-1 p-3 text-xs font-medium text-white">
                        {tile.label}
                        <ArrowRight className="size-3.5 shrink-0 transition-transform group-hover:translate-x-0.5" />
                      </span>
                    </Link>
                  ))}
                </div>
              </NavigationMenuContent>
            </NavigationMenuItem>
          ) : (
            <NavigationMenuItem key={item.label}>
              <NavigationMenuLink asChild>
                <Link
                  href={item.href}
                  className="text-sm font-medium text-accent"
                >
                  {item.label}
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          )
        )}
      </NavigationMenuList>
    </NavigationMenu>
  );
}
