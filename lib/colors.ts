// Shared display-name -> swatch-hex map, used anywhere a product color needs
// to render as an actual swatch (PDP color selector, filter sidebar). Backend
// only sends the color's display name, not a hex value, so this is a
// frontend-only presentation lookup — unknown names fall back to a neutral
// gray dot rather than guessing.
export const COLOR_HEX: Record<string, string> = {
  Black: "#111111",
  White: "#f5f5f5",
  Navy: "#1f2a44",
  Beige: "#e8dcc8",
  Olive: "#6b6f42",
  Maroon: "#5c1a26",
  Mustard: "#d9a441",
  "Blush Pink": "#f3c9cd",
  Ivory: "#f4f1e8",
  Charcoal: "#36454f",
  Emerald: "#0f6b4c",
  Rust: "#b0532a",
  Lavender: "#c8b8e8",
  Teal: "#1f6f6b",
  Camel: "#c19a6b",
  "Grey Melange": "#9a9a9a",
  Wine: "#5e1f30",
  "Sky Blue": "#8ecae6",
  Coral: "#e8735c",
  Sand: "#dcc7a1",
};
