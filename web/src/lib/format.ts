const IST = "Asia/Kolkata";

export const nf = new Intl.NumberFormat("en-US");

export function int(n: number | null | undefined): string {
  return n == null ? "—" : nf.format(Math.round(n));
}

export function ug(n: number | null | undefined): string {
  return n == null ? "—" : String(Math.round(n));
}

/** "−22%" / "+1.6%" with a real minus sign. */
export function signedPct(n: number, digits = 0): string {
  const v = Math.abs(n).toFixed(digits);
  if (Number(v) === 0) return "0%";
  return `${n < 0 ? "−" : "+"}${v}%`;
}

/** Parse "YYYY-MM-DD" as a calendar date and format it. */
export function dayLabel(
  day: string,
  opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" },
): string {
  const [y, m, d] = day.split("-").map(Number);
  if (!y || !m || !d) return day;
  return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

export function dateTimeIST(iso: string): string {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  return (
    new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: IST,
    }).format(t) + " IST"
  );
}

export function nowIST(): { hour: number; minute: number; date: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "0";
  return { hour: Number(get("hour")) % 24, minute: Number(get("minute")), date: `${get("year")}-${get("month")}-${get("day")}` };
}

/** "17:30" → 17.5 */
export function hoursOf(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return (h || 0) + (m || 0) / 60;
}

export function hh(h: number): string {
  const hr = Math.floor(h) % 24;
  const mi = Math.round((h - Math.floor(h)) * 60);
  return `${String(hr).padStart(2, "0")}:${String(mi).padStart(2, "0")}`;
}

export function shortHash(h: string, n = 10): string {
  return h.length <= n * 2 + 1 ? h : `${h.slice(0, n)}…${h.slice(-6)}`;
}

/** Haze ramp for a PM2.5 value: #3a3833 (clean) → #6e6a62 → #a9a39a (heavy). Never traffic-light.
 *  With lo/hi the ramp spans that range (the day's own spread), otherwise 0–max. */
export function hazeColor(pm: number, max = 250, lo = 0): string {
  const stops = [
    [0x3a, 0x38, 0x33],
    [0x6e, 0x6a, 0x62],
    [0xa9, 0xa3, 0x9a],
  ];
  const t = Math.max(0, Math.min(1, (pm - lo) / Math.max(1e-9, max - lo)));
  const seg = t < 0.5 ? 0 : 1;
  const f = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const a = stops[seg];
  const b = stops[seg + 1];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function confidenceWords(c: number | null | undefined): string | null {
  if (c == null) return null;
  if (c >= 0.8) return "Likely cleaner than your usual time";
  if (c >= 0.6) return "Probably cleaner than your usual time";
  return "A close call against your usual time";
}
