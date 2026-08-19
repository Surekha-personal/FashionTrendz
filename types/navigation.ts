export interface MegaMenuLink {
  label: string;
  href: string;
  badge?: string;
}

export interface MegaMenuColumn {
  heading: string;
  links: MegaMenuLink[];
}

export interface FeaturedTile {
  label: string;
  href: string;
  image: string;
  imageAlt: string;
}

export interface NavItem {
  label: string;
  href: string;
  columns?: MegaMenuColumn[];
  featured?: FeaturedTile[];
}
