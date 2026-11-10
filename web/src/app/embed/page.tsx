import type { Metadata } from "next";
import DayStrip from "@/components/DayStrip";
import { api, type WindowResult } from "@/lib/api";
import { hoursOf, signedPct, ug } from "@/lib/format";
import { activityFromApi } from "@/lib/site";
import s from "./embed.module.css";

export const metadata: Metadata = {
  title: "Today's clean window",
  robots: { index: false, follow: false },
};

type SP = Record<string, string | string[] | undefined>;

function one(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

const NOUN: Record<string, string> = {
  walk: "Cleanest walk",
  run: "Cleanest run",
  play: "Cleanest playtime",
  cycle: "Cleanest ride",
  yoga: "Cleanest yoga",
  commute: "Cleanest commute",
};

async function load(q: Parameters<typeof api.window>[0]): Promise<WindowResult | null> {
  try {
    return await api.window({ ...q, log: false }, { next: { revalidate: 600 } });
  } catch {
    return null;
  }
}

export default async function Embed({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const lat = Number(one(sp.lat));
  const lon = Number(one(sp.lon));
  const label = (one(sp.label) ?? "").slice(0, 60);
  const a = activityFromApi(one(sp.activity));
  const minutesRaw = Number(one(sp.minutes));
  const minutes = Number.isFinite(minutesRaw) && minutesRaw >= 10 && minutesRaw <= 240 ? Math.round(minutesRaw) : a.minutes;
  const habRaw = one(sp.habitual);
  const habitual = habRaw && /^([01]\d|2[0-3]):[0-5]\d$/.test(habRaw) ? habRaw : a.habitual;
  const dayParam = one(sp.day);

  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !one(sp.lat) || !one(sp.lon)) {
    return (
      <div className={s.card}>
        <p className={s.place}>Khidki card</p>
        <p className={s.msg}>Add a place to the address: ?lat=28.59&amp;lon=77.22&amp;activity=play&amp;label=Your%20school</p>
        <Credit />
      </div>
    );
  }

  const base = { lat, lon, activity: a.api, minutes, earliest: a.earliest, latest_end: a.latest, habitual, age: a.age };
  let when: "Today" | "Tomorrow" = dayParam === "tomorrow" ? "Tomorrow" : "Today";
  let r = await load({ ...base, day: when.toLowerCase() });
  if (!dayParam && r?.status === "window_closed") {
    when = "Tomorrow";
    r = await load({ ...base, day: "tomorrow" });
  }

  const appHref = `/app?lat=${lat}&lon=${lon}&activity=${a.api}${label ? `&label=${encodeURIComponent(label)}` : ""}`;
  const heading = `${label || `${lat.toFixed(3)}, ${lon.toFixed(3)}`}`;

  if (!r || r.status !== "ok" || !r.best) {
    const why = !r
      ? "The air data is unreachable right now."
      : r.status === "window_closed"
        ? "Today's hours have passed."
        : "No monitor within 15 km has a forecast for this day yet.";
    return (
      <div className={s.card}>
        <div className={s.top}>
          <p className={s.place}>{heading}</p>
          <p className={s.when}>{when}</p>
        </div>
        <p className={s.kick}>{NOUN[a.key]}</p>
        <p className={s.msg}>{why}</p>
        <Credit href={appHref} />
      </div>
    );
  }

  const curve = [...(r.curve ?? [])].sort((x, y) => x.hour.localeCompare(y.hour));
  const flags = r.flags ?? [];
  const usualBest = flags.includes("habitual_is_best");

  return (
    <div className={s.card}>
      <div className={s.top}>
        <p className={s.place}>{heading}</p>
        <p className={s.when}>{when}</p>
      </div>
      <p className={s.kick}>{NOUN[a.key]}</p>
      <p className={s.big}>
        {r.best.start}–{r.best.end}
      </p>
      <p className={s.line}>
        {usualBest ? (
          <>The usual {habitual} is already the cleanest.</>
        ) : r.usual && r.reduction_pct != null ? (
          <>
            <strong>{signedPct(-r.reduction_pct)} PM2.5</strong> vs {r.usual.start} ·{" "}
            <span className="mono">
              {ug(r.best.mean_pm25)} vs {ug(r.usual.mean_pm25)} µg/m³
            </span>
          </>
        ) : (
          <span className="mono">{ug(r.best.mean_pm25)} µg/m³</span>
        )}
      </p>
      {flags.includes("severe_all_window") && <p className={s.warn}>Severe all day: keep it indoors if you can.</p>}
      {curve.length === 24 && (
        <div className={s.strip}>
          <DayStrip
            size="sm"
            ticks={false}
            values={curve.map((p) => p.pm25)}
            measured={curve.map((p) => p.measured)}
            window={{ start: hoursOf(r.best.start), end: hoursOf(r.best.end) }}
            usual={r.usual ? { start: hoursOf(r.usual.start), end: hoursOf(r.usual.end) } : null}
            label={`PM2.5 by hour; cleanest ${r.best.start} to ${r.best.end}.`}
          />
        </div>
      )}
      <Credit href={appHref} cams={r.source === "cams_only"} />
    </div>
  );
}

function Credit({ href = "/app", cams = false }: { href?: string; cams?: boolean }) {
  return (
    <p className={s.credit}>
      <a href={href} target="_blank" rel="noopener">
        Khidki{" "}
        <span lang="hi" className={s.hi}>
          खिड़की
        </span>
      </a>
      <span>{cams ? "CAMS forecast · CPCB via OpenAQ" : "CPCB monitors via OpenAQ"}</span>
    </p>
  );
}
