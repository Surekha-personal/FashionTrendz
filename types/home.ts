export interface HeroSlide {
  id: string;
  eyebrow: string;
  title: string;
  subtitle: string;
  ctaLabel: string;
  ctaHref: string;
  image: string;
  imageAlt: string;
}

export interface Category {
  id: string;
  name: string;
  href: string;
  image: string;
  imageAlt: string;
}

export interface Brand {
  id: string;
  name: string;
  href: string;
}

export interface Testimonial {
  id: string;
  name: string;
  location: string;
  rating: number;
  review: string;
  avatar: string;
}

export interface BlogPost {
  id: string;
  title: string;
  excerpt: string;
  image: string;
  imageAlt: string;
  href: string;
  category: string;
  readTime: string;
}

export interface InstagramPost {
  id: string;
  image: string;
  imageAlt: string;
  href: string;
  likes: number;
}

export interface EditorialBanner {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  ctaLabel: string;
  ctaHref: string;
  image: string;
  imageAlt: string;
}

export interface InspirationImage {
  id: string;
  image: string;
  imageAlt: string;
  caption: string;
  tall?: boolean;
}
