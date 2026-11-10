import { api, type WindowResult } from "./api";
import { hoursOf } from "./format";
import { HERO_PLACE, WINTER_MEDIAN } from "./site";

export interface HeroLive {
  kind: "live";
  when: "Today" | "Tomorrow";
  values: number[];
  measured: boolean[];
  open: number;
  close: number;
  result: WindowResult;
}

export interface HeroFallback {
  kind: "median";
  values: number[];
  measured: boolean[];
  open: number;
  close: number;
}

export type HeroData = HeroLive | HeroFallback;

const FALLBACK: HeroFallback = {
  kind: "median",
  values: WINTER_MEDIAN,
  measured: WINTER_MEDIAN.map(() => true),
  open: 14,
  close: 18,
};

function usable(r: WindowResult | null): r is WindowResult {
  return (
    !!r &&
    r.status === "ok" &&
    !!r.best &&
    Array.isArray(r.curve) &&
    r.curve.length === 24 &&
    r.curve.every((p) => Number.isFinite(p.pm25))
  );
}

async function tryDay(day: "today" | "tomorrow"): Promise<WindowResult | null> {
  try {
    return await api.window(
      { lat: HERO_PLACE.lat, lon: HERO_PLACE.lon, activity: "walk", minutes: 60, habitual: "06:00", day, log: false },
      { next: { revalidate: 900 } },
    );
  } catch {
    return null;
  }
}

/** Live curve for Lodhi Road (today, else tomorrow once today's hours have passed), or the winter median. */
export async function getHeroData(): Promise<HeroData> {
  for (const day of ["today", "tomorrow"] as const) {
    const r = await tryDay(day);
    if (usable(r)) {
      const curve = [...r.curve!].sort((a, b) => a.hour.localeCompare(b.hour));
      return {
        kind: "live",
        when: day === "today" ? "Today" : "Tomorrow",
        values: curve.map((p) => p.pm25),
        measured: curve.map((p) => p.measured),
        open: hoursOf(r.best!.start),
        close: hoursOf(r.best!.end),
        result: r,
      };
    }
  }
  return FALLBACK;
}
