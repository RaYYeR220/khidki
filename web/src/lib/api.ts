// Typed client for the Khidki engine API.

export const API_BASE = (process.env.NEXT_PUBLIC_KHIDKI_API || "https://khidki-engine-ptslyhnp7q-el.a.run.app").replace(
  /\/$/,
  "",
);

export type Activity =
  "walk" | "run" | "cycle" | "yoga" | "play" | "commute_walk" | "commute_two_wheeler" | "errand" | "outdoor_work";

export type AgeBand = "child" | "adult" | "older";

export interface Slot {
  start: string;
  end: string;
  mean_pm25: number;
  dose_ug: number;
  category: string;
}

export interface CurvePoint {
  hour: string;
  pm25: number;
  measured: boolean;
}

export interface Neighbour {
  id: string;
  name: string | null;
  km: number;
  weight: number;
  has_forecast: boolean;
}

export interface WindowResult {
  status: "ok" | "no_data" | "stale" | "window_closed";
  reason?: string;
  day: string;
  activity?: Activity;
  minutes?: number;
  best?: Slot | null;
  usual?: Slot | null;
  worst?: Slot | null;
  alternatives?: (Slot | null)[];
  dose_avoided_ug?: number | null;
  reduction_pct?: number | null;
  confidence?: number | null;
  flags?: string[];
  health?: string | null;
  curve?: CurvePoint[];
  source?: "stations" | "cams_only" | "none";
  neighbours?: Neighbour[];
  issued_at?: string | null;
  nowcast_factor?: number | null;
  inhalation_m3_per_min?: number;
}

export interface WindowQuery {
  lat: number;
  lon: number;
  activity?: Activity;
  minutes?: number;
  earliest?: string;
  latest_end?: string;
  habitual?: string;
  age?: AgeBand;
  day?: "today" | "tomorrow" | string;
  /** false for the site's own previews, so they are not counted as lookups */
  log?: boolean;
}

export interface AiringQuery {
  lat: number;
  lon: number;
  open_minutes?: number;
  earliest?: string;
  latest_end?: string;
  habitual?: string;
  day?: string;
}

export interface AiringResult {
  status: string;
  reason?: string;
  day: string;
  open_at?: string | null;
  open_minutes?: number;
  usual?: string | null;
  outdoor_pm25_then?: number | null;
  outdoor_pm25_at_usual?: number | null;
  reduction_pct?: number | null;
  dose_avoided_ug?: number | null;
  flags?: string[];
  source?: string;
}

export interface AirNowReading {
  station: string;
  km: number;
  pm25: number;
  category: string;
  hour: string;
  hours_old: number;
}

export interface Commitment {
  day: string;
  issued_at: string;
  model: string;
  sha256: string;
  n_stations: number;
  n_recommendations: number;
  anchor: string | null;
  bitcoin_attested?: boolean;
}

export interface ScoreRow {
  station_days: number;
  stations: number;
  reduction_vs_habitual_pct: number | null;
  captured_of_hindsight_best_pct: number | null;
  better_than_habit_pct: number;
  worse_than_habit_pct: number;
  first_day: string;
  last_day: string;
}

export interface Scoreboard {
  by_scenario: Record<string, Record<string, ScoreRow>>;
  days: { day: string; stations: number }[];
}

export interface AuditFlag {
  station_id: string;
  name: string | null;
  city: string | null;
  kind: string;
  severity: "info" | "warn" | "high";
  detail: Record<string, unknown>;
}

export interface Audit {
  day: string;
  stations_audited: number;
  by_kind: Record<string, number>;
  flags: AuditFlag[];
}

export interface Bulletin {
  status: "ok" | "none";
  day: string | null;
  created_at?: string;
  text?: string;
}

export interface Impact {
  as_of: string;
  stations_covered: number;
  hours_of_readings: number;
  days_published_in_advance: number;
  recommendations_published: number;
  recommendations_verified: number;
  audit_flags_raised: number;
  people: Record<string, number>;
  plans_made_for_people: number;
  people_outcomes_verified: number;
  people_dose_avoided_ug: number;
  window_lookups: number;
}

export interface Station {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  lat: number;
  lon: number;
  provider: string | null;
  last_seen: string | null;
  latest: number | null;
  latest_hour: string | null;
  category: string | null;
}

export interface Place {
  name: string;
  lat: number;
  lon: number;
}

export class ApiError extends Error {
  constructor(
    public path: string,
    public status: number,
  ) {
    super(`${path}: ${status}`);
  }
}

type Init = RequestInit & { next?: { revalidate?: number | false } };

async function get<T>(path: string, init?: Init, timeoutMs = 12000): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  if (!r.ok) throw new ApiError(path, r.status);
  return (await r.json()) as T;
}

function qs(params: object): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  return u.toString();
}

export const api = {
  window: (q: WindowQuery, init: Init = { cache: "no-store" }) => get<WindowResult>(`/v1/window?${qs(q)}`, init),
  airing: (q: AiringQuery, init: Init = { cache: "no-store" }) => get<AiringResult>(`/v1/airing?${qs(q)}`, init),
  airNow: (lat: number, lon: number) =>
    get<{ status: string; readings: AirNowReading[] }>(`/v1/air-now?${qs({ lat, lon })}`, { cache: "no-store" }),
  geocode: (q: string) => get<{ results: Place[] }>(`/v1/geocode?${qs({ q })}`, { cache: "no-store" }),
  stations: () => get<{ count: number; stations: Station[] }>(`/v1/stations`, { next: { revalidate: 300 } }),
  ledger: () => get<{ commitments: Commitment[] }>(`/v1/ledger`, { next: { revalidate: 120 } }),
  ledgerPayloadUrl: (day: string) => `${API_BASE}/v1/ledger/${day}.json`,
  ledgerOtsUrl: (day: string) => `${API_BASE}/v1/ledger/${day}.ots`,
  scoreboard: () => get<Scoreboard>(`/v1/scoreboard`, { next: { revalidate: 300 } }),
  audit: (day?: string) => get<Audit>(`/v1/audit${day ? `?day=${day}` : ""}`, { next: { revalidate: 300 } }),
  bulletin: () => get<Bulletin>(`/v1/bulletin`, { next: { revalidate: 300 } }),
  impact: () => get<Impact>(`/v1/impact`, { next: { revalidate: 60 } }),
  chat: async (body: { text: string; session: string; lat?: number; lon?: number; lang?: string }) => {
    const r = await fetch(`${API_BASE}/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000),
    });
    if (r.status === 429) throw new ApiError("/v1/chat", 429);
    if (!r.ok) throw new ApiError("/v1/chat", r.status);
    return (await r.json()) as { reply: string; tools: string[] };
  },
};

/** Run a request and return null instead of throwing (for server-rendered sections with empty states). */
export async function settle<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch {
    return null;
  }
}

/** SHA-256 of a string, hex, computed in the browser. */
export async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 of raw bytes, hex. Used to check the ledger file exactly as served. */
export async function sha256HexBytes(buf: ArrayBuffer): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
