import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "linear-gradient(135deg, #1e40af 0%, #2563eb 100%)",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 7,
        }}
      >
        {/* Document body */}
        <div
          style={{
            position: "relative",
            display: "flex",
            width: 18,
            height: 22,
          }}
        >
          {/* Document rectangle */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "white",
              borderRadius: 2,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2,
            }}
          >
            {/* Line 1 */}
            <div
              style={{
                width: 10,
                height: 1.5,
                background: "#2563eb",
                borderRadius: 1,
                opacity: 0.4,
              }}
            />
            {/* Checkmark path (approximated with divs) */}
            <div
              style={{
                width: 8,
                height: 6,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 5,
                  borderBottom: "2px solid #2563eb",
                  borderLeft: "2px solid #2563eb",
                  transform: "rotate(-45deg) translate(1px, -1px)",
                  borderRadius: 1,
                }}
              />
            </div>
          </div>
          {/* Folded corner */}
          <div
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              width: 5,
              height: 5,
              background: "#1e40af",
              borderBottomLeftRadius: 1,
              opacity: 0.6,
            }}
          />
        </div>
      </div>
    ),
    { ...size }
  );
}
