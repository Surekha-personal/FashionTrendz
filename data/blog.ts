import { unsplash } from "@/utils/images";
import type { BlogPost } from "@/types/home";

export const blogPosts: BlogPost[] = [
  {
    id: "blog-layering",
    title: "The Art of Layering: Building a Transitional Wardrobe",
    excerpt:
      "Master the balance of textures and proportions to move seamlessly between seasons without a full wardrobe overhaul.",
    image: unsplash("1517841905240-472988babdf9", 800),
    imageAlt: "Fashion layering styling flatlay",
    href: "/blog/art-of-layering",
    category: "Style Guide",
    readTime: "5 min read",
  },
  {
    id: "blog-accessorize",
    title: "5 Ways to Accessorize a Little Black Dress",
    excerpt:
      "From statement earrings to structured totes, here's how to make one dress feel like five different outfits.",
    image: unsplash("1524250502761-1ac6f2e30d43", 800),
    imageAlt: "Accessories styled with a black dress",
    href: "/blog/accessorize-lbd",
    category: "Styling Tips",
    readTime: "4 min read",
  },
  {
    id: "blog-sustainable",
    title: "Inside Our Move Toward Responsibly Sourced Fabrics",
    excerpt:
      "A look at how our in-house labels are shifting to organic cotton and recycled fibres without compromising on fit.",
    image: unsplash("1524253482453-3fed8d2fe12b", 800),
    imageAlt: "Sustainable fabric sourcing for fashion",
    href: "/blog/responsibly-sourced-fabrics",
    category: "Sustainability",
    readTime: "6 min read",
  },
];
