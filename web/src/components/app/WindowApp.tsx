"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type AgeBand, type AiringResult, type Place, type WindowResult } from "@/lib/api";
import { nowIST } from "@/lib/format";
import { ACTIVITIES, activityFromApi, TELEGRAM_HANDLE, TELEGRAM_URL, type ActivityKey } from "@/lib/site";
import AiringCard from "./AiringCard";
import ChatPanel from "./ChatPanel";
import PlacePicker from "./PlacePicker";
import ResultCard from "./ResultCard";
import s from "./app.module.css";

type Day = "today" | "tomorrow";

export interface Settings {
  activity: ActivityKey;
  minutes: number;
  habitual: string;
  earliest: string;
  latest: string;
  age: AgeBand;
  day: Day;
}

const STORE_KEY = "khidki:last";
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const DURATIONS = [15, 20, 30, 45, 60, 90, 120];

function defaultDay(): Day {
  return nowIST().hour >= 19 ? "tomorrow" : "today";
}

function defaults(key: ActivityKey, day: Day = defaultDay()): Settings {
  const a = ACTIVITIES.find((x) => x.key === key) ?? ACTIVITIES[0];
  return { activity: a.key, minutes: a.minutes, habitual: a.habitual, earliest: a.earliest, latest: a.latest, age: a.age, day };
}

function validPlace(p: unknown): p is Place {
  if (!p || typeof p !== "object") return false;
  const o = p as Record<string, unknown>;
  return typeof o.name === "string" && Number.isFinite(o.lat) && Number.isFinite(o.lon);
}

function readInitial(): { place: Place | null; settings: Settings } {
  let place: Place | null = null;
  let settings = defaults("walk");
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const j = JSON.parse(raw) as { place?: unknown; settings?: Partial<Settings> };
      if (validPlace(j.place)) place = j.place;
      const st = j.settings;
      if (st && ACTIVITIES.some((a) => a.key === st.activity)) {
        const d = defaults(st.activity as ActivityKey);
        settings = {
          ...d,
          minutes: typeof st.minutes === "number" && st.minutes >= 10 && st.minutes <= 240 ? st.minutes : d.minutes,
          habitual: typeof st.habitual === "string" && TIME_RE.test(st.habitual) ? st.habitual : d.habitual,
          earliest: typeof st.earliest === "string" && TIME_RE.test(st.earliest) ? st.earliest : d.earliest,
          latest: typeof st.latest === "string" && TIME_RE.test(st.latest) ? st.latest : d.latest,
          age: st.age === "child" || st.age === "older" || st.age === "adult" ? st.age : d.age,
        };
      }
    }
  } catch {
    /* storage unavailable: start fresh */
  }
  try {
    const u = new URL(window.location.href);
    const lat = Number(u.searchParams.get("lat"));
    const lon = Number(u.searchParams.get("lon"));
    if (u.searchParams.has("lat") && u.searchParams.has("lon") && Number.isFinite(lat) && Number.isFinite(lon)) {
      place = { name: u.searchParams.get("label") || `${lat.toFixed(3)}, ${lon.toFixed(3)}`, lat, lon };
    }
    const a = u.searchParams.get("activity");
    if (a) settings = defaults(activityFromApi(a).key);
    const d = u.searchParams.get("day");
    if (d === "today" || d === "tomorrow") settings = { ...settings, day: d };
  } catch {
    /* ignore malformed URLs */
  }
  return { place, settings };
}

interface Res {
  key: string;
  window?: WindowResult;
  airing?: AiringResult;
  error?: string;
}

function describe(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 422)
      return "The engine could not read these settings. Check the times: the latest time must come after the earliest.";
    if (e.status === 429) return "Too many requests from this connection. Wait a moment and try again.";
    return `The Khidki engine answered with an error (${e.status}). Try again in a minute.`;
  }
  return "Could not reach the Khidki engine. Check your connection and try again.";
}

export default function WindowApp() {
  const [init] = useState(readInitial);
  const [place, setPlace] = useState<Place | null>(init.place);
  const [st, setSt] = useState<Settings>(init.settings);
  const [nonce, setNonce] = useState(0);
  const [res, setRes] = useState<Res | null>(null);

  const preset = ACTIVITIES.find((a) => a.key === st.activity) ?? ACTIVITIES[0];
  const timesOk = TIME_RE.test(st.habitual) && TIME_RE.test(st.earliest) && TIME_RE.test(st.latest) && st.latest > st.earliest;

  const qjson =
    place && timesOk
      ? JSON.stringify({
          lat: Math.round(place.lat * 1e4) / 1e4,
          lon: Math.round(place.lon * 1e4) / 1e4,
          activity: preset.api,
          minutes: st.minutes,
          earliest: st.earliest,
          latest_end: st.latest,
          habitual: st.habitual,
          age: st.age,
          day: st.day,
        })
      : "";
  const key = qjson ? `${qjson}#${nonce}` : "";
  const persist = JSON.stringify({ place, settings: { ...st, day: undefined } });

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, persist);
    } catch {
      /* private mode: fine */
    }
  }, [persist]);

  useEffect(() => {
    if (!key) return;
    const q = JSON.parse(key.slice(0, key.lastIndexOf("#")));
    let live = true;
    const t = window.setTimeout(async () => {
      const [w, a] = await Promise.allSettled([
        api.window(q),
        api.airing({ lat: q.lat, lon: q.lon, open_minutes: 30, day: q.day }),
      ]);
      if (!live) return;
      setRes({
        key,
        window: w.status === "fulfilled" ? w.value : undefined,
        airing: a.status === "fulfilled" ? a.value : undefined,
        error: w.status === "rejected" ? describe(w.reason) : undefined,
      });
    }, 220);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [key]);

  const loading = !!key && res?.key !== key;
  const shown = key ? res : null;

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setSt((p) => ({ ...p, [k]: v }));

  return (
    <div className="wrap">
      <div className={`${s.layout} ${place ? s.hasPlace : ""}`}>
        <div className={s.head}>
          <h1 className={s.title}>Your window</h1>
          <p className={s.lede}>The cleanest hour over your street, from the government monitors around you.</p>
        </div>

        <div className={s.side} id="settings">
          <PlacePicker place={place} onPick={setPlace} />

          <fieldset className={s.field}>
            <legend className={s.label}>What you&apos;re doing</legend>
            <div className={s.chips}>
              {ACTIVITIES.map((a) => (
                <label key={a.key} className={s.chip}>
                  <input
                    type="radio"
                    name="activity"
                    value={a.key}
                    checked={st.activity === a.key}
                    onChange={() => setSt((p) => defaults(a.key, p.day))}
                  />
                  <span>{a.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className={s.grid2}>
            <label className={s.field}>
              <span className={s.label}>For how long</span>
              <select className={s.input} value={st.minutes} onChange={(e) => set("minutes", Number(e.target.value))}>
                {DURATIONS.map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </select>
            </label>
            <label className={s.field}>
              <span className={s.label}>Usually at</span>
              <input
                className={`${s.input} mono`}
                type="time"
                step={900}
                value={st.habitual}
                onChange={(e) => set("habitual", e.target.value)}
              />
            </label>
            <label className={s.field}>
              <span className={s.label}>Not before</span>
              <input
                className={`${s.input} mono`}
                type="time"
                step={900}
                value={st.earliest}
                onChange={(e) => set("earliest", e.target.value)}
              />
            </label>
            <label className={s.field}>
              <span className={s.label}>Done by</span>
              <input
                className={`${s.input} mono`}
                type="time"
                step={900}
                value={st.latest}
                onChange={(e) => set("latest", e.target.value)}
              />
            </label>
            <label className={s.field}>
              <span className={s.label}>Who</span>
              <select className={s.input} value={st.age} onChange={(e) => set("age", e.target.value as AgeBand)}>
                <option value="adult">Adult</option>
                <option value="child">Child</option>
                <option value="older">Older adult</option>
              </select>
            </label>
            <fieldset className={s.field}>
              <legend className={s.label}>Day</legend>
              <div className={s.seg}>
                {(["today", "tomorrow"] as const).map((d) => (
                  <label key={d}>
                    <input type="radio" name="day" value={d} checked={st.day === d} onChange={() => set("day", d)} />
                    <span>{d === "today" ? "Today" : "Tomorrow"}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          {!timesOk && <p className={s.warn}>&ldquo;Done by&rdquo; has to be later than &ldquo;Not before&rdquo;.</p>}
        </div>

        <div className={s.results}>
          {place && (
            <a className={s.jump} href="#settings">
              Change place, activity or times
            </a>
          )}
          <section className={`${s.card} ${s.main} ${loading && shown ? s.dim : ""}`} aria-live="polite" aria-busy={loading}>
            {!place ? (
              <div className={s.state}>
                <p className={s.stateT}>Where are you?</p>
                <p className="body">
                  Use your location, search for a place, or pick a city. Khidki reads the government air monitors within 15 km.
                </p>
              </div>
            ) : !shown ? (
              <div className={s.state}>
                <p className={s.stateT}>Reading the monitors around {place.name}…</p>
                <p className="small">Forecast and measured PM2.5, hour by hour.</p>
              </div>
            ) : shown.error || !shown.window ? (
              <div className={s.state}>
                <p className={s.stateT}>Something went wrong</p>
                <p className="body">{shown.error ?? "No answer from the engine."}</p>
                <button type="button" className="btn btn-2 btn-sm" onClick={() => setNonce((n) => n + 1)}>
                  Try again
                </button>
              </div>
            ) : (
              <ResultCard
                result={shown.window}
                place={place}
                noun={preset.noun}
                label={preset.label}
                habitual={st.habitual}
                onTomorrow={() => set("day", "tomorrow")}
              />
            )}
          </section>

          <div className={s.pair}>
            <AiringCard airing={place ? shown?.airing : undefined} pending={!!place && !shown} day={st.day} />
            <section className={s.card}>
              <h2 className={s.cardT}>Get it every day on Telegram</h2>
              <p className={s.cardP}>
                Tell the bot your routine once. Each evening it sends tomorrow&apos;s window; the next day, what the monitors
                measured and how much smoke you skipped.
              </p>
              <a className="btn btn-2 btn-sm" href={TELEGRAM_URL} rel="noopener" target="_blank">
                Open {TELEGRAM_HANDLE}
              </a>
            </section>
          </div>

          <ChatPanel place={place} />
        </div>
      </div>
    </div>
  );
}
