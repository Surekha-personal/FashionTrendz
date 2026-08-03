import { unsplash } from "@/utils/images";
import type { EditorialBanner } from "@/types/home";

export const luxuryBanners: EditorialBanner[] = [
  {
    id: "luxury-couture",
    eyebrow: "The Luxury Collection",
    title: "Couture-Inspired Essentials",
    description:
      "Limited-run pieces crafted in small batches, designed to be worn for decades, not seasons.",
    ctaLabel: "Explore The Collection",
    ctaHref: "/luxury",
    image: unsplash("1550928431-ee0ec6db30d3", 1200),
    imageAlt: "Luxury couture-inspired fashion editorial",
  },
  {
    id: "luxury-atelier",
    eyebrow: "Atelier Series",
    title: "Handcrafted in Small Batches",
    description:
      "Each piece finished by hand, with signature detailing you won't find anywhere else.",
    ctaLabel: "Shop The Atelier Edit",
    ctaHref: "/luxury/limited-edition",
    image: unsplash("1483118714900-540cf339fd46", 1200),
    imageAlt: "Handcrafted luxury fashion atelier piece",
  },
];

export const editorsPicks: EditorialBanner[] = [
  {
    id: "editors-monochrome",
    eyebrow: "Editor's Pick",
    title: "Monochrome Is Having a Moment",
    description: "Our style editors break down how to wear tonal dressing.",
    ctaLabel: "Read The Edit",
    ctaHref: "/blog/monochrome-styling",
    image: unsplash("1441123694162-e54a981ceba5", 700),
    imageAlt: "Monochrome fashion editorial styling",
  },
  {
    id: "editors-power-dressing",
    eyebrow: "Editor's Pick",
    title: "Power Dressing for the Modern Desk",
    description: "Sharp tailoring that carries you from boardroom to dinner.",
    ctaLabel: "Read The Edit",
    ctaHref: "/blog/power-dressing",
    image: unsplash("1503341455253-b2e723bb3dbb", 700),
    imageAlt: "Power dressing tailored fashion editorial",
  },
  {
    id: "editors-weekend",
    eyebrow: "Editor's Pick",
    title: "The Off-Duty Weekend Edit",
    description: "Effortless separates for a slower, softer weekend wardrobe.",
    ctaLabel: "Read The Edit",
    ctaHref: "/blog/weekend-edit",
    image: unsplash("1519741497674-611481863552", 700),
    imageAlt: "Off-duty weekend fashion editorial",
  },
  {
    id: "editors-accessories",
    eyebrow: "Editor's Pick",
    title: "Accessories That Do the Talking",
    description: "Minimal outfits, maximal statement pieces.",
    ctaLabel: "Read The Edit",
    ctaHref: "/blog/statement-accessories",
    image: unsplash("1533749047139-189de3cf06d3", 700),
    imageAlt: "Statement fashion accessories editorial",
  },
];
