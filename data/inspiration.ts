import { unsplash } from "@/utils/images";
import type { InspirationImage } from "@/types/home";

export const inspirationImages: InspirationImage[] = [
  {
    id: "insp1",
    image: unsplash("1467043237213-65f2da53396f", 600),
    imageAlt: "Minimal fashion lifestyle inspiration",
    caption: "Quiet Luxury",
    tall: true,
  },
  {
    id: "insp2",
    image: unsplash("1546456073-6712f79251bb", 600),
    imageAlt: "Casual fashion lifestyle inspiration",
    caption: "Weekend Casual",
  },
  {
    id: "insp3",
    image: unsplash("1483181957632-8bda974cbc91", 600),
    imageAlt: "Street style fashion inspiration",
    caption: "Street Ready",
  },
  {
    id: "insp4",
    image: unsplash("1512436991641-6745cdb1723f", 600),
    imageAlt: "Evening wear fashion inspiration",
    caption: "After Dark",
    tall: true,
  },
  {
    id: "insp5",
    image: unsplash("1515886657613-9f3515b0c78f", 600),
    imageAlt: "Office fashion lifestyle inspiration",
    caption: "Desk To Dinner",
  },
  {
    id: "insp6",
    image: unsplash("1520903920243-00d872a2d1c9", 600),
    imageAlt: "Travel fashion lifestyle inspiration",
    caption: "Airport Edit",
  },
  {
    id: "insp7",
    image: unsplash("1524638431109-93d95c968f03", 600),
    imageAlt: "Festive fashion lifestyle inspiration",
    caption: "Festive Glam",
    tall: true,
  },
  {
    id: "insp8",
    image: unsplash("1529626455594-4ff0802cfb7e", 600),
    imageAlt: "Monochrome fashion lifestyle inspiration",
    caption: "Tonal Dressing",
  },
  {
    id: "insp9",
    image: unsplash("1530893609608-32a9af3aa95c", 600),
    imageAlt: "Accessorized fashion lifestyle inspiration",
    caption: "Layered Gold",
  },
];
