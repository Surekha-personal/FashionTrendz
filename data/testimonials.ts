import { pravatar } from "@/utils/images";
import type { Testimonial } from "@/types/home";

export const testimonials: Testimonial[] = [
  {
    id: "t1",
    name: "Ananya Rao",
    location: "Bengaluru",
    rating: 5,
    review:
      "The quality is miles ahead of what I expected online. The wrap dress fit perfectly and the packaging felt genuinely premium.",
    avatar: pravatar(47),
  },
  {
    id: "t2",
    name: "Kabir Malhotra",
    location: "New Delhi",
    rating: 5,
    review:
      "Fast delivery, true-to-size fits, and the customer support actually helped me exchange a size within a day. Rare these days.",
    avatar: pravatar(12),
  },
  {
    id: "t3",
    name: "Meera Iyer",
    location: "Mumbai",
    rating: 4,
    review:
      "Fashion Trendz has become my go-to for festive shopping. The Luxury Collection edit is curated so well, nothing feels random.",
    avatar: pravatar(29),
  },
  {
    id: "t4",
    name: "Rohan Verma",
    location: "Pune",
    rating: 5,
    review:
      "Ordered the tailored blazer for a work event — compliments all evening. The fabric feels genuinely expensive.",
    avatar: pravatar(33),
  },
  {
    id: "t5",
    name: "Simran Kaur",
    location: "Chandigarh",
    rating: 5,
    review:
      "Love that they show real fit and fabric details before you buy. Zero surprises on delivery, which is unusual for fashion sites.",
    avatar: pravatar(56),
  },
  {
    id: "t6",
    name: "Aditya Nair",
    location: "Kochi",
    rating: 4,
    review:
      "The flash sale section is dangerously good. Picked up sneakers at 30% off and they arrived two days early.",
    avatar: pravatar(15),
  },
];
