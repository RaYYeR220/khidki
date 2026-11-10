import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { WINTER_MEDIAN } from "@/lib/site";

export const alt = "Khidki: open the window when the air does. The cleanest hour over your street, published the night before.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const HAZE = ["#3a3833", "#6e6a62", "#a9a39a"];

export default async function Image() {
  const dir = join(process.cwd(), "assets");
  const [serif, sans, mono] = await Promise.all([
    readFile(join(dir, "InstrumentSerif-Regular.ttf")),
    readFile(join(dir, "InstrumentSans-Regular.woff")),
    readFile(join(dir, "GeistMono-Regular.woff")),
  ]);

  // haze particles: density follows the winter median at 15:00 (94 µg/m³), the clean hour
  let seed = 1402;
  const rand = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
  const W = 300;
  const H = 392;
  const n = Math.round(WINTER_MEDIAN[15] * 1.5);
  const dots = Array.from({ length: n }, () => ({
    x: rand() * W,
    y: rand() * H,
    s: 1 + rand() * 1.6,
    c: HAZE[Math.floor(rand() * 3)],
    o: 0.55 + rand() * 0.45,
  }));

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        background: "radial-gradient(60% 70% at 76% 50%, #1f1b15 0%, #15130f 70%)",
        color: "#f1ece2",
        fontFamily: "Instrument Sans",
        padding: "56px 72px",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", flex: 1, paddingRight: 56 }}>
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <span style={{ fontFamily: "Instrument Serif", fontSize: 40, letterSpacing: -0.8 }}>Khidki</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              fontFamily: "Instrument Serif",
              fontSize: 104,
              lineHeight: 0.94,
              letterSpacing: -3,
              display: "flex",
              flexWrap: "wrap",
            }}
          >
            Open the window when the air does.
          </div>
          <div style={{ marginTop: 28, fontSize: 24, lineHeight: 1.4, color: "#c4bdb1", maxWidth: 600 }}>
            The cleanest hour over your street, published the night before and checked against India&apos;s government monitors.
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", width: 360 }}>
        <div
          style={{
            display: "flex",
            position: "relative",
            width: 322,
            height: 414,
            border: "1px solid rgba(241,236,226,.46)",
            borderRadius: 2,
            background: "#0e0d0a",
            padding: 11,
          }}
        >
          <div
            style={{
              display: "flex",
              position: "relative",
              width: W,
              height: H,
              overflow: "hidden",
              background: "linear-gradient(180deg, #47392a 0%, #685539 100%)",
            }}
          >
            {dots.map((d, i) => (
              <div
                key={i}
                style={{ position: "absolute", left: d.x, top: d.y, width: d.s, height: d.s, background: d.c, opacity: d.o }}
              />
            ))}
            <div
              style={{
                position: "absolute",
                left: 0,
                top: 0,
                width: 150,
                height: H,
                border: "1px solid rgba(241,236,226,.6)",
                display: "flex",
              }}
            />
            <div
              style={{
                position: "absolute",
                left: 0,
                top: H * 0.41,
                width: 150,
                height: 1,
                background: "rgba(241,236,226,.42)",
                display: "flex",
              }}
            />
            <div
              style={{
                position: "absolute",
                left: 160,
                top: 6,
                width: 128,
                height: H - 12,
                border: "1px solid rgba(255,213,145,.75)",
                background: "linear-gradient(128deg, rgba(255,213,145,.16), rgba(255,213,145,.03) 60%)",
                display: "flex",
              }}
            />
          </div>
        </div>
        <div
          style={{
            display: "flex",
            width: 378,
            height: 2,
            marginTop: 10,
            background: "linear-gradient(90deg, rgba(242,176,74,.25), #f2b04a 30%, #ffd591 60%, rgba(242,176,74,.25))",
          }}
        />
        <div style={{ display: "flex", marginTop: 18, fontFamily: "Geist Mono", fontSize: 19, color: "#f1ece2" }}>
          15:00 · 94 µg/m³ · <span style={{ color: "#f2b04a", marginLeft: 10 }}>open</span>
        </div>
        <div style={{ display: "flex", marginTop: 6, fontSize: 15, color: "#9c958a" }}>Winter median, CPCB Chanakyapuri</div>
      </div>
    </div>,
    {
      ...size,
      fonts: [
        { name: "Instrument Serif", data: serif, style: "normal", weight: 400 },
        { name: "Instrument Sans", data: sans, style: "normal", weight: 400 },
        { name: "Geist Mono", data: mono, style: "normal", weight: 400 },
      ],
    },
  );
}
