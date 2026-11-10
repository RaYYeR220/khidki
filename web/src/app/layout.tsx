import type { Metadata, Viewport } from "next";
import { Geist_Mono, Instrument_Sans, Instrument_Serif, Tiro_Devanagari_Hindi } from "next/font/google";
import { SITE_URL } from "@/lib/site";
import "./globals.css";

const serif = Instrument_Serif({ weight: "400", subsets: ["latin"], variable: "--font-serif", display: "swap" });
const sans = Instrument_Sans({ weight: ["400", "500"], subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = Geist_Mono({ weight: ["400", "500"], subsets: ["latin"], variable: "--font-mono", display: "swap" });
const hindi = Tiro_Devanagari_Hindi({ weight: "400", subsets: ["devanagari"], variable: "--font-hi", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Khidki · Open the window when the air does.",
    template: "%s · Khidki",
  },
  description:
    "Khidki tells you when the air over your street is cleanest: for your walk, your run, your children's playtime and the windows at home. Published the night before, checked against India's government monitors the next day.",
  applicationName: "Khidki",
  openGraph: {
    type: "website",
    siteName: "Khidki",
    locale: "en_IN",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  themeColor: "#15130f",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable} ${hindi.variable}`}>
      <body>{children}</body>
    </html>
  );
}
