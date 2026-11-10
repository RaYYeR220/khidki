import { API_BASE, type Activity, type AgeBand, type Place } from "./api";

export const TELEGRAM_URL = "https://t.me/Khidkitgbot";
export const TELEGRAM_HANDLE = "@Khidkitgbot";
export const GITHUB_URL = "https://github.com/RaYYeR220/khidki";
export const MCP_URL = `${API_BASE}/mcp/`;

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ||
  (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : "") ||
  "http://localhost:3100"
).replace(/\/$/, "");

/** City presets with real coordinates (city centres). */
export const PRESETS: Place[] = [
  { name: "New Delhi", lat: 28.6139, lon: 77.209 },
  { name: "Mumbai", lat: 19.076, lon: 72.8777 },
  { name: "Kolkata", lat: 22.5726, lon: 88.3639 },
  { name: "Chennai", lat: 13.0827, lon: 80.2707 },
  { name: "Bengaluru", lat: 12.9716, lon: 77.5946 },
  { name: "Hyderabad", lat: 17.385, lon: 78.4867 },
  { name: "Pune", lat: 18.5204, lon: 73.8567 },
  { name: "Ahmedabad", lat: 23.0225, lon: 72.5714 },
  { name: "Lucknow", lat: 26.8467, lon: 80.9462 },
  { name: "Patna", lat: 25.5941, lon: 85.1376 },
];

/** The landing pane's live place: Lodhi Road, New Delhi. */
export const HERO_PLACE = { name: "Lodhi Road, New Delhi", lat: 28.5931, lon: 77.2197 };

export type ActivityKey = "walk" | "run" | "play" | "cycle" | "yoga" | "commute";

export interface ActivityPreset {
  key: ActivityKey;
  label: string;
  noun: string;
  api: Activity;
  minutes: number;
  habitual: string;
  earliest: string;
  latest: string;
  age: AgeBand;
}

export const ACTIVITIES: ActivityPreset[] = [
  {
    key: "walk",
    label: "Walk",
    noun: "walk",
    api: "walk",
    minutes: 60,
    habitual: "06:00",
    earliest: "05:00",
    latest: "21:00",
    age: "adult",
  },
  {
    key: "run",
    label: "Run",
    noun: "run",
    api: "run",
    minutes: 45,
    habitual: "06:00",
    earliest: "05:00",
    latest: "21:00",
    age: "adult",
  },
  {
    key: "play",
    label: "Children's play",
    noun: "playtime",
    api: "play",
    minutes: 45,
    habitual: "08:00",
    earliest: "08:00",
    latest: "14:00",
    age: "child",
  },
  {
    key: "cycle",
    label: "Cycle",
    noun: "ride",
    api: "cycle",
    minutes: 60,
    habitual: "06:30",
    earliest: "05:00",
    latest: "21:00",
    age: "adult",
  },
  {
    key: "yoga",
    label: "Yoga",
    noun: "yoga",
    api: "yoga",
    minutes: 45,
    habitual: "06:00",
    earliest: "05:00",
    latest: "21:00",
    age: "adult",
  },
  {
    key: "commute",
    label: "Commute",
    noun: "commute",
    api: "commute_walk",
    minutes: 30,
    habitual: "08:30",
    earliest: "07:00",
    latest: "11:00",
    age: "adult",
  },
];

export function activityFromApi(a: string | null | undefined): ActivityPreset {
  return ACTIVITIES.find((x) => x.api === a || x.key === a) ?? ACTIVITIES[0];
}

/** Winter median PM2.5 by hour (IST, hour start), µg/m³. CPCB New Delhi–Chanakyapuri via OpenAQ location 8118, 1 Nov 2025 – 28 Feb 2026. */
export const WINTER_MEDIAN = [
  186.5, 193, 191, 182.5, 187.5, 188.5, 181, 177, 187, 184, 170.5, 153.5, 122, 111, 108.5, 94, 99, 103, 125, 155, 181.5, 194,
  200.5, 190,
];

/** Replay of winter 2025–26 at CPCB New Delhi–Chanakyapuri (engine/results/backtest-delhi-chanakyapuri-2025-11-01-2026-02-28.json).
 *  Values are % change in PM2.5 dose vs the usual time; negative = less smoke. */
export const REPLAY = {
  station: "CPCB New Delhi–Chanakyapuri",
  period: "1 Nov 2025 – 28 Feb 2026",
  rows: [
    {
      scenario: "Morning walk, 60 min",
      usual: "06:00",
      allowed: "05:00–21:00",
      days: 113,
      khidki: -40.3,
      fixed: -41.0,
      hindsight: -50.6,
      worseDays: 19.5,
    },
    {
      scenario: "School outdoor play, 45 min",
      usual: "08:00",
      allowed: "08:00–14:00",
      days: 115,
      khidki: -36.4,
      fixed: -36.4,
      hindsight: -40.1,
      worseDays: 13.9,
    },
    {
      scenario: "Evening walk, 60 min",
      usual: "18:30",
      allowed: "15:00–22:00",
      days: 113,
      khidki: -22.5,
      fixed: -23.0,
      hindsight: -28.4,
      worseDays: 8.8,
    },
    {
      scenario: "Walk that must end by 10:00, 45 min",
      usual: "06:30",
      allowed: "05:00–10:00",
      days: 113,
      khidki: 1.6,
      fixed: -1.1,
      hindsight: -12.4,
      worseDays: 54.9,
    },
  ],
  mlModel: -35,
};


/** Replay of winter 2025–26 across India's reference-grade monitors
 *  (engine/results/backtest-national-2025-11-01-2026-02-28.json, engine/scripts/backtest_national.py).
 *  % change in PM2.5 dose vs the usual time; negative = less smoke. */
export const NATIONAL = {
  monitors: 490,
  cities: 262,
  stationDays: 49983,
  period: "1 Nov 2025 – 28 Feb 2026",
  rows: [
    { scenario: "Morning walk, 60 min", usual: "06:00", allowed: "05:00–21:00", stationDays: 38803, khidki: -28.6, fixed: -27.4, hindsight: -44.3, worseKhidki: 24.9, worseFixed: 29.3 },
    { scenario: "School outdoor play, 45 min", usual: "08:00", allowed: "08:00–14:00", stationDays: 39445, khidki: -26.4, fixed: -26.2, hindsight: -35.0, worseKhidki: 21.2, worseFixed: 27.4 },
    { scenario: "Evening walk, 60 min", usual: "18:30", allowed: "15:00–22:00", stationDays: 40791, khidki: -25.9, fixed: -24.6, hindsight: -34.4, worseKhidki: 17.8, worseFixed: 22.0 },
    { scenario: "Walk that must end by 10:00, 45 min", usual: "06:30", allowed: "05:00–10:00", stationDays: 41396, khidki: -3.4, fixed: 8.2, hindsight: -14.1, worseKhidki: 38.1, worseFixed: 64.8 },
  ],
  byCity: [
    { city: "Delhi", monitors: 30, khidki: -38.3, fixed: -37.5, hindsight: -49.3 },
    { city: "Mumbai", monitors: 25, khidki: -16.9, fixed: -20.1, hindsight: -39.9 },
    { city: "Bengaluru", monitors: 10, khidki: -10.8, fixed: 5.3, hindsight: -30.5 },
    { city: "Hyderabad", monitors: 14, khidki: -16.0, fixed: -11.7, hindsight: -29.5 },
    { city: "Chennai", monitors: 8, khidki: -28.3, fixed: -31.3, hindsight: -54.7 },
    { city: "Kolkata", monitors: 7, khidki: -32.5, fixed: -33.6, hindsight: -44.4 },
    { city: "Ahmedabad", monitors: 8, khidki: -17.2, fixed: -10.7, hindsight: -35.5 },
    { city: "Pune", monitors: 8, khidki: -44.1, fixed: -42.5, hindsight: -55.1 },
    { city: "Lucknow", monitors: 6, khidki: -18.1, fixed: -17.5, hindsight: -46.2 },
    { city: "Patna", monitors: 6, khidki: -18.8, fixed: -21.6, hindsight: -37.5 },
    { city: "Jaipur", monitors: 6, khidki: -35.4, fixed: -37.4, hindsight: -47.9 },
    { city: "Indore", monitors: 5, khidki: -46.4, fixed: -43.8, hindsight: -51.8 },
  ],
};
