import Link from "next/link";
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
        {mainNav.map((item) =>
          item.columns ? (
            <NavigationMenuItem key={item.label}>
              <NavigationMenuTrigger>{item.label}</NavigationMenuTrigger>
              <NavigationMenuContent>
                <div className="grid w-[min(64rem,90vw)] grid-cols-[1fr_1fr_1fr_10rem_10rem] gap-6 p-6">
                  {item.columns.map((column) => (
                    <div key={column.heading} className="flex flex-col gap-3">
                      <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        {column.heading}
                      </span>
                      <ul className="flex flex-col gap-2">
                        {column.links.map((link) => (
                          <li key={link.href}>
                            <NavigationMenuLink asChild className="p-0">
                              <Link
                                href={link.href}
                                className="text-sm text-foreground/80 hover:text-accent"
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
                      className="flex flex-col justify-end gap-2 rounded-xl bg-muted p-4"
                    >
                      <span
                        role="img"
                        aria-label={tile.imageAlt}
                        className="flex aspect-square w-full items-center justify-center rounded-lg bg-secondary text-xs text-muted-foreground"
                      >
                        Featured
                      </span>
                      <span className="text-sm font-medium">{tile.label}</span>
                    </Link>
                  ))}
                </div>
              </NavigationMenuContent>
            </NavigationMenuItem>
          ) : (
            <NavigationMenuItem key={item.label}>
              <NavigationMenuLink asChild>
                <Link href={item.href} className="text-sm font-medium">
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
