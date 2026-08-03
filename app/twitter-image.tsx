import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#111111",
          color: "#fafafa",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 600,
            letterSpacing: -1,
          }}
        >
          Fashion Trendz
        </div>
        <div
          style={{
            marginTop: 20,
            width: 120,
            height: 4,
            backgroundColor: "#e91e63",
            borderRadius: 999,
          }}
        />
        <div style={{ marginTop: 28, fontSize: 28, color: "#a1a1aa" }}>
          Premium Fashion, Curated for You
        </div>
      </div>
    ),
    { ...size }
  );
}
